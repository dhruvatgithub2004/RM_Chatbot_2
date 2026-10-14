"""Improvement 08 (step 4): the dashboard's dormant reactivation targets.

Merchants whose POS terminals are inactive now, ranked by their own earlier monthly card volume. Rules choose and rank them; the step is the
AI engine's retention decision where it made one, otherwise rule-based reactivation wording. Offline: no model is called.
"""
import pytest
from fastapi.testclient import TestClient

from app import models as m, segments
from app.db import SessionLocal
from app.main import app
from app.readers import PortfolioReader

api = TestClient(app)


@pytest.fixture(scope="module")
def assigned():
    with SessionLocal() as s:
        return segments.assign(s)


def test_the_dormant_set_is_exactly_the_merchants_with_inactive_terminals_now(assigned):
    with SessionLocal() as s:
        now = {f.merchant_id for f in s.query(m.ClientFact) if f.is_dormant_now}
    assert {mid for mid, sg in assigned.items() if sg["dormant_now"]} == now and now


def test_the_thirty_day_rule_would_be_empty_which_is_why_it_is_not_used(assigned):
    assert max(sg["dormant_days"] for sg in assigned.values() if sg["dormant_now"]) < 30


def test_the_list_is_ranked_by_earlier_monthly_volume_and_nobody_left_out_ranks_higher(assigned):
    with SessionLocal() as s:
        out = PortfolioReader(s).dormant_reactivation()
    items = out["items"]
    assert len(items) == 5 and [i["rank"] for i in items] == [1, 2, 3, 4, 5] and out["inactive"] >= 5
    vols = [i["earlier_monthly_volume_aed"] for i in items]
    assert vols == sorted(vols, reverse=True)
    shown = {i["merchant_id"] for i in items}
    assert all(sg["earlier_monthly_volume_aed"] <= vols[-1] for mid, sg in assigned.items() if sg["dormant_now"] and mid not in shown)


def test_the_card_shows_days_inactive_and_earlier_volume(assigned):
    with SessionLocal() as s:
        items = PortfolioReader(s).dormant_reactivation(limit=20)["items"]
    for i in items:
        sg = assigned[i["merchant_id"]]
        assert i["reasons"][0] == f"POS terminals inactive for {sg['dormant_days']} days"
        assert i["reasons"][1] == f"Earlier monthly card volume of AED {sg['earlier_monthly_volume_aed']:,}"


def test_the_step_is_ai_retention_when_it_exists_otherwise_rule_based_reactivation():
    with SessionLocal() as s:
        items = PortfolioReader(s).dormant_reactivation(limit=20)["items"]
    for i in items:
        a = i["action"]
        if a["source"] == "rules":
            assert a["kind"] == "retention" and a["next_action"].startswith("Reactivate the POS terminals")
        else:
            assert a["kind"] == "retention"


def test_the_endpoint_returns_the_data_behind_each_card():
    r = api.get("/api/dashboard/dormant")
    assert r.status_code == 200
    body = r.json()
    assert body["segment"] == "dormant" and len(body["items"]) == 5 and "30 to 90" in body["definition"]
    need = {"rank", "merchant_id", "name", "city", "industry", "dormant_days", "earlier_monthly_volume_aed", "reasons", "action"}
    assert all(need <= set(i) for i in body["items"])
