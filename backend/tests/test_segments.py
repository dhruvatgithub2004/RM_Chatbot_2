"""Improvement 05 (step 1): the dashboard's "Act now" list of high-value churn risks.

Rules choose and rank the merchants from the data; the suggested step is the AI engine's retention decision where it made one, otherwise
the rule-based wording. Offline: no model is called.
"""
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


def facts(mid):
    with SessionLocal() as s:
        f = s.get(m.ClientFact, mid)
        return dict(chg=f.volume_change_t30_vs_p30, dormant=bool(f.is_dormant_now), days=f.dormant_streak_days, v30=f.volume_t30)


# ── the facts every client gets ─────────────────────────────────────────────
def test_every_client_has_the_fields_the_suggestion_engine_reads(assigned):
    need = {"codes", "monthly_revenue_aed", "value_tier", "turnover_rank", "clients_in_portfolio", "portfolio_share_pct",
            "revenue_change_vs_prior_30d_aed", "volume_change_vs_prior_30d_pct", "dormant_days"}
    assert len(assigned) == 150 and all(need <= set(v) for v in assigned.values())
    assert segments.LABELS["churn_risk"] == "High-value churn risk"


def test_value_tiers_are_thirds_of_the_portfolio_by_estimated_revenue(assigned):
    tiers = [v["value_tier"] for v in assigned.values()]
    assert (tiers.count("High"), tiers.count("Medium"), tiers.count("Low")) == (50, 50, 50)
    rev = lambda t: [v["monthly_revenue_aed"] for v in assigned.values() if v["value_tier"] == t]
    assert min(rev("High")) >= max(rev("Medium")) >= min(rev("Medium")) >= max(rev("Low"))
    assert sorted(v["turnover_rank"] for v in assigned.values()) == list(range(1, 151))


# ── who is a churn risk ─────────────────────────────────────────────────────
def test_the_churn_risk_rule_matches_the_clients_own_figures(assigned):
    for mid, sg in assigned.items():
        f = facts(mid)
        sudden = f["chg"] is not None and f["chg"] <= segments.VOLUME_DROP
        below = sg["volume_vs_baseline_pct"] is not None and sg["volume_vs_baseline_pct"] <= segments.BASELINE_DROP * 100 and (f["chg"] is None or f["chg"] <= 0)
        assert ("churn_risk" in sg["codes"]) == (f["dormant"] or sudden or below), mid
        assert len(sg["reasons"]) == sum([f["dormant"], sudden, below])


def test_a_merchant_already_recovering_is_not_an_act_now_case(assigned):
    recovering = [mid for mid, sg in assigned.items() if sg["volume_vs_baseline_pct"] is not None and sg["volume_vs_baseline_pct"] <= -15
                  and facts(mid)["chg"] is not None and facts(mid)["chg"] > 0 and not facts(mid)["dormant"]]
    assert recovering, "the data has merchants below their baseline but rising against the prior 30 days"
    assert all("churn_risk" not in assigned[mid]["codes"] for mid in recovering)      # it may be growth-ready (step 2), but it is not a churn risk


def test_the_baseline_is_the_earlier_complete_months_and_leaves_out_the_latest_one(assigned):
    mid = next(iter(assigned))
    with SessionLocal() as s:
        vols = [r.volume_aed for r in s.query(m.ClientMonthlyVolume).filter_by(merchant_id=mid, is_complete=True).order_by(m.ClientMonthlyVolume.month)]
        f, c = s.get(m.ClientFact, mid), s.get(m.Client, mid)
    history = vols[:-1][-segments.BASELINE_MONTHS:]
    baseline = sum(history) / len(history)
    sg = assigned[mid]
    assert sg["baseline_months"] == len(history) == 6
    assert sg["volume_vs_baseline_pct"] == round((f.volume_t30 / baseline - 1) * 100, 1)
    assert sg["revenue_gap_vs_baseline_aed"] == round((baseline - f.volume_t30) * c.current_rate_pct / 100)


def test_the_reasons_name_the_figures_that_triggered_them(assigned):
    dormant = next(sg for mid, sg in assigned.items() if facts(mid)["dormant"])
    text = " ".join(dormant["reasons"])
    assert f"inactive for {dormant['dormant_days']} days" in text and "against the prior 30 days" in text


# ── the Act now list ────────────────────────────────────────────────────────
def test_the_act_now_list_is_five_high_value_churn_risks_ranked_by_revenue_lost(assigned):
    with SessionLocal() as s:
        out = PortfolioReader(s).act_now()
    items = out["items"]
    assert len(items) == 5 and [i["rank"] for i in items] == [1, 2, 3, 4, 5]
    gaps = [i["revenue_gap_vs_baseline_aed"] for i in items]
    assert gaps == sorted(gaps, reverse=True)
    assert all(i["value_tier"] in ("High", "Medium") and "churn_risk" in assigned[i["merchant_id"]]["codes"] and i["reasons"] for i in items)
    assert out["at_risk"] == sum("churn_risk" in v["codes"] for v in assigned.values())
    assert 5 <= out["high_value_at_risk"] <= out["at_risk"] and "top two thirds" in out["definition"]
    chosen = {i["merchant_id"] for i in items}
    worse = [v["revenue_gap_vs_baseline_aed"] for mid, v in assigned.items()
             if "churn_risk" in v["codes"] and v["value_tier"] != "Low" and mid not in chosen]
    assert max(worse) <= min(gaps)                 # nobody left out lost more revenue than someone included


def test_a_low_value_churn_risk_is_never_listed(assigned):
    low = {mid for mid, v in assigned.items() if "churn_risk" in v["codes"] and v["value_tier"] == "Low"}
    assert low, "the data has low-value merchants at risk"
    with SessionLocal() as s:
        listed = {i["merchant_id"] for i in PortfolioReader(s).act_now(limit=50)["items"]}
    assert not (low & listed)


def test_without_an_ai_decision_the_step_is_the_rule_based_wording():
    with SessionLocal() as s:
        first = PortfolioReader(s).act_now()["items"][0]
    a = first["action"]
    assert a["source"] == "rules" and a["model"] is None and a["kind"] == "retention"
    assert "Volume is down" in a["why"] or "dormant" in a["why"] or "fallen" in a["why"]
    assert a["next_action"] == "Call the client to understand the cause before any pricing action" or "Reactivate" in a["next_action"]


def test_the_ai_engines_retention_decision_is_used_when_it_exists_and_other_decisions_are_not():
    with SessionLocal() as s:
        items = PortfolioReader(s).act_now()["items"]
        s.add(m.ClientSuggestion(merchant_id=items[0]["merchant_id"], source="llm", model="qwen-test", kind="retention", why="Written by the AI engine.",
                                 next_action="Visit the shop this week.", priority=90.0, generated_at=datetime.now()))
        s.add(m.ClientSuggestion(merchant_id=items[1]["merchant_id"], source="llm", model="qwen-test", kind="lending", product="Working capital facility",
                                 amount_aed=300000.0, why="A lending pitch.", next_action="Offer it.", priority=90.0, generated_at=datetime.now()))
        s.commit()
        after = PortfolioReader(s).act_now()["items"]
    ai, other = after[0]["action"], after[1]["action"]
    assert (ai["source"], ai["model"], ai["why"], ai["next_action"]) == ("llm", "qwen-test", "Written by the AI engine.", "Visit the shop this week.")
    assert other["source"] == "rules" and other["kind"] == "retention" and "lending pitch" not in other["why"]


def test_the_endpoint_returns_the_list_with_the_data_behind_each_card():
    r = api.get("/api/dashboard/act-now")
    assert r.status_code == 200
    body = r.json()
    assert body["segment"] == "churn_risk" and len(body["items"]) == 5
    need = {"rank", "merchant_id", "name", "city", "industry", "value_tier", "monthly_revenue_aed", "revenue_gap_vs_baseline_aed",
            "revenue_change_vs_prior_30d_aed", "volume_change_vs_prior_30d_pct", "volume_vs_baseline_pct", "dormant_days", "reasons", "action"}
    assert all(need <= set(i) for i in body["items"])
    assert api.get("/api/dashboard?filter=opp").status_code == 200          # the existing dashboard endpoint is unchanged


# ── the suggestion engine can use the segments ──────────────────────────────
def test_the_suggestion_engine_is_given_the_segment_and_falls_back_to_a_retention_call(assigned):
    mid = next(mid for mid, v in assigned.items() if "churn_risk" in v["codes"] and v["value_tier"] != "Low")
    with SessionLocal() as s:
        payload = suggest_llm.build_payload(s, mid)
        assert payload["segments"]["codes"][0] == "churn_risk" and payload["segments"]["value_tier"] in ("High", "Medium")
        row = suggest_llm._rules_row(s, mid, "test", datetime.now(), assigned[mid])
        p = s.get(m.ClientPriority, mid)
    if p.pitch_kind != "Lending":                    # a client with a lending pitch keeps it; the others get a retention call
        assert row["kind"] == "retention" and "High-value churn risk" in row["note"]
