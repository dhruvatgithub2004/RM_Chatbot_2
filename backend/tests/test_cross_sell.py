"""Improvement 06 (step 2): the dashboard's cross-sell targets.

A cross-sell target is a merchant that is not a churn risk and does not yet hold a product the bank can offer it: a supplied new-to-bank
candidate it does not already hold, or a cross-sell the AI engine chose. It is ranked by estimated monthly revenue plus any growth in it.
A loan it also qualifies for is a second line. POS growth explains and lifts a merchant, but does not decide who is listed. Offline.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import catalogue, models as m, scoring, segments, suggest_llm
from app.db import SessionLocal
from app.main import app
from app.readers import PortfolioReader

api = TestClient(app)
CROSS_SELL_PRODUCTS = [p.name for p in catalogue.PRODUCTS if p.kind == "cross_sell"]


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


def held_products():
    with SessionLocal() as s:
        out = {}
        for mid, prod in s.query(m.ClientProduct.merchant_id, m.ClientProduct.product):
            out.setdefault(mid, []).append(prod)
        return out


def eligible(assigned):
    """The merchants that should be listed, worked out independently of the reader."""
    held, out = held_products(), {}
    with SessionLocal() as s:
        for p in s.query(m.ClientPriority):
            free = [x["candidate_product"] for x in (p.ntb or []) if not catalogue.holds(held.get(p.merchant_id, []), x["candidate_product"])]
            if free and "churn_risk" not in assigned[p.merchant_id]["codes"]:
                out[p.merchant_id] = free
    return out


# ── the growth-ready signal (it explains and lifts; it does not select) ─────
def test_the_growth_ready_rule_matches_each_clients_own_figures_and_never_overlaps_churn(assigned):
    with SessionLocal() as s:
        facts = {f.merchant_id: f for f in s.query(m.ClientFact)}
    for mid, sg in assigned.items():
        f = facts[mid]
        growing = f.volume_change_t30_vs_p30 is not None and f.volume_change_t30_vs_p30 >= scoring.GROWTH_T30
        near_limit = f.monthly_limit_utilisation_t30 is not None and f.monthly_limit_utilisation_t30 >= scoring.LIMIT_PRESSURE_MONTHLY
        churn = "churn_risk" in sg["codes"]
        assert ("growth_ready" in sg["codes"]) == ((growing or near_limit) and not churn), mid
        assert len(sg["growth_reasons"]) == (0 if churn else sum([growing, near_limit]))


# ── who is listed ───────────────────────────────────────────────────────────
def test_every_merchant_with_a_product_it_lacks_is_a_candidate_and_churn_risks_are_not(assigned):
    want = eligible(assigned)
    with SessionLocal() as s:
        out = PortfolioReader(s).cross_sell_targets(limit=500)
    assert {i["merchant_id"] for i in out["items"]} == set(want) and out["candidates"] == len(want)
    assert not any("churn_risk" in assigned[mid]["codes"] for mid in want)


def test_the_selection_is_not_driven_by_pos_growth(assigned):
    with SessionLocal() as s:
        items = PortfolioReader(s).cross_sell_targets(limit=500)["items"]
    plain = [i for i in items if not i["growth_reasons"]]
    assert plain, "merchants with no POS growth signal are listed"
    assert len(plain) > len(items) - len(plain)                       # most candidates are not growth-ready
    assert any(not i["growth_reasons"] for i in items[:5])           # growth lifts a merchant, but the top five are not all POS-growth cases


def test_a_product_the_merchant_already_holds_is_never_offered(assigned):
    held = held_products()
    with SessionLocal() as s:
        items = PortfolioReader(s).cross_sell_targets(limit=500)["items"]
        already = [(p.merchant_id, x["candidate_product"]) for p in s.query(m.ClientPriority) for x in (p.ntb or [])
                   if catalogue.holds(held.get(p.merchant_id, []), x["candidate_product"])]
    assert already, "the supplied candidates include products the client already holds (a known data warning)"
    offered = {(i["merchant_id"], i["offer"]["product"]) for i in items}
    assert not (set(already) & offered)
    assert all(not catalogue.holds(held.get(i["merchant_id"], []), i["offer"]["product"]) for i in items)


# ── the ranking ─────────────────────────────────────────────────────────────
def test_the_list_is_five_merchants_ranked_by_revenue_plus_growth(assigned):
    with SessionLocal() as s:
        out = PortfolioReader(s).cross_sell_targets()
        everyone = PortfolioReader(s).cross_sell_targets(limit=500)["items"]
    items = out["items"]
    assert len(items) == 5 and [i["rank"] for i in items] == [1, 2, 3, 4, 5]
    score = lambda mid: assigned[mid]["monthly_revenue_aed"] + max(0, assigned[mid]["revenue_change_vs_prior_30d_aed"])
    scores = [score(i["merchant_id"]) for i in items]
    assert scores == sorted(scores, reverse=True)
    chosen = {i["merchant_id"] for i in items}
    assert max(score(i["merchant_id"]) for i in everyone if i["merchant_id"] not in chosen) <= min(scores)
    assert 5 <= out["candidates"] and out["growth_ready"] <= out["candidates"] and out["also_lending"] <= out["candidates"]


def test_the_card_leads_with_the_product_gap_then_any_growth_figures(assigned):
    with SessionLocal() as s:
        items = PortfolioReader(s).cross_sell_targets(limit=500)["items"]
    for i in items:
        assert i["reasons"][0] == f"No {i['offer']['product']} on file" and i["reasons"][1:] == i["growth_reasons"]
        assert i["offer"]["kind"] == "Cross-sell" and i["offer"]["product"] in CROSS_SELL_PRODUCTS
    assert any(i["growth_reasons"] for i in items), "some candidates are also growing or near their POS limit"


# ── the loan is the second line ─────────────────────────────────────────────
def test_a_loan_the_merchant_also_qualifies_for_is_a_second_line_never_the_headline():
    with SessionLocal() as s:
        reader = PortfolioReader(s)
        items = reader.cross_sell_targets(limit=500)["items"]
        loans = {p["merchant_id"]: p for p in reader.pitch_list() if p["category"] == "Lending"}
    with_loan = [i for i in items if i["also_lending"]]
    assert with_loan and len(with_loan) < len(items) + 1
    for i in items:
        loan = loans.get(i["merchant_id"])
        assert (i["also_lending"] is None) == (loan is None)
        if loan:
            assert i["also_lending"] == dict(product=loan["product"], amount_aed=loan["amount_aed"])
        assert i["offer"]["product"] != "Working capital facility"


# ── AI versus rules ─────────────────────────────────────────────────────────
def test_the_offer_is_the_first_supplied_candidate_unless_the_ai_engine_decided(assigned):
    want = eligible(assigned)
    with SessionLocal() as s:
        first = PortfolioReader(s).cross_sell_targets()["items"][0]
    o = first["offer"]
    assert o["source"] == "rules" and o["model"] is None and o["product"] == want[first["merchant_id"]][0]


def test_the_ai_engines_cross_sell_decision_is_used_when_it_exists():
    held = held_products()
    with SessionLocal() as s:
        first = PortfolioReader(s).cross_sell_targets()["items"][0]
        mid = first["merchant_id"]
        product = next(p for p in CROSS_SELL_PRODUCTS if not catalogue.holds(held.get(mid, []), p) and p != first["offer"]["product"])
        s.add(m.ClientSuggestion(merchant_id=mid, source="llm", model="qwen-test", kind="cross_sell", product=product, amount_aed=None,
                                 why="Written by the AI engine.", next_action="Offer it.", priority=90.0, generated_at=datetime.now()))
        s.commit()
        mine = next(i for i in PortfolioReader(s).cross_sell_targets(limit=500)["items"] if i["merchant_id"] == mid)
    assert (mine["offer"]["source"], mine["offer"]["model"], mine["offer"]["product"], mine["offer"]["why"]) == (
        "llm", "qwen-test", product, "Written by the AI engine.")
    assert mine["reasons"][0] == f"No {product} on file"


def test_a_lending_or_no_action_decision_does_not_remove_the_merchant():
    with SessionLocal() as s:
        first = PortfolioReader(s).cross_sell_targets()["items"][0]["merchant_id"]
        s.add(m.ClientSuggestion(merchant_id=first, source="llm", model="t", kind="none", why="Nothing to offer.", priority=10.0, generated_at=datetime.now()))
        s.commit()
        after = {i["merchant_id"] for i in PortfolioReader(s).cross_sell_targets(limit=500)["items"]}
    assert first in after


# ── the endpoint and the suggestion engine ──────────────────────────────────
def test_the_endpoint_returns_the_list_with_the_data_behind_each_card():
    r = api.get("/api/dashboard/cross-sell")
    assert r.status_code == 200
    body = r.json()
    assert body["segment"] == "cross_sell" and len(body["items"]) == 5 and "second line" in body["definition"]
    assert all({"rank", "merchant_id", "name", "city", "industry", "value_tier", "reasons", "growth_reasons", "offer", "also_lending"} <= set(i)
               and {"kind", "product", "why", "source", "model"} <= set(i["offer"]) for i in body["items"])
    assert api.get("/api/dashboard/act-now").status_code == 200              # step 1 is unchanged


def test_the_suggestion_engine_is_told_about_the_growth_ready_segment(assigned):
    assert '"growth_ready"' in suggest_llm.TASK and "not a reason for retention" in suggest_llm.TASK
    mid = next(m_ for m_, v in assigned.items() if "growth_ready" in v["codes"])
    with SessionLocal() as s:
        assert suggest_llm.build_payload(s, mid)["segments"]["codes"][0] == "growth_ready"
