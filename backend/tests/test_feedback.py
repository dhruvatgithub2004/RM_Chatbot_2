"""Improvement 03: the RM can dig into a suggestion ("Why this?") and rate it useful or not.

Evidence is computed from the client's own data and the checks are re-run on current data. Ratings are saved with a snapshot of what was
suggested, in tables a data reload does not touch. Offline: no model is called.
"""
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import config, feedback, models as m
from app.db import Base, FeedbackBase, SessionLocal
from app.main import app
from app.readers import ClientReader, PortfolioReader

api = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    feedback.ensure_tables()
    with SessionLocal() as s:
        s.query(m.ClientFeedback).delete()
        s.query(m.ClientSuggestion).delete()
        s.commit()
    yield
    with SessionLocal() as s:
        s.query(m.ClientFeedback).delete()
        s.query(m.ClientSuggestion).delete()
        s.commit()


def clients_where(pred):
    with SessionLocal() as s:
        reader = PortfolioReader(s)
        out = []
        for mid, _ in reader.directory_names():
            d = ClientReader(s, mid).detail()
            if pred(d):
                out.append(d)
        return out


def lending_client():
    return next(d for d in clients_where(lambda d: d["pitch"] and d["pitch"]["kind"] == "Lending"))


def decide(mid, kind="lending", product="Working capital facility", amount=300_000.0, why="x" * 20, source="llm", priority=80.0):
    with SessionLocal() as s:
        s.merge(m.ClientSuggestion(merchant_id=mid, source=source, model="test" if source == "llm" else None, kind=kind, product=product,
                                   amount_aed=amount, why=why, next_action="Call the client", priority=priority, generated_at=datetime.now()))
        s.commit()


# ── ratings ─────────────────────────────────────────────────────────────────
def test_ratings_live_in_tables_a_data_reload_does_not_rebuild():
    assert "client_feedback" in FeedbackBase.metadata.tables and "client_feedback" not in Base.metadata.tables


def test_a_rating_is_saved_with_a_snapshot_and_replaced_when_the_rm_rates_again():
    d = lending_client()
    mid, product = d["merchant_id"], d["pitch"]["title"]
    r = api.post(f"/api/clients/{mid}/feedback", json={"verdict": "useful", "reason": "Good fit, they asked about funding"})
    assert r.status_code == 200 and r.json() == {"verdict": "useful", "reason": "Good fit, they asked about funding"}
    with SessionLocal() as s:
        saved = s.query(m.ClientFeedback).one()
    assert (saved.merchant_id, saved.suggestion_key, saved.kind, saved.source, saved.verdict) == (mid, product, "lending", "rules", "useful")
    assert saved.amount_aed == d["pitch"]["amount_aed"]
    api.post(f"/api/clients/{mid}/feedback", json={"verdict": "not_useful", "reason": "Already offered"})
    with SessionLocal() as s:
        rows = s.query(m.ClientFeedback).all()
    assert len(rows) == 1 and rows[0].verdict == "not_useful" and rows[0].reason == "Already offered"


def test_the_rating_comes_back_on_the_suggestions_and_dashboard_rows_and_can_be_cleared():
    d = lending_client()
    mid = d["merchant_id"]
    decide(mid, product=d["pitch"]["title"], amount=d["pitch"]["amount_aed"])
    api.post(f"/api/clients/{mid}/feedback", json={"verdict": "useful"})
    sug = [x for x in api.get("/api/suggestions").json() if x["merchant_id"] == mid]
    dash = next(c for c in api.get("/api/dashboard").json()["clients"] if c["merchant_id"] == mid)
    assert dash["feedback"] == {"verdict": "useful", "reason": None}
    if sug:
        assert sug[0]["feedback"]["verdict"] == "useful"
    assert api.delete(f"/api/clients/{mid}/feedback").json() == {"cleared": True}
    dash = next(c for c in api.get("/api/dashboard").json()["clients"] if c["merchant_id"] == mid)
    assert dash["feedback"] is None and api.delete(f"/api/clients/{mid}/feedback").json() == {"cleared": False}


def test_a_new_suggestion_does_not_inherit_the_rating_of_an_old_one():
    d = lending_client()
    mid = d["merchant_id"]
    decide(mid, product="Working capital facility", amount=300_000.0)
    api.post(f"/api/clients/{mid}/feedback", json={"verdict": "not_useful"})
    decide(mid, kind="cross_sell", product="Payroll / WPS Services", amount=None)           # the engine now suggests something else
    dash = next(c for c in api.get("/api/dashboard").json()["clients"] if c["merchant_id"] == mid)
    assert dash["feedback"] is None
    with SessionLocal() as s:
        assert s.query(m.ClientFeedback).count() == 1                                      # the old rating is kept, not overwritten


def test_there_is_nothing_to_rate_when_a_client_has_no_suggestion():
    d = next(iter(clients_where(lambda d: d["pitch"] is None)))
    r = api.post(f"/api/clients/{d['merchant_id']}/feedback", json={"verdict": "useful"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "nothing_to_rate"
    assert api.get(f"/api/clients/{d['merchant_id']}/evidence").json()["suggestion"] is None


def test_bad_requests_are_refused():
    mid = lending_client()["merchant_id"]
    assert api.post(f"/api/clients/{mid}/feedback", json={"verdict": "maybe"}).status_code == 422
    assert api.post("/api/clients/MER9999/feedback", json={"verdict": "useful"}).status_code == 404
    assert api.get("/api/clients/MER9999/evidence").status_code == 404
    long = api.post(f"/api/clients/{mid}/feedback", json={"verdict": "not_useful", "reason": "r" * 900})
    assert long.status_code == 200 and len(long.json()["reason"]) == feedback.MAX_REASON


def test_ratings_are_audited():
    mid = lending_client()["merchant_id"]
    api.post(f"/api/clients/{mid}/feedback", json={"verdict": "useful"})
    last = json.loads(open(config.AUDIT_LOG_PATH, encoding="utf-8").read().strip().splitlines()[-1])
    assert last["event"] == "feedback" and last["merchant_id"] == mid and last["verdict"] == "useful"


def test_the_summary_counts_by_who_decided_by_product_and_by_reason():
    ds = clients_where(lambda d: d["pitch"] and d["pitch"]["kind"] == "Lending")[:3]
    ids = [d["merchant_id"] for d in ds]
    decide(ids[0], source="llm")
    decide(ids[1], source="llm")
    api.post(f"/api/clients/{ids[0]}/feedback", json={"verdict": "useful"})                              # AI, useful
    api.post(f"/api/clients/{ids[1]}/feedback", json={"verdict": "not_useful", "reason": "Already offered"})   # AI, not useful
    api.post(f"/api/clients/{ids[2]}/feedback", json={"verdict": "useful"})                              # rules, useful
    out = api.get("/api/feedback/summary").json()
    assert out["overall"]["rated"] == 3 and out["overall"]["useful"] == 2 and out["overall"]["useful_share"] == pytest.approx(0.667, abs=0.001)
    assert out["by_source"]["llm"]["rated"] == 2 and out["by_source"]["llm"]["useful"] == 1
    assert out["by_source"]["rules"] == {"useful": 1, "not_useful": 0, "rated": 1, "useful_share": 1.0}
    assert out["not_useful_reasons"] == {"Already offered": 1} and "Working capital facility" in out["by_product"]


def test_an_empty_summary_has_no_share():
    out = api.get("/api/feedback/summary").json()
    assert out["overall"] == {"useful": 0, "not_useful": 0, "rated": 0, "useful_share": None}


# ── the evidence panel ──────────────────────────────────────────────────────
def test_evidence_shows_the_suggestion_the_data_behind_it_and_the_checks():
    d = lending_client()
    ev = api.get(f"/api/clients/{d['merchant_id']}/evidence").json()
    assert ev["suggestion"]["kind"] == "lending" and ev["suggestion"]["source"] == "rules" and ev["suggestion"]["product"] == d["pitch"]["title"]
    assert "Rule-based" in ev["suggestion"]["how_decided"]
    labels = [f["label"] for f in ev["facts"]]
    assert labels[0] == "Supplied working-capital limit" and sum(1 for f in ev["facts"] if f["key"]) == 4        # lending evidence comes first
    assert {"Card volume, last 30 days", "Products already held", "Risk segment"} <= set(labels)
    assert ev["signals"] == [dict(text=x["text"], points=x["points"], kind=x["kind"]) for x in d["priority"]["signals"]]
    assert ev["checks"] and all(c["ok"] for c in ev["checks"])                       # a rule-based lending pitch passes every check
    assert ev["explanation_check"]["unverified"] == [] and ev["track_record"]["same_suggestion"]["rated"] == 0 and ev["feedback"] is None


def test_the_evidence_for_each_kind_leads_with_what_matters_for_it():
    d = lending_client()
    decide(d["merchant_id"], kind="retention", product=None, amount=None)
    first = api.get(f"/api/clients/{d['merchant_id']}/evidence").json()["facts"][0]["label"]
    assert first == "POS terminals"
    decide(d["merchant_id"], kind="cross_sell", product="Payroll / WPS Services", amount=None)
    labels = [f["label"] for f in api.get(f"/api/clients/{d['merchant_id']}/evidence").json()["facts"]]
    assert labels[0] in ("Supplied cross-sell candidates", "Products already held")


def test_a_figure_in_the_ai_explanation_that_is_not_in_the_clients_data_is_listed():
    d = lending_client()
    mid = d["merchant_id"]
    bad = "Offer a facility of AED 9,999,999 because volume is up 77% and terminals have been dormant for 99 days."
    decide(mid, why=bad)
    check = api.get(f"/api/clients/{mid}/evidence").json()["explanation_check"]
    assert set(check["unverified"]) == {"AED 9,999,999", "77%", "99 days"} and "Check before relying" in check["summary"]
    decide(mid, why=f"Average monthly turnover is AED {d['profile']['avg_monthly_turnover_aed']:,.0f} and the supplied limit is "
                    f"AED {d['lending']['suggested_working_capital_limit_aed']:,.0f}.")
    ok = api.get(f"/api/clients/{mid}/evidence").json()["explanation_check"]
    assert ok["unverified"] == [] and "found in the client's data" in ok["summary"]


def test_the_checks_are_re_run_on_current_data_and_catch_problems():
    d = lending_client()
    mid, lim = d["merchant_id"], d["lending"]["suggested_working_capital_limit_aed"]
    held = d["profile"]["existing_products"]
    decide(mid, product="Working capital facility", amount=lim + 50_000)                    # above the supplied limit
    checks = api.get(f"/api/clients/{mid}/evidence").json()["checks"]
    assert any(not c["ok"] and "within the cap" in c["text"] for c in checks)
    if held:
        decide(mid, kind="cross_sell", product="businessONLINE", amount=None)
        again = api.get(f"/api/clients/{mid}/evidence").json()["checks"]
        assert any(c["ok"] == ("businessONLINE" not in held) and "does not already hold" in c["text"] for c in again)
    decide(mid, kind="retention", product=None, amount=None)
    retention = api.get(f"/api/clients/{mid}/evidence").json()["checks"]
    assert retention and retention[0]["ok"] == bool({x["code"] for x in d["priority"]["signals"]} & {"dormant", "decline_30d", "decline_6m"})


def test_lending_to_a_high_risk_or_dormant_client_is_flagged_as_a_caution():
    d = next(iter(clients_where(lambda d: d["profile"]["risk_segment"] == "High")))
    decide(d["merchant_id"], product="Working capital facility", amount=300_000.0)
    checks = api.get(f"/api/clients/{d['merchant_id']}/evidence").json()["checks"]
    risk = next(c for c in checks if "High risk segment" in c["text"])
    assert risk["kind"] == "caution" and risk["ok"] is False


def test_the_track_record_counts_ratings_of_the_same_product_and_decider():
    ds = clients_where(lambda d: d["pitch"] and d["pitch"]["kind"] == "Lending")[:3]
    for d, verdict in zip(ds, ("useful", "useful", "not_useful")):
        decide(d["merchant_id"], source="llm")
        api.post(f"/api/clients/{d['merchant_id']}/feedback", json={"verdict": verdict})
    fourth = next(d for d in clients_where(lambda d: d["pitch"] and d["pitch"]["kind"] == "Lending") if d["merchant_id"] not in {x["merchant_id"] for x in ds})
    decide(fourth["merchant_id"], source="llm")
    record = api.get(f"/api/clients/{fourth['merchant_id']}/evidence").json()["track_record"]
    assert record["same_suggestion"]["rated"] == 3 and record["same_suggestion"]["useful"] == 2 and record["same_source"]["rated"] == 3
