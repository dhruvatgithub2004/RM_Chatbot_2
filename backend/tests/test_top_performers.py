"""Improvement 07 (step 3): the dashboard's top performers.

The top 10% of merchants by card volume over the last 30 days. Card volume is used, not average monthly turnover, because the supplied
turnover has ties. Rules choose and rank them; the step is the AI engine's "engage" decision where it made one, otherwise rule-based
wording, and a top performer that is also a churn risk gets the retention step. Offline: no model is called.
"""
import math
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import models as m, segments, suggest_llm
from app.db import SessionLocal
from app.main import app
from app.readers import PortfolioReader

api = TestClient(app)


@pytest.fixture(autouse=True)
def clean_decisions():
    with SessionLocal() as s:
        s.query(m.ClientSuggestion).delete()
        s.commit()
    yield
    with SessionLocal() as s:
        s.query(m.ClientSuggestion).delete()
        s.commit()


@pytest.fixture(scope="module")
def assigned():
    with SessionLocal() as s:
        return segments.assign(s)


def volumes():
    with SessionLocal() as s:
        return {f.merchant_id: f.volume_t30 or 0.0 for f in s.query(m.ClientFact)}


# ── who is a top performer ──────────────────────────────────────────────────
def test_the_top_performers_are_the_top_ten_percent_by_card_volume(assigned):
    vol = volumes()
    ranked = sorted(vol, key=lambda k: (-vol[k], k))
    tops = {mid for mid, sg in assigned.items() if "top_performer" in sg["codes"]}
    assert tops == set(ranked[:math.ceil(0.10 * len(vol))]) and len(tops) == 15
    assert [assigned[mid]["volume_rank"] for mid in ranked] == list(range(1, 151))


def test_the_shares_are_shares_of_the_portfolios_and_of_the_citys_card_volume(assigned):
    vol = volumes()
    with SessionLocal() as s:
        city = {c.merchant_id: c.city for c in s.query(m.Client)}
    total = sum(vol.values())
    for mid in list(assigned)[::10]:
        city_total = sum(v for k, v in vol.items() if city[k] == city[mid])
        assert assigned[mid]["volume_share_pct"] == round(100 * vol[mid] / total, 1)
        assert assigned[mid]["city_volume_share_pct"] == round(100 * vol[mid] / city_total, 1) and assigned[mid]["city"] == city[mid]
    assert round(sum(v["volume_share_pct"] for v in assigned.values())) == 100


def test_the_ranking_does_not_use_the_tied_turnover(assigned):
    with SessionLocal() as s:
        turnover = sorted((c.avg_monthly_turnover_aed for c in s.query(m.Client)), reverse=True)
    assert turnover[0] == turnover[8], "the supplied turnover has ties at the top, which is why card volume is used"
    ranks = [v["volume_rank"] for v in assigned.values()]
    assert len(set(ranks)) == len(ranks)                                   # no ties in the ranking that is used


def test_a_top_performer_can_also_carry_another_segment_without_losing_it(assigned):
    both = [sg for sg in assigned.values() if "top_performer" in sg["codes"] and ("churn_risk" in sg["codes"] or "growth_ready" in sg["codes"])]
    assert both and all(len(sg["codes"]) == 2 for sg in both)
    assert not any("churn_risk" in sg["codes"] and "growth_ready" in sg["codes"] for sg in assigned.values())


# ── the list ────────────────────────────────────────────────────────────────
def test_the_list_is_the_five_largest_top_performers_by_card_volume(assigned):
    with SessionLocal() as s:
        out = PortfolioReader(s).top_performers()
    items = out["items"]
    assert len(items) == 5 and [i["rank"] for i in items] == [1, 2, 3, 4, 5] and [i["volume_rank"] for i in items] == [1, 2, 3, 4, 5]
    assert all("top_performer" in assigned[i["merchant_id"]]["codes"] for i in items)
    assert out["top_performers"] == 15
    assert out["share_of_volume_pct"] == round(sum(v["volume_share_pct"] for v in assigned.values() if "top_performer" in v["codes"]), 1)
    assert out["share_of_volume_pct"] > 50, "the top performers hold the bulk of the volume"


def test_the_card_shows_the_rank_the_shares_and_the_trend(assigned):
    with SessionLocal() as s:
        items = PortfolioReader(s).top_performers(limit=15)["items"]
    for i in items:
        sg, r = assigned[i["merchant_id"]], i["reasons"]
        assert r[0] == f"Ranked {sg['volume_rank']} of 150 merchants by card volume"
        assert r[1] == f"{sg['volume_share_pct']}% of the portfolio's card volume"
        assert r[2] == f"{sg['city_volume_share_pct']}% of {i['city']}'s card volume"
        chg = sg["volume_change_vs_prior_30d_pct"]
        assert any("against the prior 30 days" in x for x in r) == (chg is not None)
        if abs(chg) >= 1:
            assert f"Card volume {'up' if chg > 0 else 'down'} {abs(chg):.0f}% against the prior 30 days" in r


# ── the step ────────────────────────────────────────────────────────────────
def test_without_an_ai_decision_the_step_is_the_rule_based_check_in():
    with SessionLocal() as s:
        first = next(i for i in PortfolioReader(s).top_performers(limit=15)["items"] if not i["churn_risk"])
    a = first["action"]
    assert (a["kind"], a["source"], a["model"]) == ("engage", "rules", None) and a["next_action"] == "Schedule a relationship check-in and review their needs"
    assert "by card volume over the last 30 days" in a["why"] and f"% of {first['city']}'s" in a["why"]


def test_the_ai_engines_engage_decision_is_used_and_other_kinds_are_not():
    with SessionLocal() as s:
        items = [i for i in PortfolioReader(s).top_performers(limit=15)["items"] if not i["churn_risk"]]
        s.add(m.ClientSuggestion(merchant_id=items[0]["merchant_id"], source="llm", model="qwen-test", kind="engage", why="Written by the AI engine.",
                                 next_action="Visit the owner this month.", priority=90.0, generated_at=datetime.now()))
        s.add(m.ClientSuggestion(merchant_id=items[1]["merchant_id"], source="llm", model="qwen-test", kind="lending", product="Working capital facility",
                                 amount_aed=300000.0, why="A loan.", next_action="Offer it.", priority=90.0, generated_at=datetime.now()))
        s.commit()
        after = {i["merchant_id"]: i for i in PortfolioReader(s).top_performers(limit=15)["items"]}
    ai, other = after[items[0]["merchant_id"]]["action"], after[items[1]["merchant_id"]]["action"]
    assert (ai["source"], ai["model"], ai["why"], ai["next_action"]) == ("llm", "qwen-test", "Written by the AI engine.", "Visit the owner this month.")
    assert other["source"] == "rules" and other["kind"] == "engage"


def test_a_top_performer_that_is_a_churn_risk_gets_retention_first():
    with SessionLocal() as s:
        items = PortfolioReader(s).top_performers(limit=15)["items"]
    risky = [i for i in items if i["churn_risk"]]
    assert risky, "some top performers are also churn risks"
    for i in risky:
        assert i["action"]["kind"] == "retention"
        assert "Call the client" in i["action"]["next_action"] or "Reactivate" in i["action"]["next_action"]
        assert i["reasons"][-1] == "Also a churn risk, so retention comes first"
    assert all(not i["churn_risk"] and i["action"]["kind"] == "engage" for i in items if i not in risky)


# ── the endpoint and the suggestion engine ──────────────────────────────────
def test_the_endpoint_returns_the_list_with_the_data_behind_each_card():
    r = api.get("/api/dashboard/top-performers")
    assert r.status_code == 200
    body = r.json()
    assert body["segment"] == "top_performer" and len(body["items"]) == 5 and "last spoke" in body["definition"]
    need = {"rank", "merchant_id", "name", "city", "industry", "volume_rank", "volume_share_pct", "city_volume_share_pct", "churn_risk", "reasons", "action"}
    assert all(need <= set(i) for i in body["items"])
    assert api.get("/api/dashboard/act-now").status_code == 200 and api.get("/api/dashboard/cross-sell").status_code == 200


def test_the_suggestion_engine_is_briefed_in_card_volume_and_can_fall_back_to_engage(assigned):
    assert "volume_rank" in suggest_llm.TASK and "city_volume_share_pct" in suggest_llm.TASK
    mid = next(mid for mid, v in assigned.items() if "top_performer" in v["codes"] and "churn_risk" not in v["codes"])
    with SessionLocal() as s:
        payload = suggest_llm.build_payload(s, mid)
        row = suggest_llm._rules_row(s, mid, "test", datetime.now(), assigned[mid])
        p = s.get(m.ClientPriority, mid)
    assert {"volume_rank", "volume_share_pct", "city_volume_share_pct"} <= set(payload["segments"]) and "top_performer" in payload["segments"]["codes"]
    if p.pitch_kind is None:                       # no pitch: a top performer gets a relationship check-in
        assert row["kind"] == "engage" and "Top performer" in row["note"]
