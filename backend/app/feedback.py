"""RM ratings of suggestions: "was this useful?".

A rating stores a snapshot of what was suggested (product, amount, who decided, priority) next to the verdict, so it stays meaningful
after suggestions are regenerated, and so usefulness can be summarised by product and by who decided (the AI or the rules). Ratings live
in their own tables (db.FeedbackBase) so a data reload does not erase them. Every rating is also written to the audit log.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from . import models as m
from .db import FeedbackBase, engine

VERDICTS = ("useful", "not_useful")
MAX_REASON = 300
_ready = False


class NothingToRate(Exception):
    """The client has no suggestion right now (no pitch, no retention action), so there is nothing to rate."""


def ensure_tables() -> None:
    """Create the feedback table if it is missing. Cheap and idempotent; called before every use so tests and fresh databases work."""
    global _ready
    if not _ready:
        FeedbackBase.metadata.create_all(engine)
        _ready = True


def key_for(kind: str, product: str | None) -> str:
    return product or kind


def current_decision(detail: dict) -> dict | None:
    """What the RM is being shown for this client right now, from a client detail: the stored decision, else the rule-based pitch.
    None when there is nothing to act on."""
    s = detail.get("suggestion")
    if s:
        if s["kind"] == "none":
            return None
        return dict(kind=s["kind"], product=s["product"], amount_aed=s["amount_aed"], source=s["source"], model=s["model"], priority=s["priority"],
                    why=s["why"], next_action=s["next_action"], note=s.get("note"))
    p = detail.get("pitch")
    if p:
        rec = detail.get("recommendation")
        return dict(kind="lending" if p["kind"] == "Lending" else "cross_sell", product=p["title"], amount_aed=p["amount_aed"], source="rules", model=None,
                    priority=None, why=p["why"], next_action=rec["title"] if rec else None, note=None)
    return None


def verdicts(session: Session) -> dict[tuple[str, str], dict]:
    """Every rating, keyed by (merchant_id, suggestion key), as {verdict, reason}."""
    ensure_tables()
    return {(r.merchant_id, r.suggestion_key): dict(verdict=r.verdict, reason=r.reason)
            for r in session.scalars(select(m.ClientFeedback))}


def record(session: Session, merchant_id: str, decision: dict, verdict: str, reason: str | None) -> dict:
    """Save (or replace) the rating of the suggestion `decision` for this client."""
    ensure_tables()
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    key, now = key_for(decision["kind"], decision["product"]), datetime.now(timezone.utc).replace(tzinfo=None)
    reason = (reason or "").strip()[:MAX_REASON] or None      # optional for both verdicts
    row =session.scalar(select(m.ClientFeedback).where(m.ClientFeedback.merchant_id == merchant_id, m.ClientFeedback.suggestion_key == key))
    if row is None:
        row = m.ClientFeedback(merchant_id=merchant_id, suggestion_key=key, created_at=now)
        session.add(row)
    row.kind, row.product, row.amount_aed = decision["kind"], decision["product"], decision["amount_aed"]
    row.source, row.model, row.priority = decision["source"], decision["model"], decision["priority"]
    row.verdict, row.reason, row.updated_at = verdict, reason, now
    session.commit()
    audit.record("feedback", merchant_id=merchant_id, suggestion=key, verdict=verdict, reason=reason, source=row.source, model=row.model)
    return dict(verdict=row.verdict, reason=row.reason)


def clear(session: Session, merchant_id: str, decision: dict) -> bool:
    """Remove the rating of this suggestion (the RM changed their mind). True if there was one."""
    ensure_tables()
    key = key_for(decision["kind"], decision["product"])
    row = session.scalar(select(m.ClientFeedback).where(m.ClientFeedback.merchant_id == merchant_id, m.ClientFeedback.suggestion_key == key))
    if row is None:
        return False
    session.delete(row)
    session.commit()
    audit.record("feedback", merchant_id=merchant_id, suggestion=key, verdict="cleared", source=row.source, model=row.model)
    return True


def _split(rows) -> dict:
    out = dict(useful=0, not_useful=0)
    for verdict, n in rows:
        out[verdict] = n
    out["rated"] = out["useful"] + out["not_useful"]
    out["useful_share"] = round(out["useful"] / out["rated"], 3) if out["rated"] else None
    return out


def summary(session: Session) -> dict:
    """How useful have suggestions been? Overall, by who decided, by product, and the reasons given for 'not useful'."""
    ensure_tables()
    F = m.ClientFeedback
    overall = _split(session.execute(select(F.verdict, func.count()).group_by(F.verdict)).all())
    by_source = {src: _split(session.execute(select(F.verdict, func.count()).where(F.source == src).group_by(F.verdict)).all()) for src in ("llm", "rules")}
    by_product = {}
    for key in session.scalars(select(F.suggestion_key).distinct()):
        by_product[key] = _split(session.execute(select(F.verdict, func.count()).where(F.suggestion_key == key).group_by(F.verdict)).all())
    reasons = dict(session.execute(select(F.reason, func.count()).where(F.verdict == "not_useful", F.reason.is_not(None)).group_by(F.reason)
                                   .order_by(func.count().desc())).all())
    return dict(overall=overall, by_source=by_source, by_product=by_product, not_useful_reasons=reasons)


def track_record(session: Session, key: str, source: str) -> dict:
    """The ratings other suggestions of the same product, and by the same decider, have had. Shown next to a suggestion."""
    ensure_tables()
    F = m.ClientFeedback
    return dict(same_suggestion=_split(session.execute(select(F.verdict, func.count()).where(F.suggestion_key == key).group_by(F.verdict)).all()),
                same_source=_split(session.execute(select(F.verdict, func.count()).where(F.source == source).group_by(F.verdict)).all()))
