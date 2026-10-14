"""Merchant segments, built one step at a time. Step 1: high-value churn risk. Step 2: cross-sell targets. Step 3: top performers.

A segment is a reason for the RM to act, and it comes from the data, never from a model. Rules decide who is in a segment and how they
are ranked, so the list can be checked against the figures. The AI suggestion engine (suggest_llm.py) is given the segment and writes
the recommended step; where it has not decided, the rule-based wording in suggest_llm._segment_decision is shown instead.

CHURN RISK: a merchant is at risk when any one of these holds.
  * its POS terminals are inactive now (a stand-in for missed order cycles: the data has card activity, not orders);
  * its card volume over the last 30 days is down 10% or more against the prior 30 days (a sudden drop);
  * its card volume over the last 30 days is 15% or more below its own average over the earlier complete months (its historical baseline)
    and is not rising: a merchant already recovering against the prior 30 days is not an act-now case.
HIGH VALUE: estimated monthly merchant revenue (average monthly turnover times the current rate; an estimate, not booked revenue) in the
top two thirds of the portfolio. The rate is synthetic, so the revenue figures are illustrative.
RANKING: estimated monthly revenue lost against the merchant's own baseline, largest first, so a large merchant that has collapsed ranks
above a large one with a mild dip and above a small one that has collapsed.

GROWTH-READY: a merchant that is not a churn risk and is either growing (card volume up 10% or more against the prior 30 days) or close
to a volume ceiling (using 70% or more of its monthly POS limit). It is a signal that a merchant is ready for more, and it is used to
explain and rank cross-sell targets and to brief the AI engine. It does NOT decide who is a cross-sell target.

CROSS-SELL TARGET (step 2): a merchant that is not a churn risk and does not yet hold a product the bank can offer it: a supplied
new-to-bank candidate it does not already hold, or a cross-sell product the AI engine chose for it. Ranked by estimated monthly
revenue plus any growth in that revenue since the prior 30 days, so a growing merchant is lifted by the amount it has actually grown.
A merchant that also qualifies for a working-capital facility shows it as a second line, never as the headline. The data holds no
structured package-upgrade rules (the package minimum balances are text), so premium-tier upgrades are not part of this step.

TOP PERFORMER (step 3): one of the merchants driving the bulk of the portfolio's card volume: the top 10% by card volume over the last 30
days. Card volume is used and not average monthly turnover because the supplied turnover has ties (nine merchants share the same figure),
which would make the ranking arbitrary. A top performer can also be a churn risk or growth-ready; the codes then list both, and a top
performer who is a churn risk needs retention first. Each carries its share of the portfolio's card volume and of its own city's. The
data holds no record of when the RM last spoke to a merchant, so the segment cannot say who is overdue for a check-in.

The thresholds are policy parameters set against the demonstration data and need product sign-off before real use.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import scoring

LABELS = {"churn_risk": "High-value churn risk", "growth_ready": "Growth-ready cross-sell target", "top_performer": "Top performer"}
VOLUME_DROP = scoring.DECLINE_T30      # -0.10: volume down 10% or more against the prior 30 days
BASELINE_DROP = -0.15                  # 15% or more below the merchant's own earlier average
GROWTH_VOLUME_UP = scoring.GROWTH_T30             # +0.10: card volume up 10% or more against the prior 30 days
LIMIT_USED = scoring.LIMIT_PRESSURE_MONTHLY       # 0.70: using 70% or more of the monthly POS limit
TOP_PERFORMER_SHARE = 0.10                        # the top 10% of merchants by card volume over the last 30 days
BASELINE_MONTHS, MIN_BASELINE_MONTHS = 6, 3
ACT_NOW = 5
DEFINITION = ("Terminals inactive now, or card volume down 10% or more against the prior 30 days, or 15% or more below the merchant's own "
              "earlier monthly average and not rising. High value means the top two thirds by estimated monthly revenue (turnover times rate, an estimate). "
              "Ranked by estimated monthly revenue lost against the merchant's own baseline.")


TOP_PERFORMER_DEFINITION = ("The top 10% of merchants by card volume over the last 30 days, which is where most of the portfolio's volume sits. Card volume "
                            "is used because the supplied turnover has ties. Shown with each merchant's share of the portfolio's card volume and of its "
                            "own city's. There is no record of when the RM last spoke to a merchant, so the list cannot say who is overdue for a check-in.")
DORMANT_DEFINITION = ("Terminals inactive now (6 to 24 days in the data). The brief's 30 to 90 days is not used because no merchant has been inactive that long. "
                      "Ranked by the merchant's own earlier monthly card volume, the nearest figure we have to historical value (it is not true lifetime value).")
CROSS_SELL_DEFINITION = ("Not a churn risk, and does not yet hold a product we can offer: a supplied new-to-bank candidate it does not already hold, "
                         "or a cross-sell the AI engine chose. Ranked by estimated monthly revenue plus any growth in that revenue since the prior 30 "
                         "days. A merchant that also qualifies for a working-capital facility shows it as a second line.")


def _tiers(revenue: dict[str, float]) -> dict[str, str]:
    """High, Medium and Low value: thirds of the portfolio by estimated monthly revenue."""
    order = sorted(revenue, key=lambda k: (-revenue[k], k))
    third = math.ceil(len(order) / 3)
    return {mid: ("High" if i < third else "Medium" if i < 2 * third else "Low") for i, mid in enumerate(order)}


def assign(session: Session) -> dict[str, dict]:
    """The segment facts for every client, keyed by merchant id. `codes` lists the segments the client is in (today only "churn_risk")."""
    clients = {c.merchant_id: c for c in session.scalars(select(m.Client))}
    facts = {f.merchant_id: f for f in session.scalars(select(m.ClientFact))}
    months: dict[str, list[float]] = defaultdict(list)
    for r in session.scalars(select(m.ClientMonthlyVolume).where(m.ClientMonthlyVolume.is_complete).order_by(m.ClientMonthlyVolume.month)):
        months[r.merchant_id].append(r.volume_aed)

    revenue = {mid: c.avg_monthly_turnover_aed * c.current_rate_pct / 100 for mid, c in clients.items()}
    tier = _tiers(revenue)
    by_turnover = sorted(clients, key=lambda k: (-clients[k].avg_monthly_turnover_aed, k))
    total_turnover = sum(c.avg_monthly_turnover_aed for c in clients.values()) or 1.0
    by_volume = sorted(clients, key=lambda k: (-(facts[k].volume_t30 or 0.0), k))
    total_volume = sum((facts[k].volume_t30 or 0.0) for k in clients) or 1.0
    city_volume: dict[str, float] = defaultdict(float)
    for k, c in clients.items():
        city_volume[c.city] += facts[k].volume_t30 or 0.0
    top_n = math.ceil(len(clients) * TOP_PERFORMER_SHARE)

    out: dict[str, dict] = {}
    for mid, c in clients.items():
        f = facts[mid]
        v30, p30, rate = f.volume_t30 or 0.0, f.volume_p30 or 0.0, c.current_rate_pct
        chg = f.volume_change_t30_vs_p30
        history = months[mid][:-1][-BASELINE_MONTHS:]       # the earlier complete months; the latest one overlaps the last 30 days
        baseline = sum(history) / len(history) if len(history) >= MIN_BASELINE_MONTHS else None
        vs_base = v30 / baseline - 1 if baseline else None
        reasons = []
        if f.is_dormant_now:
            reasons.append(f"No card activity: POS terminals inactive for {f.dormant_streak_days} days")
        if chg is not None and chg <= VOLUME_DROP:
            reasons.append(f"Card volume down {abs(chg) * 100:.0f}% against the prior 30 days")
        if vs_base is not None and vs_base <= BASELINE_DROP and (chg is None or chg <= 0):
            reasons.append(f"Card volume {abs(vs_base) * 100:.0f}% below its own average of the earlier {len(history)} months")
        util = f.monthly_limit_utilisation_t30
        growth = []
        if chg is not None and chg >= GROWTH_VOLUME_UP:
            growth.append(f"Card volume up {chg * 100:.0f}% against the prior 30 days")
        if util is not None and util >= LIMIT_USED:
            growth.append(f"Using {util * 100:.0f}% of its monthly POS limit")
        volume_rank = by_volume.index(mid) + 1
        out[mid] = dict(
            codes=(["churn_risk"] if reasons else ["growth_ready"] if growth else []) + (["top_performer"] if volume_rank <= top_n else []),
            reasons=reasons,
            growth_reasons=growth if not reasons else [],
            monthly_revenue_aed=round(revenue[mid]),
            value_tier=tier[mid],
            turnover_rank=by_turnover.index(mid) + 1,
            city=c.city,
            volume_30d_aed=round(v30),
            volume_rank=volume_rank,
            volume_share_pct=round(100 * v30 / total_volume, 1),
            city_volume_share_pct=round(100 * v30 / (city_volume[c.city] or 1.0), 1),
            clients_in_portfolio=len(clients),
            portfolio_share_pct=round(100 * c.avg_monthly_turnover_aed / total_turnover, 1),
            revenue_change_vs_prior_30d_aed=round((v30 - p30) * rate / 100),
            volume_change_vs_prior_30d_pct=None if chg is None else round(chg * 100, 1),
            dormant_days=f.dormant_streak_days,
            dormant_now=bool(f.is_dormant_now),
            earlier_monthly_volume_aed=round(baseline) if baseline else 0,
            baseline_months=len(history) if baseline else 0,
            volume_vs_baseline_pct=None if vs_base is None else round(vs_base * 100, 1),
            revenue_gap_vs_baseline_aed=round((baseline - v30) * rate / 100) if baseline else 0,
        )
    return out


def growth_ready(assigned: dict[str, dict]) -> set[str]:
    """Merchant ids that are growth-ready (not a churn risk, and growing or close to their POS limit)."""
    return {mid for mid, s in assigned.items() if "growth_ready" in s["codes"]}


def high_value_churn(assigned: dict[str, dict], limit: int = ACT_NOW) -> tuple[list[tuple[str, dict]], int, int]:
    """(the top `limit` high-value churn risks, how many merchants are at risk, how many of those are high value). Ranked by revenue lost
    against the merchant's own baseline, then by merchant id so the order is stable."""
    at_risk = [(mid, s) for mid, s in assigned.items() if "churn_risk" in s["codes"]]
    valuable = [(mid, s) for mid, s in at_risk if s["value_tier"] != "Low"]
    valuable.sort(key=lambda t: (-t[1]["revenue_gap_vs_baseline_aed"], t[0]))
    return valuable[:limit], len(at_risk), len(valuable)


def top_performers(assigned: dict[str, dict], limit: int = ACT_NOW) -> tuple[list[tuple[str, dict]], int]:
    """(the top `limit` merchants by card volume among the top performers, how many top performers there are)."""
    tops = sorted(((mid, s) for mid, s in assigned.items() if "top_performer" in s["codes"]), key=lambda t: (t[1]["volume_rank"], t[0]))
    return tops[:limit], len(tops)


def dormant_targets(assigned: dict[str, dict], limit: int = ACT_NOW) -> tuple[list[tuple[str, dict]], int]:
    """(the top `limit` merchants with inactive terminals now, ranked by earlier monthly card volume, how many are inactive)."""
    dorm = [(mid, s) for mid, s in assigned.items() if s["dormant_now"]]
    dorm.sort(key=lambda t: (-t[1]["earlier_monthly_volume_aed"], t[0]))
    return dorm[:limit], len(dorm)
