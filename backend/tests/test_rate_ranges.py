"""Improvement 04: the suggested merchant rate is shown as a range, never as one exact figure.

The range is the model's estimate plus or minus 0.10 points, rounded outward to 0.05. The exact value stays in the database for the
recommendation rule and the audit trail, and does not reach the screen, the language model or the fallback answers. Offline.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app import copilot, guard_rules as R, models as m, rates
from app.db import SessionLocal
from app.main import app
from app.readers import ClientReader, PortfolioReader

api = TestClient(app)

OLD_RATIONALE = ("Estimated Visa interchange cost 0.65% (from this merchant's card mix) + modelled spread 1.02pp = 1.67%, vs current 2.42% "
                 "(margin over interchange 1.77pp). Current rate is 0.75pp above the modelled rate: retention risk, consider a proactive "
                 "reduction to 1.67%. Main spread drivers: facility leverage (+0.17pp), volume volatility (-0.06pp). Spread and rates are illustrative.")


@pytest.fixture(scope="module")
def rows():
    with SessionLocal() as s:
        return PortfolioReader(s).portfolio_rows()


def exact_shown(text, r):
    """True when the client's exact modelled rate appears in `text` as a figure of its own (not as a range edge or the current rate)."""
    e = f"{r['rate_suggested']:.2f}%"
    lo, hi = rates.band(r["rate_suggested"])
    return e in text and e not in (f"{lo:.2f}%", f"{hi:.2f}%", f"{r['rate_current']:.2f}%")


# ── the range ───────────────────────────────────────────────────────────────
def test_the_range_is_the_estimate_plus_or_minus_ten_points_rounded_outward_to_five():
    assert rates.band(1.67) == (1.55, 1.80) and rates.text(1.67) == "1.55%–1.80%"
    assert rates.band(1.90) == (1.80, 2.00) and rates.band(2.35) == (2.25, 2.45)
    for cents in range(100, 301):                       # every rate from 1.00 to 3.00
        s = cents / 100
        low, high = rates.band(s)
        assert low <= s - 0.10 + 1e-9 and high >= s + 0.10 - 1e-9 and low < s < high or low <= s <= high
        assert 0.20 - 1e-9 <= high - low <= 0.25 + 1e-9
        assert round(low / 0.05, 6) == round(low / 0.05) and round(high / 0.05, 6) == round(high / 0.05)


def test_position_of_the_current_rate_against_the_range():
    assert rates.position(2.42, 1.67) == "above" and rates.position(1.40, 1.67) == "below" and rates.position(1.70, 1.67) == "within"


# ── the wording ─────────────────────────────────────────────────────────────
def test_the_rationale_is_rewritten_with_rounded_figures_and_the_range():
    new = rates.rewrite_rationale(OLD_RATIONALE, 2.42, 1.67, True)
    assert "1.55%–1.80%" in new and "about 0.65%" in new and "roughly 1.0 points" in new
    assert "1.67" not in new and "1.02" not in new and "0.75pp" not in new and "0.17" not in new      # no exact modelled figures survive
    assert "above that range" in new and "retention risk" in new
    assert "facility leverage (pushes it up)" in new and "volume volatility (pulls it down)" in new and "illustrative" in new
    assert rates.rewrite_rationale(new, 9.99, 9.99, True) == new                                          # already rewritten: left alone


def test_a_marginal_case_keeps_change_recommended_and_says_the_case_is_marginal():
    new = rates.rewrite_rationale(OLD_RATIONALE.replace("2.42", "1.72"), 1.72, 1.67, True)             # current rate inside the range
    assert "inside that range" in new and "change is recommended but the case is marginal" in new


def test_no_change_recommended_says_within_the_range():
    new = rates.rewrite_rationale(OLD_RATIONALE, 1.70, 1.67, False)
    assert "within that range: no change recommended" in new


def test_text_not_in_the_scripts_format_gets_a_short_explanation_with_no_exact_figure():
    new = rates.rewrite_rationale("Some other wording about 1.67%.", 2.42, 1.67, True)
    assert new.startswith("The model puts this merchant's rate at about 1.55%–1.80%") and "1.67" not in new


def test_flag_and_explanation_wording():
    assert rates.review_text(2.49, 2.14) == "Rate review: current 2.49%, model range 2.00%–2.25%"
    assert rates.rewrite_review("Rate review: 2.49% → 2.14% recommended · High risk segment") == "Rate review: current 2.49%, model range 2.00%–2.25% · High risk segment"
    assert rates.rewrite_review("Volume down 43% vs prior 30 days") == "Volume down 43% vs prior 30 days"
    assert rates.mask_exact("reduce the merchant rate to 1.96% now", 1.96) == "reduce the merchant rate to 1.85%–2.10% now"
    assert rates.mask_exact("reduce to 1.9%", 1.90) == "reduce to 1.80%–2.00%"
    assert rates.mask_exact("2.4% growth and AED 1.96 million", 1.96) == "2.4% growth and AED 1.96 million" and rates.mask_exact(None, 1.96) is None


# ── what the app shows and sends ────────────────────────────────────────────
def test_the_client_api_returns_a_range_and_not_the_exact_rate(rows):
    r = next(x for x in rows if x["rate_change"])
    rate = api.get(f"/api/clients/{r['id']}").json()["rate"]
    assert "suggested_pct" not in rate and (rate["suggested_low_pct"], rate["suggested_high_pct"]) == rates.band(r["rate_suggested"])
    assert rate["band_pp"] == 0.10 and not exact_shown(rate["rationale"], r) and "illustrative" in rate["rationale"]


def test_marginal_recommendations_are_kept(rows):
    marginal = [r for r in rows if r["rate_change"] and rates.position(r["rate_current"], r["rate_suggested"]) == "within"]
    assert marginal, "the data has recommendations whose current rate falls inside the range"
    with SessionLocal() as s:
        signals = {p.merchant_id: [x["text"] for x in p.signals] for p in s.query(m.ClientPriority)}
    for r in marginal:
        assert api.get(f"/api/clients/{r['id']}").json()["rate"]["change_recommended"] is True
        lo, hi = rates.band(r["rate_suggested"])
        assert f"Rate review: current {r['rate_current']:.2f}%, model range {lo:.2f}%–{hi:.2f}%" in signals[r["id"]]       # flag kept, with the range
        assert "case is marginal" in api.get(f"/api/clients/{r['id']}").json()["rate"]["rationale"]


def test_the_attention_flag_shows_the_range_for_every_recommended_client(rows):
    dash = {c["merchant_id"]: c for c in api.get("/api/dashboard?filter=all").json()["clients"]}
    with SessionLocal() as s:
        texts = {p.merchant_id: " ".join(x["text"] for x in p.signals) for p in s.query(m.ClientPriority)}
    for r in rows:
        if r["rate_change"]:
            lo, hi = rates.band(r["rate_suggested"])
            assert f"Rate review: current {r['rate_current']:.2f}%, model range {lo:.2f}%–{hi:.2f}%" in texts[r["id"]]
        assert not re.search(r"Rate review: [\d.]+% → ", dash[r["id"]]["reason"] + texts[r["id"]])


def test_the_exact_rate_never_reaches_the_model_or_the_fallback_answers(rows):
    reader_rows = [r for r in rows if r["rate_change"]]
    with SessionLocal() as s:
        reader = PortfolioReader(s)
        prompt = copilot.portfolio_prompt(reader, [{"role": "user", "text": "Which clients have a recommended rate change?"}])
        assert "suggested_rate_range_pct" in prompt["system"] and "suggested_rate_pct" not in prompt["system"]
        assert not any(exact_shown(prompt["system"], r) for r in reader_rows)
        assert "model range" in copilot.portfolio_data_answer(reader, "Which clients have a rate change?")
        for r in reader_rows[::5]:
            rd = ClientReader(s, r["id"])
            assert not exact_shown(copilot.merchant_context(rd), r) and '"suggested_pct"' not in copilot.merchant_context(rd)
            assert not exact_shown(copilot.merchant_data_answer(rd, "What is the rate recommendation?"), r)
    assert "RANGE" in copilot.SYSTEM_RULES and "never a single suggested figure" in copilot.SYSTEM_RULES


def test_the_suggestion_engine_is_given_the_range_not_the_exact_rate(rows):
    from app import suggest_llm
    r = next(x for x in rows if x["rate_change"])
    with SessionLocal() as s:
        payload = suggest_llm.build_payload(s, r["id"])
    assert payload["rate"]["suggested_rate_range_pct"] == list(rates.band(r["rate_suggested"])) and "suggested_rate_pct" not in payload["rate"]
    assert "never a single figure" in suggest_llm.TASK and not exact_shown(str(payload["rate"]), r)


def test_the_evidence_panel_shows_the_range(rows):
    r = next(x for x in rows if x["rate_change"])
    ev = api.get(f"/api/clients/{r['id']}/evidence").json()
    if ev["suggestion"]:
        lo, hi = rates.band(r["rate_suggested"])
        fact = next(f["value"] for f in ev["facts"] if f["label"] == "Merchant rate")
        assert f"model range {lo:.2f}%–{hi:.2f}%" in fact and not exact_shown(fact, r)


# ── the guardrails still work with ranges ───────────────────────────────────
def test_quoting_a_model_range_for_a_client_with_no_change_recommended_is_caught():
    ctx = R.GroundingContext("portfolio", [R.ClientFacts("MER1", "Acme Trading", "Low", False, False, (), False)], [("MER1", "Acme Trading")], None,
                             "AED 1,400,000. Rates seen: 1.55% and 1.80%.")
    bad = R.check_answer("x", "Acme Trading: the model range is 1.55%–1.80%.", ctx)
    assert [v.rule for v in bad if v.hard] == ["rate_quote"]
    assert not R.check_answer("x", "Acme Trading: no change is recommended.", ctx)


def test_an_answer_quoting_the_range_passes_the_figure_check_and_an_exact_figure_does_not(rows):
    r = next(x for x in rows if x["rate_change"])
    with SessionLocal() as s:
        reader = PortfolioReader(s)
        p = copilot.portfolio_prompt(reader, [{"role": "user", "text": "Which clients have a recommended rate change?"}])
    ctx = copilot._portfolio_grounding(rows, p["facts"] + "\n" + p["kb"])
    lo, hi = rates.band(r["rate_suggested"])
    ok = R.check_answer("x", f"**{r['name']}**: model range {lo:.2f}%–{hi:.2f}%.", ctx)
    assert not [v for v in ok if v.hard and v.rule == "ungrounded_number"]
    exact = f"{r['rate_suggested']:.2f}"
    if f"{exact}%" not in (f"{lo:.2f}%", f"{hi:.2f}%", f"{r['rate_current']:.2f}%"):
        bad = R.check_answer("x", f"**{r['name']}**: the suggested rate is {exact}%.", ctx)
        assert any(v.rule == "ungrounded_number" for v in bad)


# ── text already stored in the database ─────────────────────────────────────
def test_migration_rewrites_old_stored_text_once_and_leaves_numbers_alone():
    with SessionLocal() as s:
        r = s.query(m.Client).filter(m.Client.rate_change_recommended).first()
        mid, sug, cur = r.merchant_id, r.suggested_rate_pct, r.current_rate_pct
        p = s.get(m.ClientPriority, mid)
        before = (p.reason, list(p.signals))
        p.reason = f"Rate review: {cur:.2f}% → {sug:.2f}% recommended · High risk segment"
        p.signals = [dict(code="rate_review", kind="opportunity", points=10.0, text=f"Rate review: {cur:.2f}% → {sug:.2f}% recommended")]
        s.merge(m.ClientSuggestion(merchant_id=mid, source="llm", model="t", kind="retention", product=None, amount_aed=None,
                                   why=f"Reduce the rate to {sug:.2f}% to keep the client.", next_action=f"Offer {sug:.2f}% on renewal.",
                                   priority=50.0, generated_at=__import__("datetime").datetime.now()))
        s.commit()
        first = rates.migrate(s)
        again = rates.migrate(s)
        s.expire_all()
        p, sg, row = s.get(m.ClientPriority, mid), s.get(m.ClientSuggestion, mid), s.get(m.Client, mid)
        lo, hi = rates.band(sug)
        assert first["flags"] >= 1 and first["suggestion_texts"] >= 1 and again == dict(flags=0, suggestion_texts=0)
        assert p.reason.startswith(f"Rate review: current {cur:.2f}%, model range {lo:.2f}%–{hi:.2f}%") and "→" not in p.reason
        assert f"{lo:.2f}%–{hi:.2f}%" in sg.why and f"{lo:.2f}%–{hi:.2f}%" in sg.next_action and f"{sug:.2f}%" not in sg.why + sg.next_action
        assert row.suggested_rate_pct == sug and row.current_rate_pct == cur                           # numeric columns untouched
        p.reason, p.signals = before[0], before[1]
        s.query(m.ClientSuggestion).delete()
        s.commit()
