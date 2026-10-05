import inspect

import pytest
from fastapi.testclient import TestClient

from app import copilot, models as m
from app.db import SessionLocal
from app.main import app
from app.readers import ClientNotFound, ClientReader, PortfolioReader

api = TestClient(app)


def test_ingest_counts(loaded):
    assert loaded["clients_loaded"] == 150 and loaded["pos_rows_loaded"] == 36000
    assert loaded["quarantined"] == 0
    assert loaded["as_of_date"] == "2026-08-03"
    assert loaded["products_held_rows"] == 656 and loaded["ntb_candidate_rows"] == 89
    # ntb_candidate_already_held: the supplied new-to-bank file names Trade Finance for clients that already hold it as 'smartTRADE'
    assert set(loaded["warning_types"]) == {"duplicate_business_name", "limits_not_consistent", "risk_segment_not_monotonic_with_score", "ntb_candidate_already_held",
                                            "suggested_rate_set_when_no_change", "working_capital_below_minimum_facility"}


def test_dormant_clients():
    with SessionLocal() as s:
        dormant = [f for f in s.query(m.ClientFact).all() if f.is_dormant_now]
        assert len(dormant) == 10 and all(f.volume_t30 is not None and 6 <= f.dormant_streak_days <= 24 for f in dormant)


def test_six_complete_months():
    with SessionLocal() as s:
        months = [r.month for r in ClientReader(s, "MER2001").monthly(complete_only=True)][-6:]
        assert months == ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
        assert len(ClientReader(s, "MER2001").detail()["volume_bars"]) == 6


def test_client_reader_is_single_client():
    with SessionLocal() as s:
        r = ClientReader(s, "MER2001")
        assert r.detail()["merchant_id"] == "MER2001"
        assert all(d["date"] for d in r.daily(30))
        # no method accepts another merchant id or lists clients
        for name, fn in inspect.getmembers(ClientReader, inspect.isfunction):
            if name.startswith("__"):
                continue
            assert "merchant_id" not in inspect.signature(fn).parameters, name
        with pytest.raises(ClientNotFound):
            ClientReader(s, "MER9999")


def test_merchant_context_has_no_other_clients():
    with SessionLocal() as s:
        ctx = copilot.merchant_context(ClientReader(s, "MER2001"))
        others = [n for i, n in PortfolioReader(s).directory_names() if i != "MER2001" and n != "Nguyen Training Institute"]
        assert "MER2001" in ctx and not any(f'"{n}"' in ctx for n in others)
        assert not any(f"MER{n}" in ctx for n in range(2002, 2151))


def test_scope_guard_refuses_other_client():
    with SessionLocal() as s:
        reply = copilot.merchant_reply(ClientReader(s, "MER2001"), PortfolioReader(s).directory_names(),
                                       [{"role": "user", "text": "How is Curtis Mart doing?"}])
        assert reply["mode"] == "guard"
        reply = copilot.merchant_reply(ClientReader(s, "MER2001"), PortfolioReader(s).directory_names(),
                                       [{"role": "user", "text": "compare with MER2002"}])
        assert reply["mode"] == "guard"


def test_supplied_fields_flow_through():
    d = api.get("/api/clients/MER2001").json()
    assert d["card_pos"]["card_no"].endswith("7532") and d["card_pos"]["card_type"] == "Visa Signature Business Debit Card"
    assert (d["rate"]["current_pct"], d["rate"]["suggested_pct"]) == (2.42, 1.67) and d["rate"]["change_recommended"] is True
    assert "retention risk" in d["rate"]["rationale"]
    assert set(d["profile"]["existing_products"]) >= {"Current Account", "Merchant Acquiring Services"}
    assert any(x["candidate_product"] == "Payroll / WPS Services" for x in d["ntb_candidates"])
    assert d["lending"]["suggested_working_capital_limit_aed"] == 320000
    r = api.get("/api/clients/MER2005").json()["rate"]
    assert r["change_recommended"] is True and (r["current_pct"], r["suggested_pct"]) == (2.55, 1.77)


def test_pitch_rules():
    with SessionLocal() as s:
        for c, p, f in s.query(m.Client, m.ClientPriority, m.ClientFact).join(m.ClientPriority).join(m.ClientFact).all():
            if p.pitch_kind == "Lending":
                assert c.suggested_working_capital_limit_aed >= 250_000 and not f.is_dormant_now and c.risk_segment != "High"
            if p.pitch_kind == "Cross-sell":
                assert p.pitch_title in {x["candidate_product"] for x in p.ntb}


def test_api_contract():
    assert api.get("/api/data/status").json()["synthetic"] is True
    dash = api.get("/api/dashboard?filter=opp").json()
    assert dash["flagged_count"] == len(dash["clients"]) > 0
    assert api.get("/api/dashboard?q=zzzz-none").json()["clients"] == []
    sug = api.get("/api/suggestions").json()
    assert len(sug) == 10 and all(x["category"] in ("Lending", "Cross-sell") for x in sug)
    tiers = {"Prime": 0, "Strong": 1}
    assert [tiers[x["opportunity_label"]] for x in sug] == sorted(tiers[x["opportunity_label"]] for x in sug)  # best tier first
    assert all(a["amount_aed"] >= b["amount_aed"] for a, b in zip(sug, sug[1:]) if a["opportunity_label"] == b["opportunity_label"])
    only = api.get("/api/suggestions", params={"product": sug[0]["product"]}).json()
    assert only and len(only) <= 10 and {x["product"] for x in only} == {sug[0]["product"]}
    assert sug[0]["product"] in {p["product"] for p in api.get("/api/suggestions/products").json()}
    assert api.get("/api/clients/NOPE").status_code == 404


def test_copilot_data_mode(monkeypatch):
    monkeypatch.setattr("app.config.LLM_API_KEY", "")
    r = api.post("/api/copilot/portfolio", json={"messages": [{"role": "user", "text": "Which clients are flagged?"}]}).json()
    assert r["mode"] == "data" and "flagged" in r["reply"].lower()
    r = api.post("/api/copilot/clients/MER2001", json={"messages": [{"role": "user", "text": "Rate recommendation?"}]}).json()
    assert "rate" in r["reply"].lower() and "%" in r["reply"]


# ── LLM suggestion guardrails (factual validation only; no network) ──────────
from app import catalogue, suggest_llm  # noqa: E402

PAYLOAD = {"products_held": ["Current Account", "Payroll / WPS Services"], "suggested_working_capital_limit_aed": 120_000}


def _raw(**kw):
    base = dict(kind="lending", product="Small Business Loan", amount_aed=120_000, why="Valid reason for the RM here.", next_action="Call", priority=61)
    return {**base, **kw}


def test_validate_accepts_good_decision():
    clean, note = suggest_llm.validate(_raw(), PAYLOAD)
    assert clean and clean["product"] == "Small Business Loan" and clean["amount_aed"] == 120_000


def test_validate_rejects_invented_or_unpitchable_products():
    assert suggest_llm.validate(_raw(product="Gold Super Loan"), PAYLOAD)[0] is None
    assert suggest_llm.validate(_raw(product="Business Loan Against FD"), PAYLOAD)[0] is None
    assert suggest_llm.validate(_raw(kind="cross_sell"), PAYLOAD)[0] is None          # kind must match the catalogue
    assert suggest_llm.validate(_raw(kind="cross_sell", product="Payroll / WPS Services"), PAYLOAD)[0] is None  # already held


def test_validate_amount_rules():
    assert suggest_llm.validate(_raw(amount_aed=900_000), PAYLOAD)[0]["amount_aed"] == 120_000   # clamped to supplied limit
    assert suggest_llm.validate(_raw(product="Commercial Vehicle Loan", amount_aed=500_000), PAYLOAD)[0]["amount_aed"] is None  # unsized
    low = {**PAYLOAD, "suggested_working_capital_limit_aed": 30_000}
    assert suggest_llm.validate(_raw(amount_aed=30_000), low)[0] is None                         # below Small Business Loan minimum
    assert suggest_llm.validate(_raw(product="Working capital facility", amount_aed=120_000), PAYLOAD)[0] is None  # below AED 250k
    assert suggest_llm.validate(_raw(kind="retention", product="Small Business Loan", amount_aed=5), PAYLOAD)[0]["product"] is None


def test_catalogue_names_match_ntb_file():
    assert {"Payroll / WPS Services", "Trade Finance (smartTRADE)"} <= catalogue.PITCHABLE


def test_llm_decisions_drive_suggestions_when_present():
    from datetime import datetime
    with SessionLocal() as s:
        s.add_all([
            m.ClientSuggestion(merchant_id="MER2001", source="llm", model="t", kind="cross_sell", product="Payroll / WPS Services", why="x" * 20, priority=99, generated_at=datetime.now()),
            m.ClientSuggestion(merchant_id="MER2002", source="llm", model="t", kind="retention", why="y" * 20, priority=98, generated_at=datetime.now()),
        ])
        s.commit()
        top = PortfolioReader(s).suggestions(10)
        assert [x["merchant_id"] for x in top] == ["MER2001"] and top[0]["source"] == "llm"
        s.query(m.ClientSuggestion).delete()
        s.commit()
        assert PortfolioReader(s).suggestions(10)[0]["source"] == "rules"


def test_directory_filters():
    opts = api.get("/api/clients/filter-options").json()
    assert opts["balance"]["min"] <= opts["balance"]["max"]
    assert sum(o["count"] for o in opts["segment"]) == sum(o["count"] for o in opts["card_type"]) == len(api.get("/api/clients").json())
    seg, card, prod = opts["segment"][0]["value"], opts["card_type"][0]["value"], opts["product"][0]["value"]
    assert len(api.get("/api/clients", params={"segment": seg}).json()) == opts["segment"][0]["count"]
    assert len(api.get("/api/clients", params={"card_type": card}).json()) == opts["card_type"][0]["count"]
    assert len(api.get("/api/clients", params={"product": prod}).json()) == opts["product"][0]["count"]
    rich = api.get("/api/clients", params={"balance_min": 1_000_000}).json()
    for c in rich:
        assert api.get(f"/api/clients/{c['merchant_id']}").json()["profile"]["balance_aed"] >= 1_000_000
    both = api.get("/api/clients", params={"segment": seg, "card_type": card, "balance_max": 50_000}).json()
    assert len(both) <= opts["segment"][0]["count"]
    assert api.get("/api/clients", params={"balance_min": 10**12}).json() == []
