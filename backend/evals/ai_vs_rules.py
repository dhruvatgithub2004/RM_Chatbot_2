"""How do the AI's stored decisions compare with what the plain rules would decide, and do they obey the engine's own rules?

Reads the loaded database only (no model calls). Re-run after every `python -m app.suggest_llm` or ingest:

    cd backend
    python -m evals.ai_vs_rules

Sections: coverage; decision mix; rule checks (retention needs a behavioural signal, no held product pitched); priority spread;
AI versus rule-based pitches; top-10 differentiation. 'Different from the rules' is not 'better than the rules': there is no
ground truth here. These numbers show the engine is varied, calibrated and rule-abiding; they do not prove it is right.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import catalogue, config  # noqa: E402
from app.suggest_llm import RETENTION_CODES  # noqa: E402

db = sqlite3.connect(config.DATABASE_URL.replace("sqlite:///", ""))
d = pd.read_sql("""select s.merchant_id, s.source, s.kind, s.product, s.amount_aed, s.priority, s.note,
                          p.score, p.flagged, p.signals, p.pitch_kind, p.pitch_title, p.pitch_amount_aed,
                          c.opportunity_tier tier, c.suggested_working_capital_limit_aed lim
                   from client_suggestion s join client_priority p using(merchant_id) join client c using(merchant_id)""", db)
held = pd.read_sql("select merchant_id, product from client_product", db).groupby("merchant_id").product.apply(list).to_dict()
d["flagged"] = d.flagged.astype(bool)
d["codes"] = d.signals.apply(lambda x: {y["code"] for y in json.loads(x or "[]")})
d["ai_pitch"] = d.kind.isin(["lending", "cross_sell"])
d["rule_pitch"] = d.pitch_kind.notna()
ai = d[d.source == "llm"]


def section(t):
    print(f"\n== {t}")


section("Coverage")
print(f"clients {len(d)} | decided by the model {len(ai)} | rule fallback {int((d.source == 'rules').sum())}")
for reason, n in d[d.source == "rules"].note.str.replace(r"rule-based fallback \(|\)$", "", regex=True).str[:80].value_counts().items():
    print(f"  fallback reason x{n}: {reason}")

section("Decision mix")
print("all   :", d.kind.value_counts().to_dict())
print("flagged clients   ->", d[d.flagged].kind.value_counts().to_dict())
print("unflagged clients ->", d[~d.flagged].kind.value_counts().to_dict())

section("Rule checks (should both be 0)")
ret = ai[ai.kind == "retention"]
print("retention decisions:", len(ret), "| without dormant / falling-volume signal:", int((~ret.codes.apply(lambda s: bool(RETENTION_CODES & s))).sum()))
pit = d[d.ai_pitch & d["product"].notna()]
clash = [(r.merchant_id, r["product"]) for _, r in pit.iterrows() if catalogue.holds(held.get(r.merchant_id, []), r["product"])]
print("pitched a product the client already holds:", len(clash), clash[:3])

section("Priority spread (model decisions)")
p = ai.priority
print(f"min {p.min():.0f} | p25 {p.quantile(.25):.0f} | median {p.median():.0f} | p75 {p.quantile(.75):.0f} | max {p.max():.0f} | distinct values {p.nunique()}"
      f" | exactly 55 or 65: {100 * p.isin([55, 65]).mean():.0f}%")
print(f"correlation with rule attention score {ai.priority.corr(ai.score):.2f} | with opportunity tier {ai.priority.corr(-ai.tier):.2f}"
      f" | with supplied limit {ai.priority.corr(ai.lim):.2f}")

section("AI versus the rule-based pitch")
print(f"rules would pitch {int(d.rule_pitch.sum())} clients | the AI pitches {int(d.ai_pitch.sum())}")
print(pd.crosstab(d.rule_pitch.rename("rules pitch"), d.ai_pitch.rename("AI pitches")).to_string())
both = d[d.rule_pitch & d.ai_pitch]
same = (both.pitch_title.fillna("").str.lower() == both["product"].fillna("").str.lower()).mean() if len(both) else 0
print(f"where both pitch (n={len(both)}): same product {100 * same:.0f}%")
print("rule pitch kinds:", d.pitch_kind.value_counts(dropna=False).to_dict())

section("Top 10 pitches")
ai_top = pit[pit.source == "llm"].sort_values("priority", ascending=False).head(10)
rule_top = d[d.rule_pitch].sort_values(["tier", "lim"], ascending=[True, False]).head(10)
print(f"AI top 10 : {ai_top['product'].nunique()} distinct products, {ai_top.amount_aed.nunique()} distinct amounts")
print(f"rule top 10: {rule_top.pitch_title.nunique()} distinct products, {rule_top.pitch_amount_aed.nunique()} distinct amounts")
print("overlap between the two top 10 lists:", len(set(ai_top.merchant_id) & set(rule_top.merchant_id)), "of 10")
print(f"distinct products across all pitches: AI {pit['product'].nunique()} | rules {d.pitch_title.nunique()}")
print(f"share of clients given a pitch: AI {100 * d.ai_pitch.mean():.0f}% | rules {100 * d.rule_pitch.mean():.0f}%")
