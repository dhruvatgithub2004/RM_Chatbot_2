"""Prioritisation + recommendations.

Two separate things live here, both deterministic and both built only from supplied/computed data:

1. ATTENTION SCORE  - ranks clients on the dashboard and produces the one-line reason. Rule-based on the
   base facts (dormancy, volume trend, limit pressure, idle balance, risk segment, rate review).
2. PITCH            - what to offer (Suggestions screen). Lending uses the supplied
   `suggested_working_capital_limit_aed`; cross-sell uses the supplied NTB candidate file. Nothing is
   estimated or invented.

Thresholds are *policy parameters* calibrated against the real distributions in the loaded data
(see BLOCKERS_AND_PENDING_INPUTS.md - they need product sign-off).
"""
from __future__ import annotations

import pandas as pd

from . import rates

# ── policy parameters ───────────────────────────────────────────────────────
FLAG_THRESHOLD = 30.0               # score >= this => "flagged for attention" / "Opportunity"
DECLINE_T30 = -0.10                 # volume change vs prior 30d at/below which decline is a signal
DECLINE_M6 = -0.15                  # 6-month trend at/below which a sustained decline is a signal
GROWTH_T30 = 0.10                   # volume change vs prior 30d at/above which growth is a signal
LIMIT_PRESSURE_MONTHLY = 0.70       # share of monthly POS limit used in last 30 days
IDLE_BALANCE_RATIO = 0.50           # account balance / avg monthly turnover
RATE_REVIEW_POINTS = 10.0           # points when the supplied data recommends a rate change
RISK_POINTS = {"High": 15.0, "Medium": 5.0, "Low": 0.0}
# Pitch rules
WC_MIN_FACILITY_AED = 250_000       # smallest working-capital facility per the bank's published page
PITCH_EXCLUDE_RISK = {"High"}       # no lending pitch to High risk segment clients
# (also no lending pitch while terminals are dormant)


def aed(n: float) -> str:
    n = float(n)
    if abs(n) >= 1_000_000:
        return f"AED {n / 1_000_000:.1f}M"
    if abs(n) >= 10_000:
        return f"AED {n / 1_000:.0f}k"
    return f"AED {n:,.0f}"


def aed_full(n: float) -> str:
    return f"AED {float(n):,.0f}"


def pct(x: float, digits: int = 0) -> str:
    return f"{abs(x) * 100:.{digits}f}%"


def _signals(c: dict, f: dict) -> list[dict]:
    """Return signals as {code, points, kind, text}. kind: risk | opportunity."""
    s: list[dict] = []
    dormant = bool(f.get("is_dormant_now"))
    chg = f.get("volume_change_t30_vs_p30")
    if dormant:
        n = f["dormant_streak_days"]
        extra = f" — volume down {pct(chg)} vs prior 30 days" if chg is not None and chg < 0 else ""
        s.append(dict(code="dormant", kind="risk", points=40 + min(n, 24) / 24 * 10,
                      text=f"POS terminals dormant for {n} days{extra}"))
    elif chg is not None and chg <= DECLINE_T30:
        s.append(dict(code="decline_30d", kind="risk", points=min(40.0, abs(chg) * 100),
                      text=f"Volume down {pct(chg)} vs prior 30 days"))
    m6 = f.get("volume_change_m6")
    if not dormant and m6 is not None and m6 <= DECLINE_M6:
        s.append(dict(code="decline_6m", kind="risk", points=10.0,
                      text=f"Volume down {pct(m6)} over the last 6 months"))
    util = f.get("monthly_limit_utilisation_t30")
    if util is not None and util >= LIMIT_PRESSURE_MONTHLY:
        s.append(dict(code="limit_pressure", kind="opportunity", points=min(25.0, 15 + (util - LIMIT_PRESSURE_MONTHLY) / 0.10 * 10),
                      text=f"Using {pct(util)} of monthly POS limit — nearing limit"))
    bal = f.get("balance_to_turnover")
    if bal is not None and bal >= IDLE_BALANCE_RATIO:
        s.append(dict(code="idle_balance", kind="opportunity", points=min(20.0, 10 + (bal - IDLE_BALANCE_RATIO) / 0.10 * 10),
                      text=f"Idle balance {aed(c['account_balance_aed'])} ({pct(bal)} of monthly turnover)"))
    if not dormant and chg is not None and chg >= GROWTH_T30:
        s.append(dict(code="growth_30d", kind="opportunity", points=10.0,
                      text=f"Volume up {pct(chg)} vs prior 30 days"))
    if c.get("rate_change_recommended"):
        s.append(dict(code="rate_review", kind="opportunity", points=RATE_REVIEW_POINTS,
                      text=rates.review_text(c["current_rate_pct"], c["suggested_rate_pct"])))
    rp = RISK_POINTS.get(c["risk_segment"], 0.0)
    if rp:
        s.append(dict(code="risk_segment", kind="risk", points=rp, text=f"{c['risk_segment']} risk segment"))
    return s


def _action(c: dict, f: dict, sigs: list[dict]):
    """Primary RM action from the strongest signal that maps to one (no product names are invented)."""
    by = {x["code"]: x for x in sigs}
    chg, m6, util = f.get("volume_change_t30_vs_p30"), f.get("volume_change_m6"), f.get("monthly_limit_utilisation_t30")
    cands = []
    if "dormant" in by:
        cands.append((by["dormant"]["points"], "Activation", "POS terminal reactivation",
                      f"Terminals dormant for {f['dormant_streak_days']} days and volume is down {pct(chg or 0)} vs the prior 30 days — "
                      f"restore card acceptance before the relationship erodes."))
    if "decline_30d" in by:
        tail = f" and {pct(m6)} over 6 months" if "decline_6m" in by and m6 is not None else ""
        cands.append((by["decline_30d"]["points"], "Retention", "Relationship review call",
                      f"Volume is down {pct(chg or 0)} vs the prior 30 days{tail}; understand the cause before any pricing action."))
    if "limit_pressure" in by:
        peak = f.get("daily_limit_utilisation_t30")
        cands.append((by["limit_pressure"]["points"], "Limit", "POS limit increase",
                      f"Last-30-day volume is {pct(util or 0)} of the AED {c['monthly_pos_limit_aed']:,.0f} monthly POS limit"
                      + (f"; peak day reached {pct(peak)} of the daily limit." if peak is not None else ".")))
    if not cands:
        return None, None, None, 0.0
    pts, cat, title, why = max(cands, key=lambda x: x[0])
    return cat, title, why, pts


def _pitch(c: dict, f: dict, ntb_rows: list[dict]):
    """What to offer. Lending from the supplied working-capital limit; otherwise the first supplied NTB candidate."""
    wc = float(c["suggested_working_capital_limit_aed"])
    lending_ok = wc >= WC_MIN_FACILITY_AED and not f.get("is_dormant_now") and c["risk_segment"] not in PITCH_EXCLUDE_RISK
    if lending_ok:
        why = (f"{c['opportunity_label']} opportunity (tier {c['opportunity_tier']}): average monthly turnover "
               f"{aed_full(c['avg_monthly_turnover_aed'])}, {c['risk_segment']} risk segment, synthetic score {c['synthetic_credit_score']}; "
               f"suggested working-capital limit {aed_full(wc)}.")
        return "Lending", "Working capital facility", why, wc
    if ntb_rows:
        r = ntb_rows[0]
        return "Cross-sell", r["candidate_product"], r["rationale"], None
    return None, None, None, None


def score_all(merchants: pd.DataFrame, facts: list[dict], monthly_df: pd.DataFrame,
              held: pd.DataFrame, ntb: pd.DataFrame) -> list[dict]:
    fx = {f["merchant_id"]: f for f in facts}
    ntb_by: dict[str, list[dict]] = {}
    for r in ntb.to_dict("records"):
        ntb_by.setdefault(r["merchant_id"], []).append(dict(candidate_product=r["candidate_product"], rationale=r["rationale"]))
    out = []
    for c in merchants.to_dict("records"):
        f = fx[c["merchant_id"]]
        ntb_rows = ntb_by.get(c["merchant_id"], [])
        if not c.get("has_pos_data", True):
            out.append(dict(merchant_id=c["merchant_id"], score=0.0, flagged=False, reason="No POS data on file", signals=[],
                            rec_category=None, rec_title=None, rec_why=None, rec_points=0.0,
                            pitch_kind=None, pitch_title=None, pitch_why=None, pitch_amount_aed=None, ntb=ntb_rows))
            continue
        sigs = _signals(c, f)
        score = min(100.0, round(sum(x["points"] for x in sigs), 1))
        sigs_sorted = sorted(sigs, key=lambda x: -x["points"])
        primary = [x for x in sigs_sorted if x["code"] != "risk_segment"]
        if primary:
            reason = primary[0]["text"]
            if c["risk_segment"] == "High":
                reason += " · High risk segment"
        elif c["risk_segment"] == "High":
            reason = "High risk segment — no other attention signals"
        else:
            reason = "Stable — no attention signals"
        cat, title, why, pts = _action(c, f, sigs_sorted)
        pk, pt, pw, pa = _pitch(c, f, ntb_rows)
        out.append(dict(merchant_id=c["merchant_id"], score=score, flagged=score >= FLAG_THRESHOLD, reason=reason,
                        signals=[dict(code=x["code"], kind=x["kind"], points=round(x["points"], 1), text=x["text"]) for x in sigs_sorted],
                        rec_category=cat, rec_title=title, rec_why=why, rec_points=round(pts, 1),
                        pitch_kind=pk, pitch_title=pt, pitch_why=pw, pitch_amount_aed=pa, ntb=ntb_rows))
    out.sort(key=lambda r: (-r["score"], r["merchant_id"]))
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return out
