"""Idempotent ingest: CSV -> validate -> load -> base facts -> priority -> data-quality report.

Run:  python -m app.ingest      (from backend/)
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import config, scoring
from .db import SessionLocal, engine, Base
from . import models as m

MERCHANT_COLS = [
    "merchant_id", "business_name", "industry", "mcc_code", "business_type", "license_authority",
    "vat_registered", "package", "relationship_start_date", "rm_id", "branch_id", "account_balance_aed",
    "avg_monthly_turnover_aed", "synthetic_credit_score", "num_pos_terminals", "risk_segment", "city",
    "monthly_pos_limit_aed", "daily_pos_limit_aed", "card_product", "card_number_masked", "rate_tier", "current_rate_pct",
    "suggested_rate_pct", "rate_change_recommended", "rate_rationale", "suggested_working_capital_limit_aed",
    "opportunity_tier", "opportunity_label",
]
POS_COLS = ["merchant_id", "date", "daily_acquiring_volume_aed", "transaction_count", "chargeback_count", "chargeback_ratio_pct",
            "avg_ticket_size_aed", "terminal_status", "card_type"]
PRODUCT_COLS = ["merchant_id", "product"]
NTB_COLS = ["merchant_id", "candidate_product", "rationale"]
WC_MIN_FACILITY_AED = 250_000  # smallest working-capital facility per the bank's published page (business_banking_packages_and_charges.md)
CARD_TYPES = ["Mass", "Premium", "Super Premium", "Debit", "Business"]


class IngestError(Exception):
    pass


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path, cols, label):
    if not path.exists():
        raise IngestError(f"{label} file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise IngestError(f"{label} file is missing required columns: {missing}")
    return df


class Issues:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, severity, source, code, detail, row_ref=None):
        self.rows.append(dict(severity=severity, source=source, code=code, detail=detail, row_ref=row_ref))

    @property
    def quarantined(self):
        return sum(1 for r in self.rows if r["severity"] == "quarantine")

    @property
    def warning_codes(self):
        return sorted({r["code"] for r in self.rows if r["severity"] == "warning"})


def validate_merchants(df: pd.DataFrame, issues: Issues) -> pd.DataFrame:
    bad = pd.Series(False, index=df.index)

    def flag(mask, code, detail):
        nonlocal bad
        for i in df.index[mask & ~bad]:
            issues.add("quarantine", "merchant", code, detail, f"row {i + 2} {df.at[i, 'merchant_id']}")
        bad |= mask

    flag(~df.merchant_id.str.match(r"^MER\d{4}$"), "bad_merchant_id", "merchant_id must match MER####")
    flag(df.merchant_id.duplicated(keep="first"), "duplicate_merchant_id", "duplicate merchant_id")
    flag(~df.rm_id.str.match(r"^RM\d{3}$"), "bad_rm_id", "rm_id must match RM###")
    flag(~df.branch_id.str.match(r"^BR\d{3}$"), "bad_branch_id", "branch_id must match BR###")
    flag(~df.risk_segment.isin(["Low", "Medium", "High"]), "bad_risk_segment", "risk_segment must be Low|Medium|High")
    flag(~df.vat_registered.isin(["True", "False"]), "bad_vat", "vat_registered must be True|False")
    flag(pd.to_datetime(df.relationship_start_date, errors="coerce", format="%Y-%m-%d").isna(), "bad_date", "relationship_start_date invalid")
    for c in ["account_balance_aed", "avg_monthly_turnover_aed", "monthly_pos_limit_aed", "daily_pos_limit_aed"]:
        v = pd.to_numeric(df[c], errors="coerce")
        flag(v.isna() | (v < 0), f"bad_{c}", f"{c} must be a number >= 0")
    t = pd.to_numeric(df.num_pos_terminals, errors="coerce")
    flag(t.isna() | (t < 1) | (t % 1 != 0), "bad_num_pos_terminals", "num_pos_terminals must be an integer >= 1")
    s = pd.to_numeric(df.synthetic_credit_score, errors="coerce")
    flag(s.isna() | (s < 300) | (s > 900), "bad_score", "synthetic_credit_score must be 300-900")
    for c in ["card_product", "card_number_masked", "rate_rationale", "opportunity_label"]:
        flag(df[c].str.strip() == "", f"missing_{c}", f"{c} is required")
    for c in ["current_rate_pct", "suggested_rate_pct"]:
        v = pd.to_numeric(df[c], errors="coerce")
        flag(v.isna() | (v <= 0) | (v > 10), f"bad_{c}", f"{c} must be a percentage in (0, 10]")
    flag(~df.rate_change_recommended.isin(["True", "False"]), "bad_rate_change_flag", "rate_change_recommended must be True|False")
    for c in ["rate_tier", "opportunity_tier"]:
        v = pd.to_numeric(df[c], errors="coerce")
        flag(v.isna() | ~v.isin([1, 2, 3, 4]), f"bad_{c}", f"{c} must be 1-4")
    w = pd.to_numeric(df.suggested_working_capital_limit_aed, errors="coerce")
    flag(w.isna() | (w < 0), "bad_working_capital_limit", "suggested_working_capital_limit_aed must be >= 0")
    return df[~bad].copy()


def validate_pos(df: pd.DataFrame, merchant_ids: set[str], issues: Issues) -> pd.DataFrame:
    bad = pd.Series(False, index=df.index)

    def flag(mask, code, detail):
        nonlocal bad
        for i in df.index[mask & ~bad][:50]:  # cap detail rows per rule; count stays exact below
            issues.add("quarantine", "pos", code, detail, f"row {i + 2} {df.at[i, 'merchant_id']} {df.at[i, 'date']}")
        extra = int((mask & ~bad).sum()) - min(50, int((mask & ~bad).sum()))
        if extra > 0:
            issues.add("quarantine", "pos", code, f"... and {extra} more rows for rule '{detail}'")
        bad |= mask

    flag(~df.merchant_id.isin(merchant_ids), "orphan_pos_row", "merchant_id not in merchant profiles")
    flag(pd.to_datetime(df.date, errors="coerce", format="%Y-%m-%d").isna(), "bad_date", "date invalid")
    flag(df.duplicated(["merchant_id", "date"], keep="first"), "duplicate_pos_key", "duplicate (merchant_id, date)")
    flag(~df.terminal_status.isin(["Active", "Dormant"]), "bad_terminal_status", "terminal_status must be Active|Dormant")
    flag(~df.card_type.isin(CARD_TYPES), "bad_card_type", "card_type must be Mass|Premium|Super Premium|Debit|Business")
    vol = pd.to_numeric(df.daily_acquiring_volume_aed, errors="coerce")
    cnt = pd.to_numeric(df.transaction_count, errors="coerce")
    for c in ["chargeback_count", "chargeback_ratio_pct", "avg_ticket_size_aed"]:
        v = pd.to_numeric(df[c], errors="coerce")
        flag(v.isna() | (v < 0), f"bad_{c}", f"{c} must be a number >= 0")
    flag(vol.isna() | (vol < 0), "bad_volume", "daily_acquiring_volume_aed must be >= 0")
    flag(cnt.isna() | (cnt < 0) | (cnt % 1 != 0), "bad_txn_count", "transaction_count must be an integer >= 0")
    flag((df.terminal_status == "Dormant") & ((vol != 0) | (cnt != 0)), "dormant_with_activity", "Dormant rows must have zero volume and count")
    return df[~bad].copy()


def soft_checks(merchants: pd.DataFrame, pos: pd.DataFrame, issues: Issues, held: pd.DataFrame, ntb: pd.DataFrame):
    first = pos.groupby("merchant_id").date.min().rename("first_pos")
    j = merchants.merge(first, on="merchant_id", how="left")
    pre = j[(j.first_pos.notna()) & (j.relationship_start_date > j.first_pos)]
    if len(pre):
        issues.add("warning", "merchant+pos", "pos_before_relationship_start",
                   f"{len(pre)} clients have POS data dated before relationship_start_date: {', '.join(pre.merchant_id)}")
    dup = merchants[merchants.business_name.duplicated(keep=False)].sort_values("business_name")
    if len(dup):
        names = {n: ", ".join(g.merchant_id) for n, g in dup.groupby("business_name")}
        issues.add("warning", "merchant", "duplicate_business_name", "; ".join(f"{n}: {ids}" for n, ids in names.items()))
    ratio = merchants.daily_pos_limit_aed * 30 / merchants.monthly_pos_limit_aed
    if len(ratio) and (ratio.min() < 0.99 or ratio.max() > 1.01):
        issues.add("warning", "merchant", "limits_not_consistent",
                   f"daily_pos_limit x 30 / monthly_pos_limit ranges {ratio.min():.2f}-{ratio.max():.2f}; limits are independent")
    grp = merchants.groupby("risk_segment").synthetic_credit_score.agg(["min", "max"])
    if len(grp) == 3 and grp.loc["High", "min"] < grp.loc["Low", "max"]:
        issues.add("warning", "merchant", "risk_segment_not_monotonic_with_score",
                   "risk_segment overlaps in synthetic_credit_score range: " + "; ".join(f"{k} {int(r['min'])}-{int(r['max'])}" for k, r in grp.iterrows()))
    nochg = merchants[(~merchants.rate_change_recommended) & (merchants.current_rate_pct != merchants.suggested_rate_pct)]
    if len(nochg):
        issues.add("warning", "merchant", "suggested_rate_set_when_no_change",
                   f"{len(nochg)} clients have rate_change_recommended=False but suggested_rate_pct differs from current_rate_pct; "
                   "the UI shows 'No change recommended' for these and does not display the suggested value")
    small = merchants[merchants.suggested_working_capital_limit_aed < WC_MIN_FACILITY_AED]
    if len(small):
        issues.add("warning", "merchant", "working_capital_below_minimum_facility",
                   f"{len(small)} clients have a suggested working-capital limit below AED {WC_MIN_FACILITY_AED:,} (smallest published facility size); "
                   "no lending suggestion is made for them")
    from .catalogue import holds  # name-tolerant: 'smartTRADE' (held) vs 'Trade Finance (smartTRADE)' (candidate)
    held_by = held.groupby("merchant_id")["product"].apply(list).to_dict()
    dup_ntb = [r.merchant_id for r in ntb.itertuples() if holds(held_by.get(r.merchant_id, []), r.candidate_product)]
    if dup_ntb:
        issues.add("warning", "ntb", "ntb_candidate_already_held", f"NTB candidate already held for: {', '.join(sorted(set(dup_ntb)))}")
    over = pos.merge(merchants[["merchant_id", "daily_pos_limit_aed"]], on="merchant_id")
    n_over = int((over.daily_acquiring_volume_aed > over.daily_pos_limit_aed).sum())
    if n_over:
        issues.add("warning", "pos", "volume_over_daily_limit", f"{n_over} POS rows exceed daily_pos_limit_aed")


def complete_months(pos: pd.DataFrame) -> list[str]:
    lo, hi = pos.date.min(), pos.date.max()
    out = []
    for ym in sorted(pos.date.dt.strftime("%Y-%m").unique()):
        y, mo = int(ym[:4]), int(ym[5:])
        first, last = date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])
        if first >= lo.date() and last <= hi.date():
            out.append(ym)
    return out


def _ratio(num, den):
    return None if den in (None, 0) or pd.isna(den) or pd.isna(num) else float(num) / float(den)


def compute_facts(merchants: pd.DataFrame, pos: pd.DataFrame, as_of: date):
    ts = pd.Timestamp(as_of)
    t30 = pos[(pos.date > ts - pd.Timedelta(days=30)) & (pos.date <= ts)]
    p30 = pos[(pos.date > ts - pd.Timedelta(days=60)) & (pos.date <= ts - pd.Timedelta(days=30))]
    months6 = complete_months(pos)[-6:]

    # monthly series (all calendar months in the data)
    pos = pos.assign(ym=pos.date.dt.strftime("%Y-%m"))
    comp = set(complete_months(pos))
    monthly = []
    for (mid, ym), g in pos.groupby(["merchant_id", "ym"]):
        monthly.append(dict(merchant_id=mid, month=ym, volume_aed=round(float(g.daily_acquiring_volume_aed.sum()), 2),
                            txn_count=int(g.transaction_count.sum()), active_days=int((g.terminal_status == "Active").sum()),
                            dormant_days=int((g.terminal_status == "Dormant").sum()), is_complete=ym in comp))
    monthly_df = pd.DataFrame(monthly)

    # card mix windows
    def mix(window_df, window):
        rows = []
        for mid, g in window_df.groupby("merchant_id"):
            tot_vol = g.daily_acquiring_volume_aed.sum()
            act = g[g.terminal_status == "Active"]
            tot_days = len(act)
            for ct in CARD_TYPES:
                gc = g[g.card_type == ct]
                v = float(gc.daily_acquiring_volume_aed.sum())
                d = int((gc.terminal_status == "Active").sum())
                rows.append(dict(merchant_id=mid, window=window, card_type=ct, volume_aed=round(v, 2),
                                 volume_share=_ratio(v, tot_vol), txn_count=int(gc.transaction_count.sum()),
                                 active_days=d, day_share=_ratio(d, tot_days)))
        return rows

    m6_df = pos[pos.ym.isin(months6)]
    mix_rows = mix(t30, "t30") + mix(m6_df, "m6")
    mix_df = pd.DataFrame(mix_rows)

    by_t30 = {k: g for k, g in t30.groupby("merchant_id")}
    by_p30 = {k: g for k, g in p30.groupby("merchant_id")}
    by_all = {k: g.sort_values("date") for k, g in pos.groupby("merchant_id")}
    mv = monthly_df.set_index(["merchant_id", "month"]).volume_aed.to_dict() if len(monthly_df) else {}

    facts = []
    for r in merchants.itertuples():
        mid = r.merchant_id
        g30, gp, ga = by_t30.get(mid), by_p30.get(mid), by_all.get(mid)
        f = dict(merchant_id=mid, as_of_date=as_of)
        months_tenure = (as_of.year - r.relationship_start_date.year) * 12 + (as_of.month - r.relationship_start_date.month)
        if as_of.day < r.relationship_start_date.day:
            months_tenure -= 1
        f["tenure_months"] = max(0, months_tenure)
        f["balance_to_turnover"] = _ratio(r.account_balance_aed, r.avg_monthly_turnover_aed)
        if ga is None:
            f.update(is_dormant_now=False, dormant_streak_days=0)
            facts.append(f)
            continue
        v30 = float(g30.daily_acquiring_volume_aed.sum()) if g30 is not None else 0.0
        vp = float(gp.daily_acquiring_volume_aed.sum()) if gp is not None else 0.0
        tx30 = int(g30.transaction_count.sum()) if g30 is not None else 0
        peak = float(g30.daily_acquiring_volume_aed.max()) if g30 is not None and len(g30) else 0.0
        status = ga.terminal_status.tolist()
        streak = 0
        for s in reversed(status):
            if s == "Dormant":
                streak += 1
            else:
                break
        c30 = mix_df[(mix_df.merchant_id == mid) & (mix_df.window == "t30")] if len(mix_df) else mix_df
        dom = None
        prem = None
        if len(c30) and v30 > 0:
            dom = c30.sort_values("volume_aed", ascending=False).iloc[0].card_type
            prem = float(c30[c30.card_type.isin(["Premium", "Super Premium"])].volume_aed.sum()) / v30
        m6v = [mv.get((mid, ym)) for ym in months6]
        cb30 = int(g30.chargeback_count.sum()) if g30 is not None else 0
        f.update(
            chargeback_count_t30=cb30, chargeback_ratio_t30=_ratio(cb30 * 100, tx30),
            volume_t30=round(v30, 2), volume_p30=round(vp, 2),
            volume_change_t30_vs_p30=_ratio(v30 - vp, vp), txn_t30=tx30,
            txn_p30=int(gp.transaction_count.sum()) if gp is not None else 0,
            avg_ticket_t30=_ratio(v30, tx30),
            active_days_t30=int((g30.terminal_status == "Active").sum()) if g30 is not None else 0,
            dormant_days_t30=int((g30.terminal_status == "Dormant").sum()) if g30 is not None else 0,
            is_dormant_now=status[-1] == "Dormant", dormant_streak_days=streak,
            peak_daily_volume_t30=round(peak, 2),
            daily_limit_utilisation_t30=_ratio(peak, r.daily_pos_limit_aed),
            monthly_limit_utilisation_t30=_ratio(v30, r.monthly_pos_limit_aed),
            volume_to_turnover_t30=_ratio(v30, r.avg_monthly_turnover_aed),
            dominant_card_type_t30=dom, premium_share_t30=prem,
            volume_change_m6=_ratio(m6v[-1] - m6v[0], m6v[0]) if len(m6v) == 6 and m6v[0] else None,
        )
        facts.append(f)
    return facts, monthly_df, mix_df


def _products_long(path, issues) -> pd.DataFrame:
    """Products held as (merchant_id, product) rows. Accepts the long layout, or the wide 0/1 layout (one column per product)."""
    if not path.exists():
        raise IngestError(f"products_held file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "merchant_id" not in df.columns:
        raise IngestError("products_held file is missing required columns: ['merchant_id']")
    if "product" in df.columns:
        return df[PRODUCT_COLS]
    long = df.melt(id_vars="merchant_id", var_name="product", value_name="held")
    long["held"] = long["held"].str.strip()
    for i in long.index[~long.held.isin(["0", "1"])]:
        issues.add("quarantine", "products_held", "bad_row", "held flag must be 0 or 1", f"{long.at[i, 'merchant_id']} / {long.at[i, 'product']}")
    return long[long.held == "1"][PRODUCT_COLS].reset_index(drop=True)


def _load_side_table(path, cols, label, merchant_ids, issues, key, df=None):
    """Validate a merchant-keyed side file: known merchant, non-blank values, unique key."""
    df = (_read(path, cols, label) if df is None else df)[cols].copy()
    for c in cols:
        df[c] = df[c].str.strip()
    bad = ~df.merchant_id.isin(merchant_ids) | (df[cols[1]] == "") | df.duplicated(key, keep="first")
    for i in df.index[bad]:
        issues.add("quarantine", label, "bad_row", "unknown merchant_id, blank value or duplicate", f"row {i + 2} {df.at[i, 'merchant_id']}")
    return df[~bad].copy()


def run(verbose: bool = True) -> dict:
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    mp, pp = config.MERCHANT_CSV_PATH, config.POS_CSV_PATH
    hp, np_ = config.PRODUCTS_CSV_PATH, config.NTB_CSV_PATH
    merchants_raw = _read(mp, MERCHANT_COLS, "merchant")
    pos_raw = _read(pp, POS_COLS, "pos")
    issues = Issues()

    merchants = validate_merchants(merchants_raw[MERCHANT_COLS], issues)
    for c in ["account_balance_aed", "avg_monthly_turnover_aed", "monthly_pos_limit_aed", "daily_pos_limit_aed",
              "suggested_working_capital_limit_aed"]:
        merchants[c] = pd.to_numeric(merchants[c]).round(2)
    for c in ["current_rate_pct", "suggested_rate_pct"]:
        merchants[c] = pd.to_numeric(merchants[c]).round(2)
    for c in ["synthetic_credit_score", "num_pos_terminals", "rate_tier", "opportunity_tier"]:
        merchants[c] = pd.to_numeric(merchants[c]).astype(int)
    merchants["vat_registered"] = merchants.vat_registered == "True"
    merchants["rate_change_recommended"] = merchants.rate_change_recommended == "True"
    merchants["relationship_start_date"] = pd.to_datetime(merchants.relationship_start_date).dt.date

    pos = validate_pos(pos_raw[POS_COLS], set(merchants.merchant_id), issues)
    pos["date"] = pd.to_datetime(pos.date)
    pos["daily_acquiring_volume_aed"] = pd.to_numeric(pos.daily_acquiring_volume_aed).round(2)
    pos["transaction_count"] = pd.to_numeric(pos.transaction_count).astype(int)
    pos["chargeback_count"] = pd.to_numeric(pos.chargeback_count).astype(int)
    pos["chargeback_ratio_pct"] = pd.to_numeric(pos.chargeback_ratio_pct)
    pos["avg_ticket_size_aed"] = pd.to_numeric(pos.avg_ticket_size_aed)

    ids = set(merchants.merchant_id)
    held = _load_side_table(hp, PRODUCT_COLS, "products_held", ids, issues, ["merchant_id", "product"], df=_products_long(hp, issues))
    ntb = _load_side_table(np_, NTB_COLS, "ntb", ids, issues, ["merchant_id", "candidate_product"])

    if pos.empty:
        raise IngestError("no valid POS rows; refusing to load")
    soft_checks(merchants.assign(relationship_start_date=pd.to_datetime(merchants.relationship_start_date)), pos, issues, held, ntb)

    as_of = pos.date.max().date()
    merchants["has_pos_data"] = merchants.merchant_id.isin(set(pos.merchant_id))
    facts, monthly_df, mix_df = compute_facts(merchants, pos, as_of)
    priorities = scoring.score_all(merchants, facts, monthly_df, held, ntb)

    # Schema changes between data drops are expected, so rebuild tables (all contents are re-derived from the CSVs).
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s, s.begin():
        s.bulk_insert_mappings(m.Client, merchants.to_dict("records"))
        s.bulk_insert_mappings(m.PosDaily, pos.assign(date=pos.date.dt.date).to_dict("records"))
        s.bulk_insert_mappings(m.ClientProduct, held.to_dict("records"))
        s.bulk_insert_mappings(m.NtbCandidate, ntb.to_dict("records"))
        s.bulk_insert_mappings(m.ClientFact, [_clean(f) for f in facts])
        s.bulk_insert_mappings(m.ClientMonthlyVolume, monthly_df.to_dict("records"))
        s.bulk_insert_mappings(m.ClientCardMix, [_clean(r) for r in mix_df.to_dict("records")])
        s.bulk_insert_mappings(m.ClientPriority, priorities)
        s.bulk_insert_mappings(m.IngestIssue, issues.rows)
        s.add(m.IngestRun(
            started_at=started, as_of_date=as_of, merchant_file=mp.name, pos_file=pp.name,
            merchant_sha256=_sha256(mp), pos_sha256=_sha256(pp), clients_loaded=len(merchants),
            pos_rows_loaded=len(pos), quarantined=issues.quarantined, warnings=len(issues.warning_codes), status="ok"))

    report = dict(
        as_of_date=as_of.isoformat(), clients_loaded=len(merchants), pos_rows_loaded=len(pos),
        products_held_rows=len(held), ntb_candidate_rows=len(ntb),
        quarantined=issues.quarantined, warning_types=issues.warning_codes, issues=issues.rows,
        flagged_clients=sum(1 for p in priorities if p["flagged"]),
    )
    config.QUALITY_REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    # LLM-decided suggestions (needs a configured LLM; set SKIP_LLM_SUGGESTIONS=1 to skip, e.g. in tests)
    from . import knowledge, llm, suggest_llm
    knowledge.write()
    if llm.configured() and os.getenv("SKIP_LLM_SUGGESTIONS") != "1":
        report["suggestions"] = suggest_llm.generate_all(verbose=verbose)
    elif verbose:
        print("Suggestions: LLM not configured or skipped; Suggestions screen uses the rule-based fallback.")
    if verbose:
        print(f"Ingest OK  as_of={as_of}  clients={len(merchants)}  pos_rows={len(pos)}  products={len(held)}  ntb={len(ntb)}  "
              f"quarantined={issues.quarantined}  warnings={issues.warning_codes}  flagged={report['flagged_clients']}")
    return report


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and np.isnan(v):
            v = None
        elif isinstance(v, (np.floating,)):
            v = None if np.isnan(v) else float(v)
        elif isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.bool_,)):
            v = bool(v)
        out[k] = v
    return out


if __name__ == "__main__":
    try:
        run()
    except IngestError as e:
        print(f"INGEST ABORTED: {e}", file=sys.stderr)
        sys.exit(1)
