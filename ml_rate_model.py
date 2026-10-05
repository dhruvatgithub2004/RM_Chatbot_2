"""
ml_rate_model.py -- Merchant rate suggestion: real Visa interchange + ML-predicted spread
=========================================================================================

WHAT THIS FILE DOES (read this first)
-------------------------------------
For each of the 150 merchants it produces a SUGGESTED MERCHANT RATE (MDR) as:

    suggested_rate_pct = blended_interchange_pct  +  predicted_spread_pp

  * blended_interchange_pct  -> REAL. A deterministic calculation (no ML): the Visa UAE
        interchange table (effective 19 Dec 2024) weighted by the merchant's card-type mix,
        with MCC segment overrides and debit caps. Interchange is the acquirer's COST FLOOR;
        merchants do not pay it directly.
  * predicted_spread_pp      -> ML. A Ridge regression predicts the acquirer's spread
        (margin + scheme fees + processing) from 7 merchant features. It is trained on a
        SYNTHETIC historical cohort (800 rows) because real negotiated rates are not public.

The regression is linear on purpose: every prediction decomposes EXACTLY into
    interchange + base spread (intercept) + one contribution per feature + small adjustment
so an RM can see a "waterfall" explaining the rate (output: merchant_rate_waterfall_v1.csv).

REAL vs SYNTHETIC -- keep these labels intact in any UI / copilot text
----------------------------------------------------------------------
  REAL        : Visa interchange rates, MCC overrides, debit caps.
  ASSUMPTION  : all volume is Visa; card_type -> Visa product mapping (RATE dict below);
                debit cap applied to the day's average ticket (approximation).
  SYNTHETIC   : the historical cohort, the "hidden pricing function" that generates its
                spreads, current_rate_pct, scheme fees / acquirer margin.
  => Holdout R^2 (~0.88) is high BY CONSTRUCTION (the model recovers the synthetic rule).
     It is NOT evidence of real-world accuracy. Always label rates "illustrative".

HOW TO RETRAIN ON REAL BANK DATA (production path)
--------------------------------------------------
Replace section 3 (synthetic cohort) with the bank's historical merchants:
  features (same 7 columns) + the realised spread
  (actual negotiated MDR - interchange - scheme fees). Sections 4-5 stay unchanged.

INPUTS  (OUT directory, default below; override with argv[1])
  merchant_profiles_v3.csv        merchant master (needs mcc_code, current_rate_pct, ...)
  pos_daily_acquiring_v3.csv      daily POS rows incl. card_type (Mass/Premium/Super Premium/Business/Debit)
  working_capital_facilities_v2.csv   facilities (for leverage feature)

OUTPUTS (written to OUT)
  merchant_rate_history_v1.csv    synthetic training cohort
  rate_model_metrics.json         holdout R^2 / MAE, coefficients, assumptions
  merchant_rate_waterfall_v1.csv  per-merchant exact rate decomposition
  merchant_profiles_v3.csv        UPDATED IN PLACE: only the columns in NEW + OVER lists below
                                  (current_rate_pct, rate_tier and all other columns untouched)

RUN:  python3 ml_rate_model.py [path/to/structured_data]
DEPENDENCIES: numpy, pandas, scikit-learn
"""

import json
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

OUT = sys.argv[1] if len(sys.argv) > 1 else \
    "/sessions/affectionate-youthful-bell/mnt/outputs/RM_chatbot_knowledge/structured_data"

# Fixed seed => the synthetic cohort and therefore the model are fully reproducible.
rng = np.random.default_rng(402)

prof = pd.read_csv(f"{OUT}/merchant_profiles_v3.csv")
pos = pd.read_csv(f"{OUT}/pos_daily_acquiring_v3.csv")
fac = pd.read_csv(f"{OUT}/working_capital_facilities_v2.csv")

# =====================================================================================
# 1. BLENDED INTERCHANGE PER MERCHANT  (deterministic, REAL data -- no ML here)
# =====================================================================================
# Interchange % per project card_type (assumed mapping to Visa products):
#   Debit ~0.80% (blend of 0.75% Classic..Platinum and 1.00% Signature+ debit)
#   Mass  ~ Visa Classic/Gold credit 1.15%     Premium ~ Rewards/Platinum credit 1.80%
#   Super Premium ~ Signature/Infinite credit 2.10%     Business ~ commercial cards 2.05%
RATE = {"Debit": 0.80, "Mass": 1.15, "Premium": 1.80, "Super Premium": 2.10, "Business": 2.05}

# MCC segment programs from the Visa document (override the general rates above):
#   Supermarket (5411): credit/commercial 1.05% (debit keeps the general debit rate)
#   Education (8299) and Real-estate rentals (6513): 0.65% for both debit and credit
SEG = {
    "MCC 5411": {"credit": 1.05},
    "MCC 8299": {"debit": 0.65, "credit": 0.65},
    "MCC 6513": {"debit": 0.65, "credit": 0.65},
}

mcc = pos.merchant_id.map(prof.set_index("merchant_id")["mcc_code"])
is_debit = pos.card_type == "Debit"
rate = pos.card_type.map(RATE).astype(float)
ov_credit = mcc.map({k: v["credit"] for k, v in SEG.items() if "credit" in v})
ov_debit = mcc.map({k: v["debit"] for k, v in SEG.items() if "debit" in v})
rate = rate.where(~(~is_debit & ov_credit.notna()), ov_credit)   # credit-side override
rate = rate.where(~(is_debit & ov_debit.notna()), ov_debit)      # debit-side override

# Debit interchange is capped per transaction (AED 37.50 / 50.00 general, AED 32.50 for
# education & real estate). We only have the day's AVERAGE ticket, so the cap is applied
# to it -- an approximation. 43.75 = midpoint of the two general caps.
cap_aed = np.where(ov_debit.notna(), 32.50, 43.75)
debit_capped = np.minimum(rate, cap_aed / pos.avg_ticket_size_aed * 100)
pos["interchange_pct"] = np.where(is_debit, debit_capped, rate)

# Merchant-level blended interchange = volume-weighted average over all days.
vol = pos.daily_acquiring_volume_aed
blended = (pos.interchange_pct * vol).groupby(pos.merchant_id).sum() / vol.groupby(pos.merchant_id).sum()

# =====================================================================================
# 2. LIVE-BOOK FEATURES  (the 7 model inputs, computed from real generated data)
# =====================================================================================
pos_stats = pos.groupby("merchant_id").agg(
    mean_volume=("daily_acquiring_volume_aed", "mean"),
    std_volume=("daily_acquiring_volume_aed", "std"),
    mean_chargeback=("chargeback_ratio_pct", "mean"))                 # chargeback ratio
pos_stats["volatility_cv"] = (pos_stats["std_volume"] / pos_stats["mean_volume"]).fillna(0)  # volume volatility

premium_share = (pos.assign(p=pos.card_type.isin(["Premium", "Super Premium"]))
                    .groupby("merchant_id").p.mean().rename("premium_card_share"))

# Growth = avg of last 2 FULL months / avg of first 2 FULL months - 1.
# Only the 7 complete calendar months are used (Dec-2025 and Aug-2026 are partial).
p = pos.copy()
p["month"] = pd.to_datetime(p["date"]).dt.to_period("M").astype(str)
FULL = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
monthly = p[p.month.isin(FULL)].groupby(["merchant_id", "month"]).daily_acquiring_volume_aed.sum().unstack(fill_value=0)
growth = (monthly[FULL[-2:]].mean(axis=1) / monthly[FULL[:2]].mean(axis=1) - 1).rename("growth_pct")
growth = growth.replace([np.inf, -np.inf], 0).fillna(0)

# Leverage = outstanding ACTIVE facility balance / avg monthly turnover.
active = fac[fac.status == "Active"].groupby("merchant_id").outstanding_aed.sum()
leverage = (active / prof.set_index("merchant_id")["avg_monthly_turnover_aed"]).rename("leverage_ratio").fillna(0)

live = (prof.set_index("merchant_id")[["avg_monthly_turnover_aed", "risk_segment"]]
        .join(pos_stats[["volatility_cv", "mean_chargeback"]]).join(premium_share)
        .join(growth).join(leverage))
live["risk_num"] = live["risk_segment"].map({"Low": 0, "Medium": 1, "High": 2})
live["log_turnover"] = np.log(live["avg_monthly_turnover_aed"])   # log: turnover is heavy-tailed
live["blended_interchange_pct"] = blended.round(3)

# The 7 model features (order matters: coefficients are aligned to this list).
FEATS = ["log_turnover", "growth_pct", "volatility_cv", "mean_chargeback",
         "premium_card_share", "leverage_ratio", "risk_num"]
# Human-readable names used in rationale text.
LABELS = {"log_turnover": "turnover", "growth_pct": "growth", "volatility_cv": "volume volatility",
          "mean_chargeback": "chargeback ratio", "premium_card_share": "premium-card mix",
          "leverage_ratio": "facility leverage", "risk_num": "risk segment"}

# =====================================================================================
# 3. SYNTHETIC HISTORICAL COHORT  (stand-in for the bank's real negotiated-rate history)
#    <-- REPLACE THIS SECTION with real historical data to retrain in production.
# =====================================================================================
N = 800
# Feature values: bootstrap from the live merchants' empirical values + small noise, so the
# cohort looks like the same population. NOTE: the order of rng calls below is what makes
# the output reproducible -- do not reorder.
hist = pd.DataFrame({f: rng.choice(live[f].values, N) + rng.normal(0, live[f].std() * 0.15, N)
                     for f in FEATS + ["blended_interchange_pct"] if f != "risk_num"})
hist["risk_num"] = rng.choice(live["risk_num"].values, N)
hist["growth_pct"] = hist["growth_pct"].clip(-0.6, 1.5)
for f in ["volatility_cv", "mean_chargeback", "leverage_ratio"]:
    hist[f] = hist[f].clip(lower=0)
hist["premium_card_share"] = hist["premium_card_share"].clip(0, 1)
hist["blended_interchange_pct"] = hist["blended_interchange_pct"].clip(0.5, 2.3)

# HIDDEN PRICING FUNCTION: the made-up "true" process that generates historical spreads.
# The regression below will (by design) recover these weights -- this is why accuracy is
# circular. Signs: bigger/safer/premium merchants get a lower spread; volatile, high-
# chargeback, leveraged, high-risk merchants get a higher spread.
mu, sd = live[FEATS].mean(), live[FEATS].std()
zh = (hist[FEATS] - mu) / sd            # z-scored features
spread = (0.90 + 0.10 * hist["risk_num"] - 0.07 * zh["log_turnover"] - 0.03 * zh["growth_pct"]
          + 0.05 * zh["volatility_cv"] + 0.06 * zh["mean_chargeback"] - 0.04 * zh["premium_card_share"]
          + 0.03 * zh["leverage_ratio"] + rng.normal(0, 0.05, len(hist)))
hist["negotiated_spread_pp"] = spread.clip(0.40, 1.60).round(2)       # spread floor 0.40pp
hist["negotiated_rate_pct"] = (hist["blended_interchange_pct"] + hist["negotiated_spread_pp"]).round(2)
hist["avg_monthly_turnover_aed"] = np.exp(hist["log_turnover"]).round(2)
out_hist = hist.drop(columns="log_turnover").round(4)
out_hist.insert(0, "historical_merchant_id", [f"HIST{i:04d}" for i in range(1, N + 1)])
out_hist["is_synthetic"] = True
out_hist.to_csv(f"{OUT}/merchant_rate_history_v1.csv", index=False)

# =====================================================================================
# 4. TRAIN + EVALUATE THE SPREAD MODEL  (the ML step)
# =====================================================================================
# Target = negotiated_spread_pp. Interchange is NOT a feature: it is added back afterwards
# as a known, deterministic cost.
Xtr, Xte, ytr, yte = train_test_split(hist[FEATS], hist["negotiated_spread_pp"], test_size=0.25, random_state=9)
sc = StandardScaler().fit(Xtr)
m_ = Ridge(alpha=1.0).fit(sc.transform(Xtr), ytr)       # holdout check only
pred_te = m_.predict(sc.transform(Xte))
r2, mae = r2_score(yte, pred_te), mean_absolute_error(yte, pred_te)

# Final model: refit on the FULL cohort. StandardScaler centres features at the cohort mean,
# so model.intercept_ == mean cohort spread (the "base spread" in the waterfall).
sc = StandardScaler().fit(hist[FEATS])
model = Ridge(alpha=1.0).fit(sc.transform(hist[FEATS]), hist["negotiated_spread_pp"])

# =====================================================================================
# 5. PREDICT FOR THE LIVE 150 MERCHANTS
# =====================================================================================
Zl = sc.transform(live[FEATS])                                     # standardised live features
live["predicted_spread_pp"] = np.clip(model.predict(Zl), 0.40, 1.60).round(2)   # clip to floor/cap
live["predicted_rate_pct"] = (live["blended_interchange_pct"] + live["predicted_spread_pp"]).round(2)

cur = prof.set_index("merchant_id")["current_rate_pct"]            # synthetic legacy rate, LOCKED
live["current_rate_pct"] = cur
live["rate_gap_pp"] = (cur - live["predicted_rate_pct"]).round(2)  # >0: merchant pays MORE than model
live["margin_pp"] = (cur - live["blended_interchange_pct"]).round(2)   # current margin over interchange
live["monthly_interchange_cost_aed"] = (live["avg_monthly_turnover_aed"] * live["blended_interchange_pct"] / 100).round(0)

# Direction at +/-0.10pp: Reduce (retention risk), Increase (under-priced), else Hold.
live["rate_change_direction"] = np.select([live.rate_gap_pp >= 0.10, live.rate_gap_pp <= -0.10],
                                          ["Reduce", "Increase"], default="Hold")
live["rate_change_recommended"] = live["rate_change_direction"] != "Hold"
live["suggested_rate_pct"] = live["predicted_rate_pct"]
assert ((live.suggested_rate_pct - live.blended_interchange_pct) >= 0.399).all()   # floor guard

# Per-merchant feature contributions in percentage points: coefficient x standardised value.
# These are what the RM sees as "why" (positive pushes the spread/rate up).
contrib = pd.DataFrame(Zl * model.coef_, index=live.index, columns=FEATS)

def rationale(mid, r):
    """Template (non-LLM) explanation built only from computed numbers."""
    top = contrib.loc[mid].reindex(contrib.loc[mid].abs().sort_values(ascending=False).index)[:2]
    drivers = ", ".join(f"{LABELS[f]} ({v:+.2f}pp)" for f, v in top.items())
    base = (f"Estimated Visa interchange cost {r['blended_interchange_pct']:.2f}% (from this merchant's card mix) "
            f"+ modelled spread {r['predicted_spread_pp']:.2f}pp = {r['predicted_rate_pct']:.2f}%, vs current "
            f"{r['current_rate_pct']:.2f}% (margin over interchange {r['margin_pp']:.2f}pp). ")
    if r["rate_change_direction"] == "Reduce":
        tail = (f"Current rate is {r['rate_gap_pp']:.2f}pp above the modelled rate: retention risk, consider a "
                f"proactive reduction to {r['predicted_rate_pct']:.2f}%.")
    elif r["rate_change_direction"] == "Increase":
        tail = (f"Current rate is {abs(r['rate_gap_pp']):.2f}pp below the modelled rate: under-priced for this card "
                f"mix, review toward {r['predicted_rate_pct']:.2f}% at next renewal.")
    else:
        tail = "Current rate is within 0.10pp of the modelled rate: hold."
    return f"{base}{tail} Main spread drivers: {drivers}. Spread and rates are illustrative."

live["rate_rationale"] = [rationale(m, r) for m, r in live.iterrows()]

# ---------------- exact waterfall: interchange + base + drivers + adjustment = suggested ----
KEY = {"log_turnover": "turnover", "growth_pct": "growth", "volatility_cv": "volatility",
       "mean_chargeback": "chargeback", "premium_card_share": "premium_mix",
       "leverage_ratio": "leverage", "risk_num": "risk"}
wf = pd.DataFrame(index=live.index)
wf["interchange_pct"] = live["blended_interchange_pct"].round(4)
wf["base_spread_pp"] = round(float(model.intercept_), 4)
for f in FEATS:
    wf[f"contrib_{KEY[f]}_pp"] = contrib[f].round(4)
parts = wf["interchange_pct"] + wf["base_spread_pp"] + wf[[c for c in wf.columns if c.startswith("contrib_")]].sum(axis=1)
# adjustment_pp absorbs the spread clip (0.40-1.60) and 2-decimal rounding so the pieces
# add up to the stored suggested rate exactly.
wf["adjustment_pp"] = (live["suggested_rate_pct"] - parts).round(4)
wf["suggested_rate_pct"] = live["suggested_rate_pct"]
wf["current_rate_pct"] = live["current_rate_pct"]
wf["margin_pp"] = live["margin_pp"]
wf["rate_change_direction"] = live["rate_change_direction"]
chk = (wf["interchange_pct"] + wf["base_spread_pp"] + wf[[c for c in wf.columns if c.startswith("contrib_")]].sum(axis=1)
       + wf["adjustment_pp"] - wf["suggested_rate_pct"]).abs().max()
assert chk < 0.0005, chk                                            # sum-check guard
wf["is_illustrative_except_interchange"] = True
wf.reset_index().to_csv(f"{OUT}/merchant_rate_waterfall_v1.csv", index=False)

# ---------------- write results back into the merchant profile (only these columns) ----------
NEW = ["blended_interchange_pct", "monthly_interchange_cost_aed", "margin_pp", "predicted_spread_pp",
       "rate_change_direction"]
OVER = ["suggested_rate_pct", "predicted_rate_pct", "rate_gap_pp", "rate_change_recommended", "rate_rationale"]
prof = prof.set_index("merchant_id")
for c in NEW + OVER:
    prof[c] = live[c]
prof = prof.reset_index()
prof.to_csv(f"{OUT}/merchant_profiles_v3.csv", index=False)

metrics = {
    "model": "Ridge(alpha=1.0) predicting acquirer spread (pp); rate = real blended Visa interchange + spread",
    "target": "negotiated_spread_pp (synthetic)", "train_rows": len(Xtr), "holdout_rows": len(Xte),
    "holdout_r2": round(r2, 3), "holdout_mae_pp": round(mae, 3), "spread_floor_pp": 0.40,
    "coefficients_per_std": {LABELS[f]: round(c, 4) for f, c in zip(FEATS, model.coef_)},
    "interchange_source": "Visa UAE Interchange Reimbursement Fees, effective 19 Dec 2024",
    "assumptions": ["all volume treated as Visa", "card_type to Visa product mapping",
                    "debit cap applied to daily average ticket"],
    "note": "Interchange is real; spread, scheme fees, acquirer margin and the cohort are synthetic. "
            "Accuracy is by construction."}
with open(f"{OUT}/rate_model_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

print(json.dumps({k: metrics[k] for k in ["holdout_r2", "holdout_mae_pp"]}))
print(live.rate_change_direction.value_counts().to_string())
