"""Rate ranges: the suggested merchant rate is shown as a range, never as one exact figure.

Why: the suggested rate is interchange cost plus a spread predicted by a model trained on a SYNTHETIC cohort, and it rests on assumptions
(all volume treated as Visa, an approximate card-type mapping, a debit cap applied to the daily average ticket). A single figure such as
1.67% reads as more precise than it is. The range is the model's estimate plus or minus HALF_WIDTH_PP, rounded outward to STEP_PP.

HALF_WIDTH_PP is an assumption, not a measured prediction interval. It is twice the 0.05-point noise the model script puts into its
synthetic training spreads (ml_rate_model.py), which is the only uncertainty quantified anywhere in the project. The exact value stays in
the database (suggested_rate_pct) for the recommendation rule and the audit trail; it is not shown to the RM or sent to the language model.

This module has no heavy imports, so it can be used from ingest, scoring, readers, the co-pilot and the suggestion engine alike.
Run `python -m app.rates` once to bring text already stored in the database in line (it keeps a backup copy of the database first).
"""
from __future__ import annotations

import math
import re

HALF_WIDTH_PP = 0.10
STEP_PP = 0.05
ILLUSTRATIVE = "Ranges are illustrative: the model's estimate plus or minus 0.10 points, rounded."


def band(suggested: float) -> tuple[float, float]:
    """(low, high) of the range around the model's rate, rounded outward to the nearest STEP_PP. Width is 0.20 to 0.25 points."""
    low = math.floor((suggested - HALF_WIDTH_PP) / STEP_PP + 1e-9) * STEP_PP
    high = math.ceil((suggested + HALF_WIDTH_PP) / STEP_PP - 1e-9) * STEP_PP
    return round(low, 2), round(high, 2)


def text(suggested: float) -> str:
    """The range as text, for example "1.55%–1.80%"."""
    low, high = band(suggested)
    return f"{low:.2f}%–{high:.2f}%"


def position(current: float, suggested: float) -> str:
    """Where the current rate sits against the range: above, below or within."""
    low, high = band(suggested)
    return "above" if current > high + 1e-9 else "below" if current < low - 1e-9 else "within"


# ── the model script's rationale text, rewritten with rounded figures ───────────────────────────────────────────────────────────────
_RATIONALE = re.compile(
    r"Estimated Visa interchange cost ([\d.]+)% .*?\+ modelled spread ([\d.]+)pp = [\d.]+%, vs current ([\d.]+)% "
    r"\(margin over interchange [\d.]+pp\)\. .*? Main spread drivers: (.*?)\. Spread and rates are illustrative\.", re.S)
_DRIVER = re.compile(r"(.+?) \(([+-])[\d.]+pp\)")
_NEW_RATIONALE = "The model puts this merchant's rate at about "


def _round_to(x: float, step: float) -> float:
    return round(round(x / step) * step, 2)


def rewrite_rationale(old: str, current: float, suggested: float, change_recommended: bool) -> str:
    """The rationale with the exact modelled rate, spread and cost replaced by rounded figures and a range. Safe to call on text that
    has already been rewritten. If the text is not in the model script's format, a shorter explanation is built from the rates."""
    if old.startswith(_NEW_RATIONALE):
        return old
    low, high = band(suggested)
    where = position(current, suggested)
    head = f"{_NEW_RATIONALE}{low:.2f}%–{high:.2f}%"
    m = _RATIONALE.search(old)
    if m:
        head += (f" (an estimated card cost of about {_round_to(float(m.group(1)), 0.05):.2f}% plus a spread of roughly "
                 f"{_round_to(float(m.group(2)), 0.1):.1f} points). ")
    else:
        head += ". "
    if not change_recommended:
        tail = f"The current rate, {current:.2f}%, is within that range: no change recommended."
    elif where == "above":
        tail = f"The current rate, {current:.2f}%, is above that range: retention risk, consider a proactive reduction."
    elif where == "below":
        tail = f"The current rate, {current:.2f}%, is below that range: under-priced for this card mix, review upward at next renewal."
    else:
        tail = (f"The current rate, {current:.2f}%, is inside that range, so a change is recommended but the case is marginal: "
                "the gap to the model is smaller than its margin.")
    drivers = ""
    if m:
        parts = [f"{label.strip(', ')} ({'pushes it up' if sign == '+' else 'pulls it down'})" for label, sign in _DRIVER.findall(m.group(4))]
        drivers = f" Main spread drivers: {', '.join(parts)}." if parts else ""
    return f"{head}{tail}{drivers} {ILLUSTRATIVE}"


# ── the attention flag ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
_REVIEW = re.compile(r"Rate review: ([\d.]+)% → ([\d.]+)% recommended")


def review_text(current: float, suggested: float) -> str:
    """The attention-flag wording for a recommended rate change."""
    return f"Rate review: current {current:.2f}%, model range {text(suggested)}"


def rewrite_review(stored: str) -> str:
    """Replace the old "Rate review: 2.49% → 2.14% recommended" wording inside a stored flag text. Other text is returned unchanged."""
    return _REVIEW.sub(lambda m: review_text(float(m.group(1)), float(m.group(2))), stored)


# ── text written by the suggestion engine ───────────────────────────────────────────────────────────────────────────────────────────
def mask_exact(written: str | None, suggested: float) -> str | None:
    """Replace the exact suggested rate, where the engine quoted it, with the range. 1.96% and 1.9% both match a suggested 1.96 / 1.90."""
    if not written:
        return written
    forms = {f"{suggested:.2f}"} | ({f"{suggested:.1f}"} if abs(round(suggested, 1) - suggested) < 1e-9 else set())
    pattern = r"(?<![\d.])(?:" + "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + r")\s?%"
    return re.sub(pattern, text(suggested), written)


# ── one-off: bring text already stored in the database in line ──────────────────────────────────────────────────────────────────────
def migrate(session) -> dict[str, int]:
    """Rewrite the rate wording already stored in the database: flag texts in client_priority, and exact rates quoted in the suggestion
    engine's explanations and next steps. Safe to run more than once. Numeric columns are not touched."""
    from . import models as m

    counts = dict(flags=0, suggestion_texts=0)
    exact = {c.merchant_id: c.suggested_rate_pct for c in session.query(m.Client)}
    for p in session.query(m.ClientPriority):
        reason = rewrite_review(p.reason)
        signals = [dict(x, text=rewrite_review(x["text"])) for x in (p.signals or [])]
        if reason != p.reason or signals != (p.signals or []):
            p.reason, p.signals = reason, signals
            counts["flags"] += 1
    for s in session.query(m.ClientSuggestion):
        # Rule-based decisions copy the attention-flag text into `why`, so the old flag wording is rewritten in every row; the exact
        # rate is masked only in model-written text, where the engine may have quoted it.
        why, nxt, note = rewrite_review(s.why), rewrite_review(s.next_action or ""), rewrite_review(s.note or "")
        if s.source == "llm" and s.merchant_id in exact:
            why, nxt = mask_exact(why, exact[s.merchant_id]), mask_exact(nxt, exact[s.merchant_id])
        if (why, nxt or None, note or None) != (s.why, s.next_action, s.note):
            s.why, s.next_action, s.note = why, nxt or None, note or None
            counts["suggestion_texts"] += 1
    session.commit()
    return counts


if __name__ == "__main__":
    import shutil
    from datetime import datetime

    from . import config
    from .db import SessionLocal

    path = config.DATABASE_URL.replace("sqlite:///", "")
    backup = f"{path}.bak-{datetime.now():%Y%m%d-%H%M%S}-before-rate-ranges"
    shutil.copyfile(path, backup)
    with SessionLocal() as s:
        print("backup:", backup, "| rewritten:", migrate(s))
