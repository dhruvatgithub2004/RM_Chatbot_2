"""Portfolio and Merchant co-pilots.

Grounding is structural:
  * Portfolio co-pilot  -> context built from PortfolioReader (all clients, compact rows).
  * Merchant co-pilot   -> context built from ONE ClientReader only; other clients' names are
                           detected up-front and refused before any model call.
With an LLM configured (see llm.py), answers come from the model; otherwise (or on any LLM error) from a
deterministic responder that only quotes computed facts.
"""
from __future__ import annotations

import json
import logging
import re

from . import config, guard_rules, guardrails, knowledge, llm
from .guard_rules import ClientFacts, GroundingContext
from .readers import ClientReader, PortfolioReader
from .scoring import aed, pct

log = logging.getLogger("rm_copilot")
LLM_ERROR_PUBLIC = "The AI service is unavailable right now, so this is a data-only answer."

SYSTEM_RULES = """You are the RM Co-pilot, an assistant for a bank Relationship Manager (RM).
Hard rules:
- Answer ONLY from the DATA block and the KNOWLEDGE PAGE below (client facts come from DATA; product, package and charge facts come from the KNOWLEDGE PAGE). If something is in neither, say it is not available. Never guess or invent figures, product names, fees, rates, card numbers or existing products.
- The data is synthetic demonstration data. Never describe it as real customer, credit-bureau or compliance data. "synthetic_credit_score" is a synthetic score, not a bureau score.
- Rates: use current_rate_pct / suggested_rate_pct / rate_rationale exactly as given. If rate_change_recommended is false, say no rate change is recommended and do not quote the suggested rate.
- Pitches: each client's recommended pitch (product, amount, why, next action) was decided by the suggestion engine and is in its pitch / next_action fields; quote those. A client with pitch "none" has no pitch. For "who first" questions use pitch_rank (1 = strongest). Rank is by the engine's priority.
- Products: the KNOWLEDGE PAGE lists the bank's real products, published limits and charges. You may answer product questions from it (e.g. loan caps, package fees) and may reason about which listed product fits a client, but never invent products, amounts, rates or fees that are in neither the data nor the page. Products marked NOT PITCHABLE need data we do not hold.
- When listing clients for a topic, list only those where the relevant field is not "none"; never pad a list. Existing products come only from the products list; cross-sell candidates are in ntb_candidates.
- Actions ('recommendation' / 'rec' fields) are rule-based on the client's computed signals.
- Card mix is by per-day card label (Mass / Premium / Super Premium / Debit / Business), not by individual transaction.
- Be concise and easy to scan. Quote AED figures as given.
- Formatting: simple questions get 1-3 plain sentences. For anything longer (lists of clients, several facts, comparisons, recommendations) start with a one-line summary, then use short bullet points ("- " at line start), one fact per bullet, with the client or product name in **bold**. Put a blank line between sections and use a short bold label (e.g. **Why:**, **Next action:**) when helpful. Never write a dense paragraph of more than 3 sentences. No markdown tables or headings.
"""

OTHER_CLIENT_REPLY = ("This chat is scoped to {name} only, so I can't discuss other clients. "
                      "Use the portfolio Co-pilot for cross-client questions.")


# ── context builders ────────────────────────────────────────────────────────
def portfolio_context(reader: PortfolioReader, rows: list[dict] | None = None) -> str:
    st = reader.status()
    rows = rows if rows is not None else reader.portfolio_rows()
    lines = [f"as_of_date={st.get('as_of_date')} clients={len(rows)} flagged={st.get('flagged')}",
             "fields: id|name|city|industry|package|risk_segment|rank|score|flagged|reason|volume_last30d_aed|vol_change_vs_prior30d|"
             "dormant_days|monthly_limit_used|balance_aed|action|current_rate_pct|suggested_rate_pct|rate_change_recommended|"
             "lending_pitch_limit_aed(only if a lending pitch exists)|opportunity|products_held|ntb_candidates|pitch|pitch_rank(1=strongest pitch)|next_action"]
    for r in rows:
        lines.append("|".join(str(x) for x in [
            r["id"], r["name"], r["city"], r["industry"], r["package"], r["risk"], r["rank"], r["score"], "Y" if r["flagged"] else "N",
            r["reason"], round(r["vol_t30"] or 0), None if r["vol_change"] is None else round(r["vol_change"], 3),
            r["dormant_days"], None if r["limit_util"] is None else round(r["limit_util"], 3), round(r["balance"]), r["rec"] or "none",
            r["rate_current"], r["rate_suggested"] if r["rate_change"] else "no change", "Y" if r["rate_change"] else "N",
            round(r["lending_pitch_limit"]) if r["lending_pitch_limit"] else "none", r["opportunity"], ",".join(r["products"]) or "none",
            ",".join(r["ntb"]) or "none", r["pitch"] or "none", r["pitch_rank"] or "none", r["next_action"] or "none"]))
    lines.append("\nTOP PITCHES, strongest first (use this list, in this order, for 'who to pitch first / best pitch' questions):")
    for x in reader.suggestions(limit=25):
        amt = f" — suggested limit AED {x['amount_aed']:,.0f}" if x["amount_aed"] else ""
        lines.append(f"{x['rank']}. {x['name']} ({x['merchant_id']}): {x['category']} — {x['product']}{amt}")
    return "\n".join(lines)


def merchant_context(reader: ClientReader) -> str:
    d = reader.detail()
    d["monthly_volume_all_months"] = [dict(month=r.month, volume_aed=r.volume_aed, txns=r.txn_count, complete=r.is_complete) for r in reader.monthly()]
    d["daily_last_30_days"] = reader.daily(30)
    return json.dumps(d, default=str)


# ── scope guard ─────────────────────────────────────────────────────────────
def mentions_other_client(text: str, current_id: str, current_name: str, directory: list[tuple[str, str]]) -> bool:
    t = text.lower()
    for mid, name in directory:
        if mid == current_id or name.lower() == current_name.lower():
            continue
        if re.search(rf"\b{_id_pattern(mid)}\b", t) or re.search(rf"\b{re.escape(name.lower())}\b", t):
            return True
    return False


def _id_pattern(mid: str) -> str:
    """Regex for a merchant ID that also matches separated spellings ('MER 2002', 'mer-2002')."""
    return guard_rules.id_pattern(mid)


# ── deterministic responders (real computed facts only) ─────────────────────
def _has(t: str, *words: str) -> bool:
    return any(w in t for w in words)


def portfolio_data_answer(reader: PortfolioReader, text: str) -> str:
    t = text.lower()
    rows = reader.portfolio_rows()
    flagged = [r for r in rows if r["flagged"]]
    # Questions that combine conditions (dormant, risk segment, flagged, holds a product): list the clients that meet all (or any) of them
    gctx = _portfolio_grounding(rows, "")
    conds, mode = guard_rules.question_conditions(text, gctx)
    if len(conds) >= 2 and _has(t, "which", "who", "list", "show", "clients"):
        hits = [c for c in gctx.clients if (any if mode == "any" else all)(pred(c) for _, pred in conds)]
        label = (" or " if mode == "any" else " and ").join(lbl for lbl, _ in conds)
        if not hits:
            return f"No client is {label} in the data."
        more = f"\n- +{len(hits) - 15} more" if len(hits) > 15 else ""
        return f"{len(hits)} of {len(rows)} clients {'is' if len(hits) == 1 else 'are'} {label}:\n" + "\n".join(f"- **{c.name}**" for c in hits[:15]) + more
    # "Which clients hold <product>?": answered from the products-held data
    terms = sorted({p for r in rows for p in r["products"]}, key=len, reverse=True)
    term = next((x for x in terms if re.search(rf"(?<!\w){re.escape(x.lower())}(?!\w)", t)), None)
    if term and _has(t, "hold", "have", "has", "own", "using") and not guard_rules.NOT_A_HOLD_QUESTION.search(text):
        h = [r for r in rows if term in r["products"]]
        more = f"\n- +{len(h) - 15} more" if len(h) > 15 else ""
        return f"{len(h)} of {len(rows)} clients hold {term}:\n" + "\n".join(f"- **{r['name']}**" for r in h[:15]) + more
    if _has(t, "flag", "attention", "priorit", "who needs"):
        top = "\n".join(f"- **{r['name']}** — {r['reason']}" for r in flagged[:6])
        more = f"\n- +{len(flagged) - 6} more on the dashboard" if len(flagged) > 6 else ""
        return f"{len(flagged)} of {len(rows)} clients are flagged for attention:\n{top}{more}"
    if _has(t, "dormant", "inactive"):
        d = [r for r in rows if r["dormant_days"]]
        return f"{len(d)} clients have dormant POS terminals right now:\n" + "\n".join(f"- **{r['name']}** — {r['dormant_days']} days" for r in d[:8])
    if _has(t, "risk", "high-risk"):
        h = [r for r in rows if r["risk"] == "High"]
        hf = [r for r in h if r["flagged"]]
        return (f"{len(h)} clients are in the High risk segment:\n" + "\n".join(f"- **{r['name']}**" for r in h[:8])
                + (f"\n\n{len(hf)} of them are also flagged for attention." if hf else ""))
    if _has(t, "rate", "pricing", "mdr"):
        rc = [r for r in rows if r["rate_change"]]
        return (f"{len(rc)} of {len(rows)} clients have a recommended rate change. Examples:\n"
                + "\n".join(f"- **{r['name']}** — {r['rate_current']:.2f}% → {r['rate_suggested']:.2f}%" for r in rc[:5]))
    if _has(t, "lend", "loan", "credit", "facility", "working capital"):
        l = sorted([r for r in rows if r["pitch"] and r["pitch"].startswith("Lending")], key=lambda r: -r["wc_limit"])
        return (f"{len(l)} clients are eligible for a working-capital lending pitch. Largest suggested limits:\n"
                + "\n".join(f"- **{r['name']}** — AED {r['wc_limit']:,.0f}" for r in l[:5])) if l else "No client currently has a lending pitch."
    if _has(t, "cross", "ntb", "new-to-bank", "new to bank"):
        c = [r for r in rows if r["ntb"]]
        from collections import Counter
        mix = Counter(p for r in c for p in r["ntb"])
        return (f"{len(c)} clients have new-to-bank cross-sell candidates ("
                + ", ".join(f"{k}: {v}" for k, v in mix.most_common()) + "). Examples:\n"
                + "\n".join(f"- **{r['name']}** — {', '.join(r['ntb'])}" for r in c[:5]))
    if _has(t, "summar", "portfolio", "overview"):
        dorm = sum(1 for r in rows if r["dormant_days"])
        hi = sum(1 for r in rows if r["risk"] == "High")
        vol = sum(r["vol_t30"] or 0 for r in rows)
        return (f"Portfolio of {len(rows)} clients across {len({r['industry'] for r in rows})} industries; {len(flagged)} flagged for attention, "
                f"{dorm} with dormant POS terminals, {hi} in the High risk segment. Total POS volume in the last 30 days: {aed(vol)}.")
    return ("I can answer questions across the full portfolio — try asking about flagged clients, dormant terminals, risk, lending opportunities, "
            "or a portfolio summary. For a specific merchant, open their profile and use that client's co-pilot.")


def merchant_data_answer(reader: ClientReader, text: str) -> str:
    t = text.lower()
    d = reader.detail()
    n, b, p, cp = d["name"], d["behaviour"], d["priority"], d["card_pos"]
    rec = d["recommendation"]
    if _has(t, "rate", "pricing", "mdr", "fee"):
        r = d["rate"]
        if r["change_recommended"]:
            return f"Current rate {r['current_pct']:.2f}% → suggested {r['suggested_pct']:.2f}%. {r['rationale']}"
        return f"Current rate {r['current_pct']:.2f}%. No rate change is recommended. {r['rationale']}"
    if _has(t, "cross", "sell", "product", "recommend", "pitch", "best"):
        parts = []
        if d["pitch"]:
            pt = d["pitch"]
            amt = f" (suggested limit AED {pt['amount_aed']:,.0f})" if pt["amount_aed"] else ""
            parts.append(f"- **Best pitch:** {pt['kind']} — {pt['title']}{amt}. {pt['why']}")
        if d["ntb_candidates"]:
            parts.append("- **New-to-bank candidates:**\n" + "\n".join(f"  - {x['candidate_product']} — {x['rationale']}" for x in d["ntb_candidates"]))
        if rec:
            parts.append(f"- **Suggested action:** {rec['title']}. {rec['why']}")
        held = ", ".join(d["profile"]["existing_products"]) or "none"
        parts.append(f"- **Existing products:** {held}")
        return "\n".join(parts) if len(parts) > 1 else "No pitch applies to this client right now.\n" + parts[0]
    if _has(t, "lend", "loan", "facilit", "credit"):
        pt = d["pitch"]
        if pt and pt["kind"] == "Lending":
            return f"{pt['title']}: suggested limit AED {pt['amount_aed']:,.0f}. {pt['why']}"
        return "No lending pitch is recommended for this client right now."
    if _has(t, "risk", "flag", "concern", "attention"):
        sig = "; ".join(x["text"] for x in p["signals"]) or "no attention signals"
        return f"{n} is in the {d['profile']['risk_segment']} risk segment (synthetic score {d['profile']['synthetic_credit_score']}). Signals: {sig}."
    if _has(t, "volume", "trend", "growth", "decline"):
        bars = ", ".join(f"{x['month']} {aed(x['volume_aed'])}" for x in d["volume_bars"])
        ch = b["volume_change_t30_vs_p30"]
        return f"Monthly POS volume: {bars}. Last 30 days vs prior 30: {'n/a' if ch is None else ('+' if ch >= 0 else '-') + pct(ch)}."
    if _has(t, "card", "mix"):
        return "Card mix (last 30 days, by volume): " + ", ".join(f"{x['type']} {x['pct']:.0f}% ({x['txns']:,} txns)" for x in d["card_mix"]) + "."
    if _has(t, "summar", "profile", "overview", "who"):
        return (f"{n} is a {d['profile']['segment']} package {d['industry']} client in {d['city']} with a balance of {aed(d['profile']['balance_aed'])}. "
                f"POS volume in the last 30 days was {aed(cp['volume_t30'] or 0)} across {cp['txn_t30']:,} transactions. "
                f"{p['reason']}.")
    return (f"Based on the POS and profile data for {n}: {aed(cp['volume_t30'] or 0)} volume in the last 30 days, "
            f"{d['profile']['risk_segment'].lower()} risk segment. {p['reason']}. Ask about risk, volume, card mix or the recommended action.")


# ── LLM ─────────────────────────────────────────────────────────────────────
def _history(messages: list[dict]) -> list[dict]:
    api_msgs = [{"role": "assistant" if x["role"] in ("bot", "assistant") else "user", "content": x["text"]} for x in messages[-12:]]
    while api_msgs and api_msgs[0]["role"] != "user":
        api_msgs.pop(0)
    return api_msgs


def _llm(system: str, messages: list[dict]) -> str:
    return llm.complete(system, _history(messages))


def _answer(system: str, messages: list[dict], fallback, gctx: GroundingContext) -> dict:
    """Input rails -> model -> output rails (NVIDIA NeMo Guardrails, see guardrails.py). A blocked answer is replaced by the
    deterministic data-only answer, so the RM never sees an answer that failed a hard check."""
    question = messages[-1]["text"]
    use_llm = bool(config.LLM_API_KEY)
    gin = guardrails.check_input(question, use_llm=use_llm)
    if not gin.allowed:
        return dict(reply=gin.message or guardrails.DECISION_MESSAGE, mode="guard", guardrail=gin.info())
    if not use_llm:
        return dict(reply=fallback(), mode="data")
    try:
        reply = _llm(system, messages)
    except Exception as e:  # noqa: BLE001 - never break the chat; degrade to data answer
        log.warning("LLM call failed (%s): %s", type(e).__name__, e)  # provider detail stays in the server log only
        return dict(reply=fallback(), mode="data", llm_error=LLM_ERROR_PUBLIC)
    gout = guardrails.check_output(question, reply, gctx, use_llm=True)
    if not gout.allowed:
        return dict(reply=fallback(), mode="data", guardrail=gout.info())
    out = dict(reply=reply, mode="llm")
    if gout.violations or gout.engine != "nemo":   # soft findings or a degraded engine are audited, not shown
        out["guardrail"] = gout.info()
    return out


def _portfolio_grounding(rows: list[dict], reference: str) -> GroundingContext:
    clients = [ClientFacts(r["id"], r["name"], r["risk"], bool(r["dormant_days"]), bool(r["flagged"]), tuple(r["products"]),
                           bool(r["rate_change"])) for r in rows]
    return GroundingContext("portfolio", clients, [(r["id"], r["name"]) for r in rows], None, reference)


def portfolio_reply(reader: PortfolioReader, messages: list[dict]) -> dict:
    last = messages[-1]["text"]
    rows = reader.portfolio_rows()
    data = portfolio_context(reader, rows)
    kb = knowledge.text()
    system = (SYSTEM_RULES + "\nScope: the whole portfolio.\n\n=== KNOWLEDGE PAGE ===\n" + kb
              + "\n\n=== DATA (one client per line) ===\n" + data)
    return _answer(system, messages, lambda: portfolio_data_answer(reader, last), _portfolio_grounding(rows, data + "\n" + kb))


def merchant_reply(reader: ClientReader, directory: list[tuple[str, str]], messages: list[dict]) -> dict:
    last = messages[-1]["text"]
    d = reader.detail()
    name = d["name"]
    if mentions_other_client(last, reader.merchant_id, name, directory):
        return dict(reply=OTHER_CLIENT_REPLY.format(name=name), mode="guard")
    data, kb = merchant_context(reader), knowledge.text()
    system = (SYSTEM_RULES + f"\nScope: ONLY the single client {name} ({reader.merchant_id}). You have no information about any other client; "
              "if asked about another client, decline.\n\n=== KNOWLEDGE PAGE ===\n" + kb + "\n\n=== DATA (JSON) ===\n" + data)
    me = ClientFacts(reader.merchant_id, name, d["profile"]["risk_segment"], bool(d["behaviour"]["is_dormant_now"]),
                     bool(d["priority"]["flagged"]), tuple(d["profile"]["existing_products"]), bool(d["rate"]["change_recommended"]))
    gctx = GroundingContext("client", [me], directory, reader.merchant_id, data + "\n" + kb)
    return _answer(system, messages, lambda: merchant_data_answer(reader, last), gctx)
