"""The AI decision engine (suggest_llm): retention precondition, priority built from three parts, peer percentiles,
name-tolerant held-product matching and the rule fallback. Offline: the model is never called."""
import pytest

from app import catalogue, models as m, suggest_llm as S
from app.db import SessionLocal

BASE = {"products_held": ["Current Account"], "suggested_working_capital_limit_aed": 120_000}


def raw(**kw):
    base = dict(kind="cross_sell", product="Payroll / WPS Services", amount_aed=None, why="A valid reason for the RM here.",
                next_action="Call", opportunity=30, signal=20, fit=20)
    return {**base, **kw}


# ── retention needs a behavioural signal ────────────────────────────────────
@pytest.mark.parametrize("codes,allowed", [
    (["dormant"], True), (["decline_30d", "rate_review"], True), (["decline_6m"], True),
    (["rate_review"], False), (["idle_balance"], False), (["rate_review", "idle_balance", "risk_segment"], False), ([], False)])
def test_retention_requires_dormancy_or_falling_volume(codes, allowed):
    clean, note = S.validate(raw(kind="retention", product=None), {**BASE, "attention_signal_codes": codes})
    assert (clean is not None) is allowed
    if not allowed:
        assert "retention needs dormant terminals or falling volume" in note       # the reason is fed back to the model on retry


def test_retention_rule_is_skipped_when_signal_codes_are_unknown():
    assert S.validate(raw(kind="retention", product=None), BASE)[0] is not None


def test_other_kinds_do_not_need_a_signal():
    assert S.validate(raw(), {**BASE, "attention_signal_codes": ["rate_review"]})[0]["kind"] == "cross_sell"
    assert S.validate(raw(kind="none", product=None), {**BASE, "attention_signal_codes": []})[0]["kind"] == "none"


# ── priority = opportunity + signal + fit ───────────────────────────────────
def test_priority_is_the_sum_of_three_clamped_parts():
    assert S.validate(raw(opportunity=30, signal=20, fit=25), BASE)[0]["priority"] == 75
    assert S.validate(raw(opportunity=99, signal=-5, fit=99), BASE)[0]["priority"] == 40 + 0 + 30      # each part is clamped to its range
    assert S.validate(raw(opportunity=None, signal=None, fit=None, priority=61), BASE)[0]["priority"] == 61   # older single-number answers still work
    assert S.validate(raw(opportunity="x"), BASE)[0] is None


def test_peer_percentiles():
    payloads = {f"M{i}": {"avg_monthly_turnover_aed": i * 1000, "account_balance_aed": 5, "suggested_working_capital_limit_aed": i,
                          "pos_last_30d": {"volume_aed": None}} for i in range(1, 101)}
    S.add_peer_percentiles(payloads)
    pct = [payloads[f"M{i}"]["peer_percentile"]["turnover"] for i in range(1, 101)]
    assert pct == sorted(pct) and pct[0] == 0 and pct[-1] == 99                                       # rank among all clients, 0 to 100
    assert payloads["M50"]["peer_percentile"]["balance"] == 0 and payloads["M50"]["peer_percentile"]["volume_last_30d"] == 0   # ties rank lowest


# ── held products ───────────────────────────────────────────────────────────
def test_held_matching_tolerates_shorter_names_in_the_data():
    assert catalogue.holds(["smartTRADE"], "Trade Finance (smartTRADE)")
    assert catalogue.holds(["businessONLINE", "Current Account"], "businessONLINE")
    assert not catalogue.holds(["Current Account"], "Trade Finance (smartTRADE)")
    clean, note = S.validate(raw(product="Trade Finance (smartTRADE)"), {**BASE, "products_held": ["smartTRADE"]})
    assert clean is None and "already holds" in note


def test_payload_carries_codes_and_only_products_the_client_can_be_pitched():
    with SessionLocal() as s:
        mid = next(r[0] for r in s.query(m.ClientProduct.merchant_id, m.ClientProduct.product).all() if "smartTRADE" in r[1])
        p = S.build_payload(s, mid)
    assert isinstance(p["attention_signal_codes"], list)
    assert "Trade Finance (smartTRADE)" not in p["pitchable_products_not_held"] and "Semi Secured Business Loan" not in p["pitchable_products_not_held"]
    assert "Payroll / WPS Services" in p["pitchable_products_not_held"] or "Payroll / WPS Services" in p["products_held"]


def test_rule_fallback_never_pitches_a_product_the_client_already_holds():
    from datetime import datetime
    with SessionLocal() as s:
        held = {}
        for mid, prod in s.query(m.ClientProduct.merchant_id, m.ClientProduct.product).all():
            held.setdefault(mid, []).append(prod)
        clash = [p.merchant_id for p in s.query(m.ClientPriority).filter(m.ClientPriority.pitch_title.is_not(None)).all()
                 if catalogue.holds(held.get(p.merchant_id, []), p.pitch_title)]
        assert clash, "the supplied data has candidates that are already held; this test needs one"
        row = S._rules_row(s, clash[0], "test", datetime.now())
    assert row["kind"] == "none" and row["product"] is None and "already held" in row["note"]


def test_dashboard_rows_carry_the_ai_decision():
    from datetime import datetime
    from fastapi.testclient import TestClient
    from app.main import app
    api = TestClient(app)
    assert all(c["decision"] is None for c in api.get("/api/dashboard").json()["clients"])       # nothing decided yet
    top = api.get("/api/dashboard").json()["clients"][0]["merchant_id"]
    with SessionLocal() as s:
        s.add(m.ClientSuggestion(merchant_id=top, source="llm", model="t", kind="retention", why="x" * 20, next_action="Call the client",
                                 priority=70, generated_at=datetime.now()))
        s.commit()
    try:
        d = api.get("/api/dashboard").json()
        row = next(c for c in d["clients"] if c["merchant_id"] == top)
        assert d["decisions_source"] == "llm" and row["decision"]["kind"] == "retention" and row["decision"]["next_action"] == "Call the client"
        assert row["decision"]["source"] == "llm" and sum(c["decision"] is not None for c in d["clients"]) == 1
    finally:
        with SessionLocal() as s:
            s.query(m.ClientSuggestion).delete()
            s.commit()
