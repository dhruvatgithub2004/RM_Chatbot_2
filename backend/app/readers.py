"""Data access layer.

`PortfolioReader` sees the whole book. `ClientReader` is bound to exactly ONE merchant_id at
construction and has no method that takes another id or returns a list of clients: the Merchant
Co-pilot can only reach data through it, so the scoping is enforced by code, not by a prompt.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import config
from . import models as m

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

class ClientNotFound(Exception):
    pass


class PortfolioReader:
    def __init__(self, session: Session):
        self.s = session

    # ── status ──────────────────────────────────────────────────────────────
    def status(self) -> dict:
        run = self.s.scalars(select(m.IngestRun).order_by(m.IngestRun.id.desc())).first()
        n = self.s.scalar(select(func.count()).select_from(m.Client)) or 0
        flagged = self.s.scalar(select(func.count()).select_from(m.ClientPriority).where(m.ClientPriority.flagged)) or 0
        if not run:
            return dict(loaded=False, clients=0, flagged=0, synthetic=True, disclaimer=config.DISCLAIMER)
        return dict(
            loaded=True, as_of_date=run.as_of_date.isoformat() if run.as_of_date else None, clients=n, flagged=flagged,
            pos_rows=run.pos_rows_loaded, quarantined=run.quarantined, warnings=run.warnings,
            ingested_at=run.started_at.isoformat(), synthetic=True, disclaimer=config.DISCLAIMER,
            llm_configured=bool(config.LLM_API_KEY), llm_provider=config.LLM_PROVIDER if config.LLM_API_KEY else None,
            llm_model=config.LLM_MODEL if config.LLM_API_KEY else None,
            suggestions_source=self._suggestions_source(),
        )

    def _suggestions_source(self) -> dict:
        n_llm = self.s.scalar(select(func.count()).select_from(m.ClientSuggestion).where(m.ClientSuggestion.source == "llm")) or 0
        n_all = self.s.scalar(select(func.count()).select_from(m.ClientSuggestion)) or 0
        return dict(mode="llm" if n_llm else "rules", llm_decisions=n_llm, rule_fallbacks=n_all - n_llm)

    # ── lists ───────────────────────────────────────────────────────────────
    def _ranked(self):
        return (select(m.Client, m.ClientPriority, m.ClientFact)
                .join(m.ClientPriority, m.ClientPriority.merchant_id == m.Client.merchant_id)
                .join(m.ClientFact, m.ClientFact.merchant_id == m.Client.merchant_id)
                .order_by(m.ClientPriority.rank))

    def dashboard(self, flt: str = "all", q: str = "") -> dict:
        stmt = self._ranked()
        if flt == "opp":
            stmt = stmt.where(m.ClientPriority.flagged)
        elif flt == "high":
            stmt = stmt.where(m.Client.risk_segment == "High")
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(m.Client.business_name).like(like), func.lower(m.Client.industry).like(like),
                                  func.lower(m.Client.merchant_id).like(like)))
        rows = self.s.execute(stmt).all()
        flagged = self.s.scalar(select(func.count()).select_from(m.ClientPriority).where(m.ClientPriority.flagged)) or 0
        sug = self._suggestion_rows()      # the AI decision (or the rule fallback) for each client, shown next to the attention reason

        def decision(mid: str):
            x = sug.get(mid)
            return None if x is None else dict(kind=x.kind, product=x.product, amount_aed=x.amount_aed, next_action=x.next_action,
                                               priority=x.priority, source=x.source, model=x.model)
        return dict(
            flagged_count=flagged,
            decisions_source=self._suggestions_source()["mode"],
            clients=[dict(rank=i, merchant_id=c.merchant_id, name=c.business_name, city=c.city, industry=c.industry,
                          reason=p.reason, score=p.score, flagged=p.flagged, risk=c.risk_segment, is_dormant_now=f.is_dormant_now,
                          decision=decision(c.merchant_id))
                     for i, (c, p, f) in enumerate(rows, start=1)],
        )

    def client_directory(self, q: str = "", balance_min: float | None = None, balance_max: float | None = None,
                         segment: str | None = None, card_type: str | None = None, product: str | None = None) -> list[dict]:
        """Light list for the Profile & analytics rail (ordered by priority rank). Filters are optional and combine with AND."""
        stmt = select(m.Client.merchant_id, m.Client.business_name, m.Client.industry, m.Client.city,
                      m.ClientPriority.rank).join(m.ClientPriority, m.ClientPriority.merchant_id == m.Client.merchant_id
                                                  ).order_by(m.ClientPriority.rank)
        if balance_min is not None:
            stmt = stmt.where(m.Client.account_balance_aed >= balance_min)
        if balance_max is not None:
            stmt = stmt.where(m.Client.account_balance_aed <= balance_max)
        if segment:
            stmt = stmt.where(m.Client.package == segment)
        if card_type:
            stmt = stmt.where(m.Client.card_product == card_type)
        if product:
            stmt = stmt.where(select(m.ClientProduct.merchant_id).where(
                m.ClientProduct.merchant_id == m.Client.merchant_id, m.ClientProduct.product == product).exists())
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(m.Client.business_name).like(like), func.lower(m.Client.industry).like(like),
                                  func.lower(m.Client.merchant_id).like(like)))
        return [dict(merchant_id=a, name=b, industry=c, city=d, rank=r) for a, b, c, d, r in self.s.execute(stmt).all()]

    def client_filter_options(self) -> dict:
        """Choices (with client counts) for the Profile & analytics rail filters, plus the balance bounds."""
        def counts(col):
            return [dict(value=v, count=n) for v, n in self.s.execute(
                select(col, func.count()).group_by(col).order_by(func.count().desc(), col)).all()]
        lo, hi = self.s.execute(select(func.min(m.Client.account_balance_aed), func.max(m.Client.account_balance_aed))).one()
        return dict(balance=dict(min=lo, max=hi), segment=counts(m.Client.package), card_type=counts(m.Client.card_product),
                    product=counts(m.ClientProduct.product))

    def _suggestion_rows(self) -> dict[str, m.ClientSuggestion]:
        return {x.merchant_id: x for x in self.s.scalars(select(m.ClientSuggestion))}

    def pitch_list(self) -> list[dict]:
        """Clients to pitch, strongest first.

        When the LLM has decided (client_suggestion has rows) the order is the LLM's own priority; clients where the LLM chose
        retention/none have no pitch. Otherwise it falls back to the supplied-data rules (opportunity tier, then limit).
        """
        sug = self._suggestion_rows()
        base = (select(m.Client, m.ClientPriority)
                .join(m.ClientPriority, m.ClientPriority.merchant_id == m.Client.merchant_id))
        items = []
        if sug:
            for c, p in self.s.execute(base).all():
                x = sug.get(c.merchant_id)
                if x and x.kind in ("lending", "cross_sell"):
                    items.append((c, dict(category="Lending" if x.kind == "lending" else "Cross-sell", product=x.product, amount_aed=x.amount_aed,
                                          explanation=x.why, next_action=x.next_action, priority=x.priority, source=x.source, model=x.model)))
            items.sort(key=lambda t: (-t[1]["priority"], t[0].opportunity_tier, -t[0].suggested_working_capital_limit_aed, t[0].merchant_id))
        else:
            for c, p in self.s.execute(base.where(m.ClientPriority.pitch_kind.is_not(None))).all():
                items.append((c, dict(category=p.pitch_kind, product=p.pitch_title, amount_aed=p.pitch_amount_aed, explanation=p.pitch_why,
                                      next_action=p.rec_title, priority=None, source="rules", model=None)))
            items.sort(key=lambda t: (t[0].opportunity_tier, t[1]["category"] != "Lending", -t[0].suggested_working_capital_limit_aed,
                                      -t[0].synthetic_credit_score, t[0].merchant_id))
        return [dict(rank=i, merchant_id=c.merchant_id, name=c.business_name, industry=c.industry, city=c.city,
                     opportunity_label=c.opportunity_label, **d) for i, (c, d) in enumerate(items, start=1)]

    def suggestions(self, limit: int = 10, product: str | None = None) -> list[dict]:
        """Top `limit` pitches; with `product`, the top `limit` among pitches for that product (global rank is kept)."""
        items = self.pitch_list()
        if product:
            items = [x for x in items if x["product"] == product]
        return items[:limit]

    def suggestion_products(self) -> list[dict]:
        """Products that appear in the pitch list, with how many clients each is pitched to."""
        counts: dict[str, int] = {}
        for x in self.pitch_list():
            counts[x["product"]] = counts.get(x["product"], 0) + 1
        return [dict(product=k, count=v) for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    # ── co-pilot context ────────────────────────────────────────────────────
    def portfolio_rows(self) -> list[dict]:
        out = []
        held: dict[str, list[str]] = {}
        for mid, prod in self.s.execute(select(m.ClientProduct.merchant_id, m.ClientProduct.product)).all():
            held.setdefault(mid, []).append(prod)
        pitches = {x["merchant_id"]: x for x in self.pitch_list()}
        sug = self._suggestion_rows()
        for c, p, f in self.s.execute(self._ranked()).all():
            out.append(dict(
                id=c.merchant_id, name=c.business_name, city=c.city, industry=c.industry, package=c.package, risk=c.risk_segment,
                rm=c.rm_id, rank=p.rank, score=p.score, flagged=p.flagged, reason=p.reason,
                vol_t30=f.volume_t30, vol_change=f.volume_change_t30_vs_p30, dormant_days=f.dormant_streak_days,
                limit_util=f.monthly_limit_utilisation_t30, balance=c.account_balance_aed,
                rec=(f"{p.rec_category}: {p.rec_title}" if p.rec_title else None), rec_category=p.rec_category,
                card_product=c.card_product, rate_current=c.current_rate_pct, rate_suggested=c.suggested_rate_pct,
                rate_change=c.rate_change_recommended, wc_limit=c.suggested_working_capital_limit_aed,
                opportunity=c.opportunity_label, products=sorted(held.get(c.merchant_id, [])),
                ntb=[x["candidate_product"] for x in (p.ntb or [])],
                pitch=(f"{pitches[c.merchant_id]['category']}: {pitches[c.merchant_id]['product']}" if c.merchant_id in pitches else None),
                pitch_rank=pitches[c.merchant_id]["rank"] if c.merchant_id in pitches else None,
                pitch_why=pitches[c.merchant_id]["explanation"] if c.merchant_id in pitches else None,
                lending_pitch_limit=(pitches[c.merchant_id]["amount_aed"] if c.merchant_id in pitches and pitches[c.merchant_id]["category"] == "Lending" else None),
                next_action=(sug[c.merchant_id].next_action if c.merchant_id in sug else None),
            ))
        return out

    def directory_names(self) -> list[tuple[str, str]]:
        return [(r[0], r[1]) for r in self.s.execute(select(m.Client.merchant_id, m.Client.business_name)).all()]

    def client_exists(self, merchant_id: str) -> bool:
        return self.s.get(m.Client, merchant_id) is not None


class ClientReader:
    """Bound to a single client. Every query below filters on self.merchant_id."""

    def __init__(self, session: Session, merchant_id: str):
        self.s = session
        self.merchant_id = merchant_id
        if self.s.get(m.Client, merchant_id) is None:
            raise ClientNotFound(merchant_id)

    def _client(self) -> m.Client:
        return self.s.get(m.Client, self.merchant_id)

    def _fact(self) -> m.ClientFact:
        return self.s.get(m.ClientFact, self.merchant_id)

    def _priority(self) -> m.ClientPriority:
        return self.s.get(m.ClientPriority, self.merchant_id)

    def _suggestion(self) -> dict | None:
        x = self.s.get(m.ClientSuggestion, self.merchant_id)
        if not x:
            return None
        return dict(source=x.source, model=x.model, kind=x.kind, product=x.product, amount_aed=x.amount_aed, why=x.why,
                    next_action=x.next_action, priority=x.priority, note=x.note)

    def _pitch(self, p: m.ClientPriority) -> dict | None:
        """The pitch for this client: the LLM's decision when it exists, else the rule-based one."""
        x = self.s.get(m.ClientSuggestion, self.merchant_id)
        if x is not None:
            if x.kind not in ("lending", "cross_sell"):
                return None
            return dict(kind="Lending" if x.kind == "lending" else "Cross-sell", title=x.product, why=x.why, amount_aed=x.amount_aed, source=x.source)
        return (dict(kind=p.pitch_kind, title=p.pitch_title, why=p.pitch_why, amount_aed=p.pitch_amount_aed, source="rules")
                if p.pitch_kind else None)

    def products(self) -> list[str]:
        stmt = select(m.ClientProduct.product).where(m.ClientProduct.merchant_id == self.merchant_id).order_by(m.ClientProduct.product)
        return list(self.s.scalars(stmt))

    def monthly(self, complete_only: bool = False) -> list[m.ClientMonthlyVolume]:
        stmt = select(m.ClientMonthlyVolume).where(m.ClientMonthlyVolume.merchant_id == self.merchant_id)
        if complete_only:
            stmt = stmt.where(m.ClientMonthlyVolume.is_complete)
        return list(self.s.scalars(stmt.order_by(m.ClientMonthlyVolume.month)))

    def card_mix(self, window: str = "t30") -> list[m.ClientCardMix]:
        stmt = (select(m.ClientCardMix).where(m.ClientCardMix.merchant_id == self.merchant_id, m.ClientCardMix.window == window)
                .order_by(m.ClientCardMix.volume_aed.desc()))
        return list(self.s.scalars(stmt))

    def daily(self, last_n_days: int = 30) -> list[dict]:
        stmt = (select(m.PosDaily).where(m.PosDaily.merchant_id == self.merchant_id)
                .order_by(m.PosDaily.date.desc()).limit(last_n_days))
        rows = list(self.s.scalars(stmt))[::-1]
        return [dict(date=r.date.isoformat(), volume_aed=r.daily_acquiring_volume_aed, transactions=r.transaction_count,
                     terminal_status=r.terminal_status, card_type=r.card_type) for r in rows]

    def detail(self) -> dict:
        c, f, p = self._client(), self._fact(), self._priority()
        complete = self.monthly(complete_only=True)[-6:]
        peak = max((r.volume_aed for r in complete), default=0) or 1
        bars = [dict(month=MONTH_ABBR[int(r.month[5:]) - 1], month_key=r.month, volume_aed=r.volume_aed,
                     height_pct=round(r.volume_aed / peak * 100)) for r in complete]
        mix = [dict(type=r.card_type, pct=round((r.volume_share or 0) * 100, 1), txns=r.txn_count,
                    volume_aed=r.volume_aed, active_days=r.active_days) for r in self.card_mix("t30")]
        return dict(
            merchant_id=c.merchant_id, name=c.business_name, city=c.city, industry=c.industry,
            card_pos=dict(
                card_no=c.card_number_masked, card_type=c.card_product,
                dominant_tier_t30=f.dominant_card_type_t30,  # per-day card label (Mass/Premium/Super Premium/Debit/Business) with most volume
                monthly_pos_limit_aed=c.monthly_pos_limit_aed, daily_pos_limit_aed=c.daily_pos_limit_aed,
                volume_t30=f.volume_t30, txn_t30=f.txn_t30, num_pos_terminals=c.num_pos_terminals,
                monthly_limit_utilisation=f.monthly_limit_utilisation_t30,
            ),
            profile=dict(
                balance_aed=c.account_balance_aed, risk_segment=c.risk_segment, segment=c.package,
                existing_products=self.products(),
                synthetic_credit_score=c.synthetic_credit_score, avg_monthly_turnover_aed=c.avg_monthly_turnover_aed,
                relationship_start_date=c.relationship_start_date.isoformat(), tenure_months=f.tenure_months,
                business_type=c.business_type, license_authority=c.license_authority, vat_registered=c.vat_registered,
                rm_id=c.rm_id, branch_id=c.branch_id,
            ),
            rate=dict(
                available=True, tier=c.rate_tier, current_pct=c.current_rate_pct, suggested_pct=c.suggested_rate_pct,
                change_recommended=c.rate_change_recommended, rationale=c.rate_rationale,
            ),
            lending=dict(suggested_working_capital_limit_aed=c.suggested_working_capital_limit_aed,
                         opportunity_tier=c.opportunity_tier, opportunity_label=c.opportunity_label),
            ntb_candidates=list(p.ntb or []),
            pitch=self._pitch(p), suggestion=self._suggestion(),
            volume_bars=bars, card_mix=mix,
            behaviour=dict(
                volume_change_t30_vs_p30=f.volume_change_t30_vs_p30, volume_change_m6=f.volume_change_m6,
                is_dormant_now=f.is_dormant_now, dormant_streak_days=f.dormant_streak_days, dormant_days_t30=f.dormant_days_t30,
                peak_daily_volume_t30=f.peak_daily_volume_t30, daily_limit_utilisation_t30=f.daily_limit_utilisation_t30,
                volume_to_turnover_t30=f.volume_to_turnover_t30, balance_to_turnover=f.balance_to_turnover,
                avg_ticket_t30=f.avg_ticket_t30, premium_share_t30=f.premium_share_t30,
                chargeback_count_t30=f.chargeback_count_t30, chargeback_ratio_t30_pct=f.chargeback_ratio_t30,
            ),
            priority=dict(rank=p.rank, score=p.score, flagged=p.flagged, reason=p.reason, signals=p.signals),
            recommendation=(dict(category=p.rec_category, title=p.rec_title, why=p.rec_why) if p.rec_title else None),
            as_of_date=f.as_of_date.isoformat(),
        )
