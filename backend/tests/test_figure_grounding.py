"""Improvement 02: every figure in a model answer must be in the data the model was given.

Before this, only AED amounts of 1,000 or more were checked, and a miss was only logged. Percentages, day counts, small amounts and
client counts passed unchecked. Now an AED amount (100 or more), a percentage, a day or month count, or a client count that is not in
the supplied data blocks the answer, and the RM gets the data-only answer instead. Offline: the model is never called.
"""
import pytest

from app import copilot, guard_rules as R
from app.db import SessionLocal
from app.readers import ClientReader, PortfolioReader

MERCHANT_QUESTIONS = ["Summarize this client", "Any risk flags?", "What's the best cross-sell?", "Rate recommendation?",
                      "What is the volume trend?", "What is the card mix?", "Any lending opportunity?"]
PORTFOLIO_QUESTIONS = ["Which clients are flagged?", "Portfolio summary", "Which clients are dormant?", "Which clients are high risk?",
                       "Which clients have a recommended rate change?", "Lending opportunities?", "Cross-sell candidates?",
                       "Which clients hold smartTRADE?", "Which clients are dormant and high risk?"]


@pytest.fixture(scope="module")
def book():
    with SessionLocal() as s:
        r = PortfolioReader(s)
        rows = r.portfolio_rows()
        prompt = copilot.portfolio_prompt(r, [{"role": "user", "text": "Which clients are flagged?"}])
        yield dict(reader=r, rows=rows, ctx=copilot._portfolio_grounding(rows, prompt["facts"]),
                   dormant=next(x for x in rows if x["dormant_days"]),
                   active=next(x for x in rows if not x["dormant_days"] and x["risk"] == "Low" and x["rate_current"]))


def verdict(ctx, answer, question="x"):
    """block when the figure rule (ungrounded_number) objects. Other rules are tested elsewhere and are ignored here."""
    v = R.check_answer(question, answer, ctx)
    return "block" if any(x.hard and x.rule == "ungrounded_number" for x in v) else "pass"


# ── wrong figures are blocked ───────────────────────────────────────────────
def test_wrong_percentages_are_blocked(book):
    ctx, a, d = book["ctx"], book["active"], book["dormant"]
    assert verdict(ctx, f"**{a['name']}** has volume up 85% vs prior 30 days.") == "block"
    assert verdict(ctx, f"**{a['name']}** current rate is 1.50%.") == "block"
    assert verdict(ctx, f"**{d['name']}** volume is down 91% vs prior 30 days.") == "block"


def test_wrong_day_counts_are_blocked(book):
    ctx, d = book["ctx"], book["dormant"]
    assert verdict(ctx, f"**{d['name']}** has been dormant for 99 days.") == "block"
    assert verdict(ctx, f"**{d['name']}** has been dormant for 10 days.") == ("pass" if d["dormant_days"] == 10 else "block")   # 10 is a client COUNT elsewhere


def test_wrong_aed_amounts_are_blocked_including_small_ones(book):
    ctx, a = book["ctx"], book["active"]
    assert verdict(ctx, f"**{a['name']}** has a balance of AED 7,777,777.") == "block"
    assert verdict(ctx, f"**{a['name']}** pays a monthly fee of AED 450.") == "block"        # below the old AED 1,000 threshold
    assert verdict(ctx, "A limit of AED 1,400,00 is suggested.") == "block"                  # a malformed amount found in a real answer


def test_wrong_client_counts_are_blocked(book):
    ctx = book["ctx"]
    assert verdict(ctx, "99 of 150 clients are flagged for attention.") == "block"
    assert verdict(ctx, "12 clients have dormant terminals.") == "block"


def test_a_blocked_figure_is_a_hard_violation_named_ungrounded_number(book):
    v = R.check_answer("x", "99 of 150 clients are flagged for attention.", book["ctx"])
    assert [x.rule for x in v] == ["ungrounded_number"] and all(x.hard for x in v)


# ── correct figures pass, including rounded ones ────────────────────────────
def test_correct_figures_pass(book):
    ctx, a, d, rows = book["ctx"], book["active"], book["dormant"], book["rows"]
    pct = round(abs(d["vol_change"]) * 100)
    assert verdict(ctx, f"- **{d['name']}**: dormant for {d['dormant_days']} days, volume down {pct}% vs prior 30 days") == "pass"
    flagged = sum(1 for x in rows if x["flagged"])
    assert verdict(ctx, f"{flagged} of {len(rows)} clients are flagged for attention.") == "pass"
    assert verdict(ctx, f"**{a['name']}**: current rate {a['rate_current']:.2f}%.") == "pass"
    assert verdict(ctx, f"**{a['name']}** holds AED {a['balance']:,.0f}.") == "pass"
    assert verdict(ctx, f"**{a['name']}** holds about AED {round(a['balance'] / 1000)}k.") == "pass"          # rounded to the nearest thousand
    assert verdict(ctx, "About 19% of clients are flagged.") == "pass"                                      # share given in the header


def test_rounding_is_allowed_only_to_the_precision_the_answer_states(book):
    total = sum(x["vol_t30"] or 0 for x in book["rows"]) / 1e6
    assert verdict(book["ctx"], f"Total volume in the last 30 days was AED {total:.1f}M.") == "pass"
    assert verdict(book["ctx"], f"Total volume in the last 30 days was AED {total:.0f} million.") == "pass"
    assert verdict(book["ctx"], f"Total volume in the last 30 days was AED {total + 1:.1f}M.") == "block"        # one million out
    assert verdict(book["ctx"], f"Total volume in the last 30 days was AED {total + 0.3:.1f}M.") == "block"      # 0.3 million out


def test_the_comparison_windows_and_the_rms_own_numbers_pass(book):
    assert verdict(book["ctx"], "Volume over the last 30 days compared with the prior 60 days.") == "pass"
    assert verdict(book["ctx"], "A loan of AED 50,000 is within the published range.", question="Can a client take AED 50,000?") == "pass"
    assert verdict(book["ctx"], "A loan of AED 50,000 is within the published range.", question="Can a client take a loan?") == "block"


def test_a_percentage_cannot_pass_on_a_day_count_or_a_client_count(book):
    ctx, d = book["ctx"], book["dormant"]
    clash = next(x for x in (11, 29, 48, 91, 110) if x != round(abs(d["vol_change"]) * 100))         # counts present in the header
    assert verdict(ctx, f"**{d['name']}** volume is down {clash}% vs prior 30 days.") == "block"


# ── the single-client chat ──────────────────────────────────────────────────
def test_client_chat_figures_are_checked_against_that_clients_data(book):
    r = book["reader"]
    mid = book["dormant"]["id"]
    with SessionLocal() as s:
        rd = ClientReader(s, mid)
        d = rd.detail()
        p = copilot.merchant_prompt(rd, [{"role": "user", "text": "Summarize this client"}])
    me = R.ClientFacts(mid, d["name"], d["profile"]["risk_segment"], True, bool(d["priority"]["flagged"]), tuple(d["profile"]["existing_products"]), None)
    ctx = R.GroundingContext("client", [me], r.directory_names(), mid, p["data"] + "\n" + p["kb"])
    days = d["behaviour"]["dormant_streak_days"]
    assert verdict(ctx, f"Terminals have been dormant for {days} days.") == "pass"
    assert verdict(ctx, f"Terminals have been dormant for {days + 37} days.") == "block"
    assert verdict(ctx, "The monthly POS limit is AED 123,457,891.") == "block"
    assert verdict(ctx, "Trade finance fees are about 50% lower than over the counter.") == "pass"             # a figure from the knowledge page


def test_scaled_numbers_in_the_reference_are_understood():
    assert 5_000_000 in R.numbers_in("up to AED 5 million") and 27_000 in R.numbers_in("Idle balance AED 27k")
    assert R.numbers_in("MER2001 last30d") == []        # digits inside identifiers are not figures


# ── no false blocks on answers that are correct by construction ─────────────
def test_the_deterministic_answers_are_never_blocked(book):
    r, rows = book["reader"], book["rows"]
    for q in PORTFOLIO_QUESTIONS:
        p = copilot.portfolio_prompt(r, [{"role": "user", "text": q}])
        ctx = copilot._portfolio_grounding(rows, p["facts"] + "\n" + p["kb"])
        assert verdict(ctx, copilot.portfolio_data_answer(r, q), q) == "pass", q
    directory = r.directory_names()
    with SessionLocal() as s:
        for mid, _ in directory[::4]:                                  # every 4th client, 7 questions each
            rd = ClientReader(s, mid)
            d = rd.detail()
            me = R.ClientFacts(mid, d["name"], d["profile"]["risk_segment"], bool(d["behaviour"]["is_dormant_now"]), bool(d["priority"]["flagged"]),
                               tuple(d["profile"]["existing_products"]), bool(d["rate"]["change_recommended"]))
            for q in MERCHANT_QUESTIONS:
                p = copilot.merchant_prompt(rd, [{"role": "user", "text": q}])
                ctx = R.GroundingContext("client", [me], directory, mid, p["data"] + "\n" + p["kb"])
                assert verdict(ctx, copilot.merchant_data_answer(rd, q), q) == "pass", (mid, q)
