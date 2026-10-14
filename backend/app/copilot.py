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

from . import audit, chat_cache, config, guard_rules, guardrails, knowledge, llm, prompt_budget
from .guard_rules import ClientFacts, GroundingContext, numbers_in
from .readers import ClientReader, PortfolioReader
from .scoring import aed, pct

log = logging.getLogger("rm_copilot")
LLM_ERROR_PUBLIC = "The AI service is unavailable right now, so this is a data-only answer."

SYSTEM_RULES = """You are the RM Co-pilot, an assistant for a bank Relationship Manager (RM).
Hard rules:
- Answer ONLY from the DATA block and, when provided, the KNOWLEDGE PAGE (client facts come from DATA; product, package and charge facts come from the KNOWLEDGE PAGE). If something is in neither, say it is not available. Never guess or invent figures, product names, fees, rates, card numbers or existing products.
- The data is synthetic demonstration data. Never describe it as real customer, credit-bureau or compliance data. "synthetic_credit_score" is a synthetic score, not a bureau score.
- Rates: use current_rate_pct / suggested_rate_range_pct / rate_rationale exactly as given. The suggested rate is only ever a RANGE (the model's estimate plus or minus 0.10 points): quote the range, never a single suggested figure, and say it is illustrative. If rate_change_recommended is false, say no rate change is recommended and do not quote the range.
- Pitches: each client's recommended pitch (product, amount, why, next action) was decided by the suggestion engine and is in its pitch / next_action fields; quote those. A client with pitch "none" has no pitch. For "who first" questions use pitch_rank (1 = strongest). Rank is by the engine's priority.
- Products: the KNOWLEDGE PAGE lists the bank's real products, published limits and charges. You may answer product questions from it (e.g. loan caps, package fees) and may reason about which listed product fits a client, but never invent products, amounts, rates or fees that are in neither the data nor the page. Products marked NOT PITCHABLE need data we do not hold.
- When listing clients for a topic, list only those where the relevant field is not "none"; never pad a list. Existing products come only from the products list; cross-sell candidates are in ntb_candidates.
- Actions ('recommendation' / 'rec' fields) are rule-based on the client's computed signals.
- Card mix is by per-day card label (Mass / Premium / Super Premium / Debit / Business), not by individual transaction.
- The DATA header counts ALL clients; the rows below it list only the clients most relevant to the question. When the header says some matching clients are not listed, say the list is partial and quote the counts from the header. Never say a client lacks something just because it is not listed.
- Be concise and easy to scan. Quote AED figures as given.
- Formatting: simple questions get 1-3 plain sentences. For anything longer (lists of clients, several facts, comparisons, recommendations) start with a one-line summary, then use short bullet points ("- " at line start), one fact per bullet, with the client or product name in **bold**. Put a blank line between sections and use a short bold label (e.g. **Why:**, **Next action:**) when helpful. Never write a dense paragraph of more than 3 sentences. No markdown tables or headings.
"""
PORTFOLIO_FILTER_RULES = """Answer the RM using only the supplied synthetic portfolio data. For a client-list question, include only clients that match every requested condition unless the question says OR. Use the portfolio and matching-client counts from the data header. If the header says some matching clients are not listed, give the count and say the list is partial. Use client names, never IDs. Do not invent clients or facts. Keep the answer concise and use bullets for names."""

OTHER_CLIENT_REPLY = ("This chat is scoped to {name} only, so I can't discuss other clients. "
                      "Use the portfolio Co-pilot for cross-client questions.")


def _is_compact_portfolio_filter(question: str, rows: list[dict]) -> bool:
    ctx = _portfolio_grounding(rows, "")
    conditions, _ = guard_rules.question_conditions(question, ctx)
    asks_for_clients = re.search(r"\b(which|who|list|show|clients?|how many|count|number of)\b", question, re.I)
    asks_for_other_data = re.search(r"\b(volume|balance|rate|pricing|mdr|product|pitch|opportunity|action|amount|industry|city|package)\b", question, re.I)
    return bool(conditions and asks_for_clients and not asks_for_other_data)


# ── context builders ────────────────────────────────────────────────────────
# The model never receives the whole portfolio. Every portfolio question gets (1) a header with counts and totals over ALL clients,
# so "how many" and "how much" answers are right whatever is listed, and (2) the rows of the clients that question is about, with only
# the fields it needs, capped at config.PORTFOLIO_ROW_LIMIT rows and at the room left in the window (prompt_budget.py).
FIELDS = {   # key -> (label shown to the model, value)
    "id": ("id", lambda r: r["id"]),
    "name": ("name", lambda r: r["name"]),
    "city": ("city", lambda r: r["city"]),
    "industry": ("industry", lambda r: r["industry"]),
    "package": ("package", lambda r: r["package"]),
    "risk": ("risk_segment", lambda r: r["risk"]),
    "rank": ("rank", lambda r: r["rank"]),
    "score": ("score", lambda r: r["score"]),
    "flagged": ("flagged", lambda r: "Y" if r["flagged"] else "N"),
    "reason": ("reason", lambda r: r["reason"]),
    "volume": ("volume_last30d_aed", lambda r: round(r["vol_t30"] or 0)),
    "vol_change": ("vol_change_vs_prior30d", lambda r: None if r["vol_change"] is None else round(r["vol_change"], 3)),
    "dormant": ("dormant_days", lambda r: r["dormant_days"]),
    "limit_used": ("monthly_limit_used", lambda r: None if r["limit_util"] is None else round(r["limit_util"], 3)),
    "balance": ("balance_aed", lambda r: round(r["balance"])),
    "action": ("action", lambda r: r["rec"] or "none"),
    "rate_now": ("current_rate_pct", lambda r: r["rate_current"]),
    "rate_new": ("suggested_rate_range_pct", lambda r: f"{r['rate_lo']:.2f}-{r['rate_hi']:.2f}" if r["rate_change"] else "no change"),
    "rate_change": ("rate_change_recommended", lambda r: "Y" if r["rate_change"] else "N"),
    "lend_limit": ("lending_pitch_limit_aed(only if a lending pitch exists)", lambda r: round(r["lending_pitch_limit"]) if r["lending_pitch_limit"] else "none"),
    "opportunity": ("opportunity", lambda r: r["opportunity"]),
    "products": ("products_held", lambda r: ",".join(r["products"]) or "none"),
    "ntb": ("ntb_candidates", lambda r: ",".join(r["ntb"]) or "none"),
    "pitch": ("pitch", lambda r: r["pitch"] or "none"),
    "pitch_rank": ("pitch_rank(1=strongest pitch)", lambda r: r["pitch_rank"] or "none"),
    "next_action": ("next_action", lambda r: r["next_action"] or "none"),
}
ALL_FIELDS = list(FIELDS)
_BIG = 10 ** 9


def _declining(q: str) -> bool:
    return bool(re.search(r"\b(declin\w+|drop\w*|fall\w*|fell|down|decreas\w+|shrink\w*|worst)\b", q, re.I))


def _volume_order(r: dict, q: str):
    if re.search(r"\blimits?\b", q, re.I):
        return -(r["limit_util"] or 0)
    change = r["vol_change"]
    if _declining(q):
        return change if change is not None else 99
    if re.search(r"\b(growth|grew|growing)\b", q, re.I):
        return -(change if change is not None else -99)
    return -(r["vol_t30"] or 0)


def _pitch_kept(r: dict, q: str) -> bool:
    """A pitch question about cross-sell lists the cross-sell candidates; one about lending lists the lending pitches; otherwise both."""
    if r["pitch"] is None:
        return False
    cross = re.search(r"\b(cross[- ]?sell\w*|ntb|new[- ]to[- ]bank)", q, re.I)
    lend = re.search(r"\b(lending|loans?|credit|facilit\w+|working capital)", q, re.I)
    if cross and not lend:
        return r["pitch"].startswith("Cross-sell") or bool(r["ntb"])
    if lend and not cross:
        return r["pitch"].startswith("Lending")
    return True


# Topics a portfolio question can be about: the words that signal it, the fields it needs, which clients are relevant, and the order.
# A question matching several topics gets the union of their fields and clients, ordered by the first.
TOPICS = [
    dict(name="pitches", rx=r"\b(pitch\w*|suggest\w*|recommend\w*(?!\s+(?:rate|pricing|mdr|change))|first|best|lending|loans?|credit|facilit\w+|cross[- ]?sell\w*|ntb|new[- ]to[- ]bank|opportunit\w+|working capital)\b",
         fields=["name", "pitch", "pitch_rank", "lend_limit", "opportunity", "next_action", "ntb"], keep=_pitch_kept,
         sort=lambda r, q: r["pitch_rank"] or _BIG, by="pitch rank", limit=5),     # a pitch takes about 60 reply tokens to write up; 5 fit the reply limit
    dict(name="rates", rx=r"\b(rates?|pricing|mdr|margin|reprice\w*)\b",
         fields=["name", "rate_now", "rate_new", "rate_change"], keep=lambda r, q: bool(r["rate_change"]),
         sort=lambda r, q: -abs((r["rate_current"] or 0) - (r["rate_suggested"] or 0)), by="size of the suggested rate change"),
    dict(name="attention", rx=r"\b(flagged|attention|priorit\w+|worry\w*|concern\w*|why|reason|urgent|needs?)\b",
         fields=["name", "flagged", "reason", "score", "action", "rank"], keep=lambda r, q: bool(r["flagged"]),
         sort=lambda r, q: r["rank"], by="attention rank"),
    dict(name="dormant", rx=r"\b(dormant|inactive|terminals?|reactivat\w+)\b",
         fields=["name", "dormant", "vol_change", "reason"], keep=lambda r, q: bool(r["dormant_days"]),
         sort=lambda r, q: -(r["dormant_days"] or 0), by="days dormant"),
    dict(name="risk", rx=r"\b(risks?|risky)\b",
         fields=["name", "risk", "flagged", "reason"], keep=lambda r, q: True,
         sort=lambda r, q: ({"High": 0, "Medium": 1, "Low": 2}.get(r["risk"], 3), r["rank"]), by="risk segment, High first"),
    dict(name="volume", rx=r"\b(volumes?|turnover|transactions?|sales|growth|grew|growing|trend\w*|limit|limits|declin\w+|drop\w*|fall\w*|fell)\b",
         fields=["name", "volume", "vol_change", "limit_used"], keep=lambda r, q: True, sort=_volume_order, by="the figure the question asks about"),
    dict(name="balance", rx=r"\b(balances?|deposits?|idle|cash)\b",
         fields=["name", "balance", "package"], keep=lambda r, q: True, sort=lambda r, q: -(r["balance"] or 0), by="balance"),
    dict(name="products", rx=r"\b(products?|packages?|holds?|holding|owns?|smarttrade|businessonline|payroll|cards?)\b",
         fields=["name", "package", "products"], keep=lambda r, q: True, sort=lambda r, q: r["rank"], by="attention rank"),
    dict(name="profile", rx=r"\b(cit(?:y|ies)|emirates?|industr(?:y|ies)|sectors?)\b",
         fields=["name", "industry", "city"], keep=lambda r, q: True, sort=lambda r, q: r["rank"], by="attention rank"),
]
OVERVIEW = dict(name="overview", fields=["name", "industry", "risk", "flagged", "dormant", "pitch", "rank"], keep=lambda r, q: True,
                sort=lambda r, q: r["rank"], by="attention rank")
_GENERIC_WORDS = {"services", "trading", "retail", "repair", "estate", "technology", "center", "centre"}


def _named_clients(rows: list[dict], q: str) -> list[dict]:
    low = q.lower()
    return [r for r in rows if re.search(rf"(?<!\w){re.escape(r['name'].lower())}(?!\w)", low)]


def _scope_rows(rows: list[dict], q: str) -> list[dict]:
    """Narrow to the city, package or industry the question mentions (a question about Dubai clients is about Dubai clients)."""
    low = q.lower()
    cities = {c for c in {r["city"] for r in rows} if re.search(rf"\b{re.escape(c.lower())}\b", low)}
    if cities:
        rows = [r for r in rows if r["city"] in cities]
    if "package" in low:
        pk = {p for p in {r["package"] for r in rows} if re.search(rf"\b{re.escape(p.lower())}\b", low)}
        if pk:
            rows = [r for r in rows if r["package"] in pk]
    stems = {w[:6] for ind in {r["industry"] for r in rows} for w in re.findall(r"[a-z]{5,}", ind.lower()) if w not in _GENERIC_WORDS}
    hit = {s for s in stems if re.search(rf"\b{re.escape(s)}", low)}
    if hit:
        rows = [r for r in rows if any(w[:6] in hit for w in re.findall(r"[a-z]{5,}", r["industry"].lower()))]
    return rows


def _share(n: int, total: int) -> str:
    return f"{n} ({round(100 * n / total)}%)" if total else str(n)


def portfolio_header(reader: PortfolioReader, rows: list[dict]) -> str:
    """Counts and totals over ALL clients. Always sent, so a question about a count or a total never depends on which rows are listed."""
    n = len(rows)
    v30, p30 = sum(r["vol_t30"] or 0 for r in rows), sum(r["vol_p30"] or 0 for r in rows)
    change = f"{(v30 / p30 - 1) * 100:+.1f}%" if p30 else "n/a"
    pitch = lambda kind: sum(1 for r in rows if r["pitch"] and r["pitch"].startswith(kind))
    return (f"as_of_date={reader.status().get('as_of_date')} | clients={n} | flagged_for_attention={_share(sum(1 for r in rows if r['flagged']), n)} | "
            f"dormant_terminals_now={_share(sum(1 for r in rows if r['dormant_days']), n)} | risk_high={sum(1 for r in rows if r['risk'] == 'High')} | "
            f"risk_medium={sum(1 for r in rows if r['risk'] == 'Medium')} | risk_low={sum(1 for r in rows if r['risk'] == 'Low')} | "
            f"rate_change_recommended={_share(sum(1 for r in rows if r['rate_change']), n)} | lending_pitch={pitch('Lending')} | "
            f"cross_sell_pitch={pitch('Cross-sell')} | total_volume_last30d_aed={v30:,.0f} | total_volume_prior30d_aed={p30:,.0f} | "
            f"portfolio_volume_change_vs_prior30d={change} | total_balance_aed={sum(r['balance'] or 0 for r in rows):,.0f}")


def _compact_fields(question: str) -> list[str]:
    fields = ["name"]
    if re.search(r"\b(flagged|attention)\b", question, re.I):
        fields += ["flagged", "reason"]
    if re.search(r"\bhigh[\s-]*risk|medium[\s-]*risk|low[\s-]*risk", question, re.I):
        fields.append("risk")
    if re.search(r"\b(dormant|inactive)\b", question, re.I):
        fields.append("dormant")
    return fields


def _plan(rows: list[dict], question: str, compact: bool, knowledge_given: bool = False):
    """Which clients to list, with which fields and in which order. Returns (fields, clients, how they are ordered, limit)."""
    if compact:     # a filter question: every client that meets the conditions, names only
        ctx = _portfolio_grounding(rows, "")
        conds, mode = guard_rules.question_conditions(question, ctx)
        combine = any if mode == "any" else all
        hits = [r for r, c in zip(rows, ctx.clients) if combine(pred(c) for _, pred in conds)]
        return _compact_fields(question), hits, "attention rank", None
    named = _named_clients(rows, question)
    if named:       # the question names clients: their full records
        return ALL_FIELDS, named[:5], "the order named", None
    topics = [t for t in TOPICS if re.search(t["rx"], question, re.I)] or [OVERVIEW]
    if knowledge_given and all(t["name"] == "products" for t in topics):
        return ["name"], [], "n/a", 0       # a fee or product-catalogue question is answered from the knowledge page, not from client rows
    fields = [f for f in ALL_FIELDS if any(f in t["fields"] for t in topics)]
    scoped = _scope_rows(rows, question)
    keep = [r for r in scoped if any(t["keep"](r, question) for t in topics)]
    first = topics[0]
    limit = 8 if first is OVERVIEW else first.get("limit", config.PORTFOLIO_ROW_LIMIT)
    return fields, sorted(keep, key=lambda r: first["sort"](r, question)), first["by"], limit


def portfolio_context_parts(reader: PortfolioReader, rows: list[dict] | None = None, question: str | None = None,
                            budget_chars: int | None = None, knowledge_given: bool = False) -> tuple[str, str]:
    """(header, body) of the data block. `body` is the field list, the listed rows and a line saying how many were left out."""
    all_rows = rows if rows is not None else reader.portfolio_rows()
    header = portfolio_header(reader, all_rows)
    if question is None:      # no question: every client, every field
        fields, clients, by, limit = ALL_FIELDS, all_rows, "attention rank", None
    else:
        fields, clients, by, limit = _plan(all_rows, question, _is_compact_portfolio_filter(question, all_rows), knowledge_given)
    total, lines, used = len(clients), [], 0
    cap = total if limit is None else min(total, limit)
    for r in clients[:cap]:
        line = "|".join(str(FIELDS[f][1](r)) for f in fields)
        if budget_chars is not None and used + len(line) + 1 > budget_chars:
            break
        lines.append(line)
        used += len(line) + 1
    left = total - len(lines)
    summary = f"matching_clients={total} listed={len(lines)} ordered_by={by}" + (f" | NOT LISTED: {left} more matching clients" if left else "")
    body = summary + "\nfields: " + "|".join(FIELDS[f][0] for f in fields) + ("\n" + "\n".join(lines) if lines else "")
    return header, body


def portfolio_context(reader: PortfolioReader, rows: list[dict] | None = None, question: str | None = None,
                      budget_chars: int | None = None) -> str:
    header, body = portfolio_context_parts(reader, rows, question, budget_chars)
    return header + "\n" + body


def merchant_context(reader: ClientReader) -> str:
    """One client's data as compact JSON. The two long series are written as short pipe-separated lines: they were 45% of the JSON."""
    d = reader.detail()
    d.pop("volume_bars", None)     # chart heights for the screen; the monthly figures below carry the same facts
    d["monthly_volume_all_months (month|volume_aed|txns|complete)"] = [
        f"{r.month}|{r.volume_aed:.0f}|{r.txn_count}|{'Y' if r.is_complete else 'N'}" for r in reader.monthly()]
    d["daily_last_30_days (date|volume_aed|txns|terminal|card_type)"] = [
        f"{x['date']}|{x['volume_aed']:.0f}|{x['transactions']}|{x['terminal_status']}|{x['card_type']}" for x in reader.daily(30)]
    return json.dumps(d, default=str, separators=(",", ":"))


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
                + "\n".join(f"- **{r['name']}** — {r['rate_current']:.2f}% now, model range {r['rate_lo']:.2f}%–{r['rate_hi']:.2f}%" for r in rc[:5]))
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
            return f"Current rate {r['current_pct']:.2f}%; the model's range is {r['suggested_low_pct']:.2f}%–{r['suggested_high_pct']:.2f}%. {r['rationale']}"
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
    """The last 12 turns, starting with a user turn. When they are long, the OLDEST turns go first and the newest question always stays,
    so a long conversation cannot push the rules out of the window."""
    api_msgs = [{"role": "assistant" if x["role"] in ("bot", "assistant") else "user", "content": x["text"]} for x in messages[-12:]]
    while api_msgs and api_msgs[0]["role"] != "user":
        api_msgs.pop(0)
    while len(api_msgs) > 1 and sum(len(x["content"]) for x in api_msgs) > config.HISTORY_MAX_CHARS:
        api_msgs.pop(0)
        while len(api_msgs) > 1 and api_msgs[0]["role"] != "user":
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
    history = _history(messages)
    estimated = prompt_budget.estimate(system, history)
    if estimated > prompt_budget.prompt_limit():
        # A prompt over the window would be cut at the start by the model server, losing the rules. Never send one.
        log.warning("prompt too large for the context window (est. %d tokens, limit %d); answering from data only", estimated, prompt_budget.prompt_limit())
        audit.record("prompt_over_budget", estimated_tokens=estimated, limit_tokens=prompt_budget.prompt_limit(), question=question)
        return dict(reply=fallback(), mode="data")
    cache_key = chat_cache.chat_cache.exact_key(system, history, config.LLM_MODEL)
    namespace = chat_cache.chat_cache.semantic_namespace(system, config.LLM_MODEL)
    reply = chat_cache.chat_cache.get_exact(cache_key)
    cache_hit = "exact" if reply is not None else None
    if reply is None and len(history) == 1 and history[0]["role"] == "user":
        reply = chat_cache.chat_cache.get_semantic(question, namespace, config.LLM_MODEL)
        if reply is not None:
            cache_hit = "semantic"
    usage = None
    try:
        if reply is None:
            reply = llm.complete(system, history)
            usage = {**(llm.last_usage() or {}), "prompt_tokens_estimated": estimated}
    except Exception as e:  # noqa: BLE001 - never break the chat; degrade to data answer
        log.warning("LLM call failed (%s): %s", type(e).__name__, e)  # provider detail stays in the server log only
        return dict(reply=fallback(), mode="data", llm_error=LLM_ERROR_PUBLIC)
    gout = guardrails.check_output(question, reply, gctx, use_llm=True)
    if not gout.allowed:
        return dict(reply=fallback(), mode="data", guardrail=gout.info(), blocked_reply=reply)     # the blocked text is audited, not shown
    if cache_hit != "exact":
        chat_cache.chat_cache.store(cache_key, namespace, config.LLM_MODEL, question, reply)
    out = dict(reply=reply, mode="llm")
    if cache_hit:
        out["cache_hit"] = cache_hit
    if usage:
        out["usage"] = usage     # audited by the API layer, not returned to the browser
    if gout.violations or gout.engine != "nemo":   # soft findings or a degraded engine are audited, not shown
        out["guardrail"] = gout.info()
    return out


def _row_figures(r: dict) -> tuple[tuple[str, float], ...]:
    """Every figure the model was shown for one client, typed (pct, days, any), so an answer that names the client is checked against it."""
    out: list[tuple[str, float]] = [("any", float(r[k])) for k in ("vol_t30", "balance", "wc_limit", "dormant_days", "score", "rank",
                                                                 "lending_pitch_limit", "pitch_rank") if r.get(k) is not None]
    out += [("pct", float(r[k])) for k in ("rate_current", "rate_lo", "rate_hi") if r.get(k) is not None]     # rates are percentages; the exact modelled rate is not shown
    out += [("any", float(r["rate_current"]))] if r.get("rate_current") is not None else []
    if r.get("dormant_days"):
        out.append(("days", float(r["dormant_days"])))
    for k in ("vol_change", "limit_util"):     # stored as fractions, quoted as percentages
        if r.get(k) is not None:
            out += [("pct", abs(r[k]) * 100), ("any", abs(r[k]))]
    text = " ".join(str(r[k]) for k in ("reason", "rec", "pitch", "next_action") if r.get(k))
    out += [("pct", float(m.group(1))) for m in guard_rules._PCT.finditer(text)]
    out += [("days", float(m.group(1))) for m in guard_rules._DURATION.finditer(text) if m.group(2).lower().startswith("day")]
    out += [("any", v) for v in numbers_in(text)]
    return tuple(out)


def _portfolio_grounding(rows: list[dict], reference: str) -> GroundingContext:
    clients = [ClientFacts(r["id"], r["name"], r["risk"], bool(r["dormant_days"]), bool(r["flagged"]), tuple(r["products"]),
                           bool(r["rate_change"]), _row_figures(r)) for r in rows]
    return GroundingContext("portfolio", clients, [(r["id"], r["name"]) for r in rows], None, reference)


def portfolio_prompt(reader: PortfolioReader, messages: list[dict]) -> dict:
    """The system prompt for a portfolio question, sized to fit the window. Also returns the pieces the answer is checked against."""
    last = messages[-1]["text"]
    rows = reader.portfolio_rows()
    compact = _is_compact_portfolio_filter(last, rows)
    kb = "" if compact else knowledge.for_question(last)
    rules = PORTFOLIO_FILTER_RULES if compact else SYSTEM_RULES
    head = rules + "\nScope: the whole portfolio."
    if kb:
        head += "\n\n=== KNOWLEDGE PAGE ===\n" + kb
    head += "\n\n=== DATA (one client per line) ===\n"
    prose_used = prompt_budget.prose_tokens(head) + sum(prompt_budget.prose_tokens(m["content"]) for m in _history(messages))
    header, body = portfolio_context_parts(reader, rows, last, prompt_budget.data_chars_left(prose_used), knowledge_given=bool(kb))
    facts = header + "\n" + body.split("\n", 1)[0]     # totals over all clients, plus the line that counts what is listed
    return dict(system=head + header + "\n" + body, rows=rows, header=header, facts=facts, kb=kb, compact=compact)


def portfolio_reply(reader: PortfolioReader, messages: list[dict]) -> dict:
    last = messages[-1]["text"]
    p = portfolio_prompt(reader, messages)
    # The answer is checked against the totals and counts in the prompt, the knowledge text and each named client's own figures.
    return _answer(p["system"], messages, lambda: portfolio_data_answer(reader, last), _portfolio_grounding(p["rows"], p["facts"] + "\n" + p["kb"]))


def merchant_prompt(reader: ClientReader, messages: list[dict]) -> dict:
    """The system prompt for a single-client question. The knowledge page contributes only the parts the question needs."""
    last = messages[-1]["text"]
    d = reader.detail()
    data, kb = merchant_context(reader), knowledge.for_question(last, always_core=True)
    system = (SYSTEM_RULES + f"\nScope: ONLY the single client {d['name']} ({reader.merchant_id}). You have no information about any other client; "
              "if asked about another client, decline.\n\n=== KNOWLEDGE PAGE ===\n" + kb + "\n\n=== DATA (JSON) ===\n" + data)
    return dict(system=system, data=data, kb=kb, detail=d)


def merchant_reply(reader: ClientReader, directory: list[tuple[str, str]], messages: list[dict]) -> dict:
    last = messages[-1]["text"]
    d = reader.detail()
    name = d["name"]
    if mentions_other_client(last, reader.merchant_id, name, directory):
        return dict(reply=OTHER_CLIENT_REPLY.format(name=name), mode="guard")
    p = merchant_prompt(reader, messages)
    me = ClientFacts(reader.merchant_id, name, d["profile"]["risk_segment"], bool(d["behaviour"]["is_dormant_now"]),
                     bool(d["priority"]["flagged"]), tuple(d["profile"]["existing_products"]), bool(d["rate"]["change_recommended"]))
    gctx = GroundingContext("client", [me], directory, reader.merchant_id, p["data"] + "\n" + p["kb"])
    return _answer(p["system"], messages, lambda: merchant_data_answer(reader, last), gctx)
