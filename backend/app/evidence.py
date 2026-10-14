"""The "Why this?" evidence behind a suggestion, so an RM can judge for themselves whether it is useful.

Everything here is computed from the client's own stored data. No model writes any of it, except the explanation text the suggestion
engine produced, which is shown as written and then checked: every figure in it is looked for in the client's data, and any that is
not found is listed. The checks on the suggestion (is the product pitchable, does the client already hold it, is the amount within
limits) are re-run now against current data, not repeated from when the suggestion was made.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import catalogue, feedback, guard_rules, knowledge
from .guard_rules import ClientFacts, GroundingContext
from .scoring import aed_full, pct
from .suggest_llm import RETENTION_CODES

KIND_LABEL = {"lending": "Lending", "cross_sell": "Cross-sell", "retention": "Retention"}
# Which facts matter most for each kind of suggestion, most relevant first. The first four are marked as key evidence.
RELEVANCE = {
    "lending": ["wc", "turnover", "balance", "limit", "volume", "m6", "terminals", "risk", "held", "rate"],
    "cross_sell": ["ntb", "held", "turnover", "balance", "volume", "risk", "terminals"],
    "retention": ["terminals", "volume", "m6", "limit", "risk", "balance", "rate"],
}


def _facts(d: dict) -> dict[str, tuple[str, str]]:
    """label and value for every fact we can show about this client, keyed so they can be ordered by relevance."""
    b, cp, pr, lend, rate = d["behaviour"], d["card_pos"], d["profile"], d["lending"], d["rate"]
    chg, m6, util, btt = b["volume_change_t30_vs_p30"], b["volume_change_m6"], cp["monthly_limit_utilisation"], b["balance_to_turnover"]

    def move(x):
        return "no prior-period figure" if x is None else f"{'up' if x >= 0 else 'down'} {pct(x)}"

    facts = {
        "volume": ("Card volume, last 30 days", f"{aed_full(cp['volume_t30'] or 0)} ({move(chg)} vs the prior 30 days)"),
        "m6": ("Six-month trend", move(m6) + " over the last six complete months"),
        "terminals": ("POS terminals", f"Dormant for {b['dormant_streak_days']} days" if b["is_dormant_now"]
                      else f"Active ({b['dormant_days_t30']} dormant days in the last 30)"),
        "limit": ("Monthly POS limit used", "no figure" if util is None else f"{pct(util)} of the {aed_full(cp['monthly_pos_limit_aed'])} limit"),
        "balance": ("Account balance", aed_full(pr["balance_aed"]) + ("" if btt is None else f", {pct(btt)} of average monthly turnover")),
        "turnover": ("Average monthly turnover", aed_full(pr["avg_monthly_turnover_aed"])),
        "risk": ("Risk segment", f"{pr['risk_segment']} (synthetic score {pr['synthetic_credit_score']}; synthetic, not a bureau score)"),
        "wc": ("Supplied working-capital limit", f"{aed_full(lend['suggested_working_capital_limit_aed'])}; opportunity {lend['opportunity_label']} (tier {lend['opportunity_tier']})"),
        "held": ("Products already held", ", ".join(pr["existing_products"]) or "none"),
        "rate": ("Merchant rate", f"{rate['current_pct']:.2f}% now; model range {rate['suggested_low_pct']:.2f}%–{rate['suggested_high_pct']:.2f}% (illustrative)"
                 if rate["change_recommended"] else f"{rate['current_pct']:.2f}%; no change recommended"),
    }
    if d["ntb_candidates"]:
        facts["ntb"] = ("Supplied cross-sell candidates", "; ".join(f"{x['candidate_product']}: {x['rationale']}" for x in d["ntb_candidates"]))
    return facts


def _checks(d: dict, s: dict) -> list[dict]:
    """The validations a suggestion must pass, re-run now on current data. `kind: caution` marks something worth a second look."""
    out: list[dict] = []
    kind, product, amount = s["kind"], s["product"], s["amount_aed"]
    held, lim, risk = d["profile"]["existing_products"], d["lending"]["suggested_working_capital_limit_aed"], d["profile"]["risk_segment"]

    def add(text, ok, level="check"):
        out.append(dict(text=text, ok=bool(ok), kind=level))

    if kind in ("lending", "cross_sell"):
        add(f"{product} is a product the bank sells and can be pitched from the data we hold", product in catalogue.PITCHABLE)
        add(f"The client does not already hold {product}", not catalogue.holds(held, product))
        spec = catalogue.BY_NAME.get(product)
        if spec and spec.sized and amount:
            cap = min(x for x in (spec.max_aed, lim) if x is not None)
            add(f"{aed_full(amount)} is within the cap of {aed_full(cap)} (the product's published maximum and the client's supplied limit)", amount <= cap + 0.5)
            if spec.min_aed:
                add(f"{aed_full(amount)} meets the published minimum of {aed_full(spec.min_aed)}", amount >= spec.min_aed)
    if kind == "retention":
        codes = {x["code"] for x in d["priority"]["signals"]}
        add("A retention action needs dormant terminals or falling volume, and this client has " + (", ".join(sorted(RETENTION_CODES & codes)) or "neither"),
            RETENTION_CODES & codes)
    if kind == "lending":     # the rule-based engine never pitches lending in these cases; the AI is not bound by that, so flag it
        add("The client is not in the High risk segment (the rule-based engine does not pitch lending to High risk clients)", risk != "High", "caution")
        add("The client's POS terminals are active (the rule-based engine does not pitch lending while terminals are dormant)",
            not d["behaviour"]["is_dormant_now"], "caution")
    return out


def _explanation_check(d: dict, s: dict) -> dict:
    """Look for every figure in the suggestion's written explanation and next step in the client's own data."""
    text = " ".join(x for x in (s["why"], s["next_action"]) if x)
    own = {k: v for k, v in d.items() if k not in ("suggestion", "pitch", "recommendation")}      # exclude the text being checked
    reference = json.dumps(own, default=str) + "\n" + knowledge.for_question("", always_core=True)
    me = ClientFacts(d["merchant_id"], d["name"], d["profile"]["risk_segment"], bool(d["behaviour"]["is_dormant_now"]),
                     bool(d["priority"]["flagged"]), tuple(d["profile"]["existing_products"]), None)
    found = guard_rules.check_figures("", text, GroundingContext("client", [me], [], d["merchant_id"], reference))
    missing = [v.detail.replace(" is not in the data", "") for v in found]
    return dict(unverified=missing, summary=("Every figure in this explanation was found in the client's data." if not missing
                                             else "Not found in the client's data: " + ", ".join(missing) + ". Check before relying on the explanation."))


def build(detail: dict, session: Session) -> dict:
    """The evidence panel for one client's current suggestion."""
    s = feedback.current_decision(detail)
    base = dict(merchant_id=detail["merchant_id"], name=detail["name"], as_of_date=detail["as_of_date"])
    if s is None:
        return dict(base, suggestion=None, message="There is no suggested action for this client right now.")
    key = feedback.key_for(s["kind"], s["product"])
    facts, order = _facts(detail), RELEVANCE.get(s["kind"], [])
    ranked = [k for k in order if k in facts] + [k for k in facts if k not in order]
    how = (f"Decided by the AI suggestion engine ({s['model']}). Its priority of {s['priority']:.0f} out of 100 is its own rating of the opportunity, "
           "the signal and the fit." if s["source"] == "llm"
           else f"Rule-based on the supplied data. The attention score is {detail['priority']['score']:.0f} (a client is flagged at 30 or more).")
    return dict(
        base,
        suggestion=dict(kind=s["kind"], kind_label=KIND_LABEL[s["kind"]], product=s["product"], amount_aed=s["amount_aed"], source=s["source"], model=s["model"],
                        priority=s["priority"], why=s["why"], next_action=s["next_action"], note=s["note"], how_decided=how),
        explanation_check=_explanation_check(detail, s),
        facts=[dict(label=facts[k][0], value=facts[k][1], key=i < 4) for i, k in enumerate(ranked)],
        signals=[dict(text=x["text"], points=x["points"], kind=x["kind"]) for x in detail["priority"]["signals"]],
        checks=_checks(detail, s),
        track_record=feedback.track_record(session, key, s["source"]),
        feedback=feedback.verdicts(session).get((detail["merchant_id"], key)),
    )
