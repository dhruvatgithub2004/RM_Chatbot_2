"""SQLAlchemy models. Sourced tables mirror the CSVs; derived tables are computed at ingest."""
from datetime import date as DateT, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class IngestRun(Base):
    __tablename__ = "ingest_run"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    as_of_date: Mapped[DateT | None] = mapped_column(Date, nullable=True)
    merchant_file: Mapped[str] = mapped_column(String)
    pos_file: Mapped[str] = mapped_column(String)
    merchant_sha256: Mapped[str] = mapped_column(String)
    pos_sha256: Mapped[str] = mapped_column(String)
    clients_loaded: Mapped[int] = mapped_column(Integer, default=0)
    pos_rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="ok")


class IngestIssue(Base):
    __tablename__ = "ingest_issue"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String)  # quarantine | warning
    source: Mapped[str] = mapped_column(String)
    row_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    code: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(String)


# ── sourced ──────────────────────────────────────────────────────────────────
class Client(Base):
    __tablename__ = "client"
    merchant_id: Mapped[str] = mapped_column(String, primary_key=True)
    business_name: Mapped[str] = mapped_column(String)
    industry: Mapped[str] = mapped_column(String)
    mcc_code: Mapped[str] = mapped_column(String)
    business_type: Mapped[str] = mapped_column(String)
    license_authority: Mapped[str] = mapped_column(String)
    vat_registered: Mapped[bool] = mapped_column(Boolean)
    package: Mapped[str] = mapped_column(String)
    relationship_start_date: Mapped[DateT] = mapped_column(Date)
    rm_id: Mapped[str] = mapped_column(String, index=True)
    branch_id: Mapped[str] = mapped_column(String)
    account_balance_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    avg_monthly_turnover_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    synthetic_credit_score: Mapped[int] = mapped_column(Integer)
    num_pos_terminals: Mapped[int] = mapped_column(Integer)
    risk_segment: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    monthly_pos_limit_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    daily_pos_limit_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    card_product: Mapped[str] = mapped_column(String)
    card_number_masked: Mapped[str] = mapped_column(String)
    rate_tier: Mapped[int] = mapped_column(Integer)
    current_rate_pct: Mapped[float] = mapped_column(Float)
    suggested_rate_pct: Mapped[float] = mapped_column(Float)
    rate_change_recommended: Mapped[bool] = mapped_column(Boolean)
    rate_rationale: Mapped[str] = mapped_column(String)
    suggested_working_capital_limit_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    opportunity_tier: Mapped[int] = mapped_column(Integer)
    opportunity_label: Mapped[str] = mapped_column(String)
    has_pos_data: Mapped[bool] = mapped_column(Boolean, default=True)


class PosDaily(Base):
    __tablename__ = "pos_daily"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    date: Mapped[DateT] = mapped_column(Date, primary_key=True)
    daily_acquiring_volume_aed: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False))
    transaction_count: Mapped[int] = mapped_column(Integer)
    terminal_status: Mapped[str] = mapped_column(String)
    card_type: Mapped[str] = mapped_column(String)
    chargeback_count: Mapped[int] = mapped_column(Integer, default=0)
    chargeback_ratio_pct: Mapped[float] = mapped_column(Float, default=0.0)
    avg_ticket_size_aed: Mapped[float] = mapped_column(Float, default=0.0)


class ClientProduct(Base):
    """Products the client already holds (sourced: merchant_products_held_v2.csv)."""
    __tablename__ = "client_product"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    product: Mapped[str] = mapped_column(String, primary_key=True)


class NtbCandidate(Base):
    """New-to-bank cross-sell candidates (sourced: ntb_cross_sell_candidates.csv)."""
    __tablename__ = "ntb_candidate"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    candidate_product: Mapped[str] = mapped_column(String, primary_key=True)
    rationale: Mapped[str] = mapped_column(String)


# ── derived ──────────────────────────────────────────────────────────────────
class ClientFact(Base):
    __tablename__ = "client_fact"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    as_of_date: Mapped[DateT] = mapped_column(Date)
    volume_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_p30: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_change_t30_vs_p30: Mapped[float | None] = mapped_column(Float, nullable=True)
    txn_t30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    txn_p30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_ticket_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_days_t30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dormant_days_t30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_dormant_now: Mapped[bool] = mapped_column(Boolean, default=False)
    dormant_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    peak_daily_volume_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_limit_utilisation_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_limit_utilisation_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_to_turnover_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_to_turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenure_months: Mapped[int] = mapped_column(Integer, default=0)
    dominant_card_type_t30: Mapped[str | None] = mapped_column(String, nullable=True)
    premium_share_t30: Mapped[float | None] = mapped_column(Float, nullable=True)
    chargeback_count_t30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chargeback_ratio_t30: Mapped[float | None] = mapped_column(Float, nullable=True)  # % of transactions
    volume_change_m6: Mapped[float | None] = mapped_column(Float, nullable=True)  # last complete month vs first of the 6


class ClientMonthlyVolume(Base):
    __tablename__ = "client_monthly_volume"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    month: Mapped[str] = mapped_column(String, primary_key=True)  # YYYY-MM
    volume_aed: Mapped[float] = mapped_column(Float)
    txn_count: Mapped[int] = mapped_column(Integer)
    active_days: Mapped[int] = mapped_column(Integer)
    dormant_days: Mapped[int] = mapped_column(Integer)
    is_complete: Mapped[bool] = mapped_column(Boolean)


class ClientCardMix(Base):
    __tablename__ = "client_card_mix"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    window: Mapped[str] = mapped_column(String, primary_key=True)  # t30 | m6
    card_type: Mapped[str] = mapped_column(String, primary_key=True)
    volume_aed: Mapped[float] = mapped_column(Float)
    volume_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    txn_count: Mapped[int] = mapped_column(Integer)
    active_days: Mapped[int] = mapped_column(Integer)
    day_share: Mapped[float | None] = mapped_column(Float, nullable=True)


class ClientPriority(Base):
    """Prioritisation output: score, one-line reason and the signal-derived recommendation."""
    __tablename__ = "client_priority"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer, index=True)
    flagged: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(String)
    signals: Mapped[list] = mapped_column(JSON)  # [{code, points, text}]
    rec_category: Mapped[str | None] = mapped_column(String, nullable=True)
    rec_title: Mapped[str | None] = mapped_column(String, nullable=True)
    rec_why: Mapped[str | None] = mapped_column(String, nullable=True)
    rec_points: Mapped[float] = mapped_column(Float, default=0.0)
    pitch_kind: Mapped[str | None] = mapped_column(String, nullable=True)       # Lending | Cross-sell
    pitch_title: Mapped[str | None] = mapped_column(String, nullable=True)
    pitch_why: Mapped[str | None] = mapped_column(String, nullable=True)
    pitch_amount_aed: Mapped[float | None] = mapped_column(Float, nullable=True)
    ntb: Mapped[list] = mapped_column(JSON, default=list)                        # all supplied NTB candidates


class ClientSuggestion(Base):
    """One decision per client: what the RM should pitch / do next. source: llm | rules (LLM failed or invalid)."""
    __tablename__ = "client_suggestion"
    merchant_id: Mapped[str] = mapped_column(ForeignKey("client.merchant_id"), primary_key=True)
    source: Mapped[str] = mapped_column(String)                       # llm | rules
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)                         # lending | cross_sell | retention | none
    product: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_aed: Mapped[float | None] = mapped_column(Float, nullable=True)
    why: Mapped[str] = mapped_column(String)
    next_action: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[float] = mapped_column(Float, default=0.0)       # 0-100, LLM's own strength-of-opportunity rating
    note: Mapped[str | None] = mapped_column(String, nullable=True)   # validation note (e.g. amount clamped, fallback reason)
    generated_at: Mapped[datetime] = mapped_column(DateTime)
