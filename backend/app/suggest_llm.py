"""LLM-decided suggestions.

For every client the LLM receives (a) the consolidated knowledge page and (b) that client's data, and returns ONE decision:
what the RM should pitch (a catalogue product + amount) or do next, with a reason and a 0-100 priority.
The code only enforces *facts* (see validate): product exists and is pitchable, not already held, amount within published limits.
If the model fails or breaks a rule three times, the client falls back to the rule-based pitch and is marked source="rules".

Run:  python -m app.suggest_llm [--limit N]
"""
from __future__ import annotations

import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import delete, select

from . import audit, catalogue, config, knowledge, llm
from . import models as m
from .db import SessionLocal
from .readers import ClientReader

KINDS = {"lending", "cross_sell", "retention", "none"}

TASK = """You are the pitch-decision engine for a bank Relationship Manager (RM).
Below is the bank's knowledge page, then you will receive ONE client's data as JSON.
Decide the single best thing for the RM to do with this client right now.

Return ONLY a JSON object:
{
  "kind": "lending" | "cross_sell" | "retention" | "none",
  "product": "<exact name from section 2 'Allowed products', or null>",
  "amount_aed": <number or null>,
  "why": "<1-2 sentences for the RM, citing this client's own numbers>",
  "next_action": "<one concrete next step for the RM, max 20 words>",
  "opportunity": <integer 0-40>,
  "signal": <integer 0-30>,
  "fit": <integer 0-30>
}

How to decide:
- "lending" or "cross_sell": pick a product only if this client's data supports it. Use the client's own situation: industry, turnover, POS volume trend, limit use, balance, risk segment, synthetic score, dormancy, products held, the supplied NTB candidates, and the product notes in the knowledge page. Different clients should get different products and reasons where their data differs.
- "retention": protect the relationship. Use it ONLY when `attention_signal_codes` contains "dormant", "decline_30d" or "decline_6m" (dormant terminals or falling volume). A "rate_review" or "idle_balance" signal on its own is NOT a reason for retention: do not recommend giving away margin without a behavioural reason. With no such signal choose lending, cross_sell or none. product and amount_aed must be null.
- "none": nothing worth pitching. product and amount_aed must be null.
- Choose the product ONLY from `pitchable_products_not_held` (computed for this client: pitchable and not already held). Never suggest a product marked NOT PITCHABLE, one the client already holds, or a name not in section 2.
- Amounts: only for sized lending products (Working capital facility, Small Business Loan, Merchant Loan (POS)). The amount must not exceed the client's `suggested_working_capital_limit_aed` and must respect the product's published minimum/maximum. For every other product amount_aed must be null.
- Use only numbers that appear in the client data or the knowledge page. Never invent rates, fees or amounts. If rate_change_recommended is false, do not quote a suggested rate.
- why: 1-2 sentences that cite at least TWO of this client's own numbers (e.g. turnover, volume change, limit used, balance, tenure, rate) and say why THIS product fits THIS client's industry and situation. Do not write a generic sentence that could apply to any client.
- The priority is the SUM of three integer parts that you give separately, each judged against the 150-client portfolio. `peer_percentile` (0-100; 50 is a typical client) shows where this client sits among all clients, so use it to anchor size:
    opportunity 0-40: value at stake. Anchor on peer_percentile (turnover, supplied limit, balance): roughly 0.4 x the percentile for a client with a clear product fit, lower if there is nothing to pitch.
    signal 0-30: how clearly THIS client's own data (attention signals, volume trend, limit use, idle balance, dormancy) points to the action now. 0-5 when nothing points to it; 25-30 only when several signals agree.
    fit 0-30: how well the product, or the retention action, matches the client's industry, risk segment, synthetic score and products held.
  Do not default to round numbers or a middle value. Clients differ, so spread the parts widely. Retention and none still get parts reflecting urgency and opportunity.
"""


def _pct(x):
    return None if x is None else round(x * 100, 1)


def build_payload(session, merchant_id: str) -> dict:
    r = ClientReader(session, merchant_id)
    d = r.detail()
    c, b, p = d["profile"], d["behaviour"], d["priority"]
    mix = {x["type"]: x["pct"] for x in d["card_mix"]}
    return {
        "merchant_id": d["merchant_id"], "name": d["name"], "industry": d["industry"], "city": d["city"],
        "package": c["segment"], "business_type": c["business_type"], "tenure_months": c["tenure_months"],
        "account_balance_aed": c["balance_aed"], "avg_monthly_turnover_aed": c["avg_monthly_turnover_aed"],
        "risk_segment": c["risk_segment"], "synthetic_credit_score": c["synthetic_credit_score"],
        "pos_terminals": d["card_pos"]["num_pos_terminals"], "card_product": d["card_pos"]["card_type"],
        "monthly_pos_limit_aed": d["card_pos"]["monthly_pos_limit_aed"], "daily_pos_limit_aed": d["card_pos"]["daily_pos_limit_aed"],
        "pos_last_30d": {
            "volume_aed": d["card_pos"]["volume_t30"], "transactions": d["card_pos"]["txn_t30"],
            "volume_change_vs_prior_30d_pct": _pct(b["volume_change_t30_vs_p30"]),
            "volume_change_6m_pct": _pct(b["volume_change_m6"]),
            "monthly_limit_used_pct": _pct(d["card_pos"]["monthly_limit_utilisation"]),
            "peak_day_pct_of_daily_limit": _pct(b["daily_limit_utilisation_t30"]),
            "dormant_streak_days": b["dormant_streak_days"], "avg_ticket_aed": round(b["avg_ticket_t30"]) if b["avg_ticket_t30"] else None,
            "chargeback_ratio_pct": None if b["chargeback_ratio_t30_pct"] is None else round(b["chargeback_ratio_t30_pct"], 2),
            "card_mix_pct": mix,
        },
        "monthly_volume_aed_last_6_complete_months": {x["month_key"]: round(x["volume_aed"]) for x in d["volume_bars"]},
        "rate": {"tier": d["rate"]["tier"], "current_rate_pct": d["rate"]["current_pct"],
                 "rate_change_recommended": d["rate"]["change_recommended"],
                 "suggested_rate_pct": d["rate"]["suggested_pct"] if d["rate"]["change_recommended"] else None,
                 "rate_rationale": d["rate"]["rationale"]},
        "suggested_working_capital_limit_aed": d["lending"]["suggested_working_capital_limit_aed"],
        "opportunity_label": d["lending"]["opportunity_label"], "opportunity_tier": d["lending"]["opportunity_tier"],
        "products_held": c["existing_products"], "ntb_candidates": d["ntb_candidates"],
        "pitchable_products_not_held": [x for x in sorted(catalogue.PITCHABLE) if not holds(c["existing_products"], x)],
        "attention_score": p["score"], "attention_reason": p["reason"], "attention_signals": [x["text"] for x in p["signals"]],
        "attention_signal_codes": [x["code"] for x in p["signals"]],
    }


def holds(held, product: str) -> bool:
    """True if the client already has `product`. Held-product names in the data are sometimes shorter than catalogue names."""
    return catalogue.holds(held, product)


def add_peer_percentiles(payloads: dict[str, dict]) -> None:
    """Add `peer_percentile` (0-100 rank of each client among all clients) so the model can anchor 'size' without guessing."""
    cols = {"turnover": lambda p: p["avg_monthly_turnover_aed"], "balance": lambda p: p["account_balance_aed"],
            "supplied_limit": lambda p: p["suggested_working_capital_limit_aed"], "volume_last_30d": lambda p: p["pos_last_30d"]["volume_aed"] or 0}
    ranked = {k: sorted(f(p) or 0 for p in payloads.values()) for k, f in cols.items()}
    n = len(payloads)
    for p in payloads.values():
        p["peer_percentile"] = {k: round(100 * sum(1 for v in ranked[k] if v < (f(p) or 0)) / n) for k, f in cols.items()}


RETENTION_CODES = {"dormant", "decline_30d", "decline_6m"}   # behavioural signals that justify a retention action


def validate(raw: dict, payload: dict) -> tuple[dict | None, str]:
    """Factual validation only. Returns (clean decision, note) or (None, reason it was rejected)."""
    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in KINDS:
        return None, f"bad kind {raw.get('kind')!r}"
    why = str(raw.get("why") or "").strip()
    if len(why) < 10:
        return None, "missing why"
    try:
        parts = [raw.get(k) for k in ("opportunity", "signal", "fit")]
        if all(v is not None for v in parts):          # the priority is the sum of the three parts, so it is explainable
            priority = sum(max(0.0, min(hi, float(v))) for v, hi in zip(parts, (40, 30, 30)))
        else:
            priority = max(0, min(100, float(raw.get("priority"))))
    except (TypeError, ValueError):
        return None, "bad priority"
    codes = payload.get("attention_signal_codes")
    if kind == "retention" and codes is not None and not (RETENTION_CODES & set(codes)):
        return None, ("retention needs dormant terminals or falling volume; a rate review or idle balance alone is not enough, "
                      "choose lending, cross_sell or none")
    nxt = str(raw.get("next_action") or "").strip()[:240] or None
    product, amount, note = raw.get("product"), raw.get("amount_aed"), ""
    if kind in ("retention", "none"):
        product, amount = None, None
    else:
        if product not in catalogue.PITCHABLE:
            return None, f"product {product!r} is not an allowed pitchable product"
        spec = catalogue.BY_NAME[product]
        if spec.kind != kind:
            return None, f"{product} is {spec.kind}, model said {kind}"
        if holds(payload["products_held"], product):
            return None, f"client already holds {product}"
        ok, amount, note = catalogue.validate_amount(product, amount, payload["suggested_working_capital_limit_aed"])
        if not ok:
            return None, note
    return dict(kind=kind, product=product, amount_aed=amount, why=why, next_action=nxt, priority=priority), note


def _ask(system: str, payload: dict, previous_error: str | None = None) -> dict:
    user = "CLIENT DATA:\n" + json.dumps(payload, default=str)
    if previous_error:
        user += f"\n\nYour previous answer was rejected: {previous_error}. Return a corrected JSON object."
    text = llm.complete(system, [{"role": "user", "content": user}], json_mode=True, max_tokens=500, timeout=60,
                        model=config.SUGGESTION_MODEL or None)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def decide(system: str, payload: dict) -> tuple[dict | None, str]:
    """Ask the model; retry rate-limit/transport errors with backoff, and a rejected answer up to twice more, each time with the rejection reason."""
    err, rejected = None, 0
    for attempt in range(8):
        try:
            raw = _ask(system, payload, err if rejected else None)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:200]
            rate_limited = "RateLimit" in type(e).__name__ or "429" in str(e)
            time.sleep(min(30, (3 if rate_limited else 1) * 2 ** min(attempt, 4)) + random.random())
            continue
        clean, note = validate(raw, payload)
        if clean:
            return clean, note
        err, rejected = note, rejected + 1
        if rejected >= 3:
            break
    return None, err or "unknown"


def _rules_row(session, merchant_id: str, reason: str, now) -> dict:
    p = session.get(m.ClientPriority, merchant_id)
    kind = {"Lending": "lending", "Cross-sell": "cross_sell"}.get(p.pitch_kind or "", "none")
    held = session.scalars(select(m.ClientProduct.product).where(m.ClientProduct.merchant_id == merchant_id)).all()
    if p.pitch_title and catalogue.holds(held, p.pitch_title):     # the supplied candidate list can name a product the client already has
        return dict(merchant_id=merchant_id, source="rules", model=None, kind="none", product=None, amount_aed=None,
                    why=f"No pitch: the rule-based candidate ({p.pitch_title}) is already held by this client.", next_action=p.rec_title,
                    priority=p.score, note=f"rule-based fallback ({reason}); candidate already held", generated_at=now)
    return dict(merchant_id=merchant_id, source="rules", model=None, kind=kind, product=p.pitch_title, amount_aed=p.pitch_amount_aed,
                why=p.pitch_why or p.reason, next_action=p.rec_title, priority=p.score,
                note=f"rule-based fallback ({reason})", generated_at=now)


def generate_all(limit: int | None = None, workers: int = 4, verbose: bool = True) -> dict:
    if not llm.configured():
        raise RuntimeError("No LLM configured (set LLM_PROVIDER and its API key in backend/.env)")
    system = TASK + "\n\n=== KNOWLEDGE PAGE ===\n" + knowledge.text()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as s:
        all_ids = list(s.scalars(select(m.Client.merchant_id).order_by(m.Client.merchant_id)))
        payloads = {mid: build_payload(s, mid) for mid in all_ids}
        add_peer_percentiles(payloads)          # percentiles are over the whole portfolio, even when only some clients are decided
        ids = all_ids[:limit] if limit else all_ids

    def work(mid):
        return mid, decide(system, payloads[mid])

    rows, ok, fb, notes = [], 0, 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(work, ids))
    with SessionLocal() as s, s.begin():
        s.execute(delete(m.ClientSuggestion).where(m.ClientSuggestion.merchant_id.in_(ids)))
        for mid, (clean, note) in results:
            if clean:
                ok += 1
                notes += bool(note)
                rows.append(dict(merchant_id=mid, source="llm", model=config.SUGGESTION_MODEL or config.LLM_MODEL, note=note or None, generated_at=now, **clean))
            else:
                fb += 1
                rows.append(_rules_row(s, mid, note, now))
        s.bulk_insert_mappings(m.ClientSuggestion, rows)
    for r in rows:  # one audit line per decision: who decided (llm or rules), what, and any validation note
        audit.record("suggestion", merchant_id=r["merchant_id"], source=r["source"], model=r.get("model"), kind=r["kind"],
                     product=r.get("product"), amount_aed=r.get("amount_aed"), priority=r.get("priority"), note=r.get("note"))
    out = dict(clients=len(ids), llm=ok, rules_fallback=fb, amount_notes=notes, model=config.SUGGESTION_MODEL or config.LLM_MODEL)
    if verbose:
        kinds = {}
        for r in rows:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        prods = {}
        for r in rows:
            if r["product"]:
                prods[r["product"]] = prods.get(r["product"], 0) + 1
        print(f"Suggestions generated: {out}\n  kinds={kinds}\n  products={prods}")
    return out


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    knowledge.write()
    generate_all(limit=lim)
