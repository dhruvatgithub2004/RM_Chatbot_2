"""Builds the ONE consolidated knowledge page the LLM reads (both for suggestions and for the co-pilots).

structured_data/rm_product_knowledge.md =
    how-to-read header + data dictionary + allowed-products table (from catalogue.py)
    + the bank's packages & charges document + the public business-loans reference.
Run `python -m app.knowledge` to rebuild; it is also rebuilt automatically when missing.
"""
from __future__ import annotations

import re

from . import config
from .catalogue import render_allowed_table

KNOWLEDGE_PATH = config.ROOT_DIR / "structured_data" / "rm_product_knowledge.md"
PACKAGES_DOC = config.ROOT_DIR / "structured_data" / "business_banking_packages_and_charges.md"
LOANS_DOC = config.ROOT_DIR / "structured_data" / "enbd_business_loans_public_reference.md"

HEADER = """# RM Co-pilot — Product & Policy Knowledge Page

This single page is everything the assistant knows about the bank's products, charges and the meaning of the client data.
It is public product information (emiratesnbd.com) plus a data dictionary. It contains NO client data and NO pitching policy:
deciding what to suggest to each client is the assistant's job, using the client's data and this page.

## 1. Data dictionary (what each client field means)
- `package`: the client's Business Banking package (Connect, Proprietor, Prime, Preferred, Prestige, Platinum, Emirati Business). Minimum balances and fall-below fees are in section 3.
- `account_balance_aed`: current account balance. `avg_monthly_turnover_aed`: average monthly turnover.
- `synthetic_credit_score`: a SYNTHETIC score (300-900), not a bureau score. `risk_segment`: Low / Medium / High, as supplied; it does not track the synthetic score.
- `monthly_pos_limit_aed` / `daily_pos_limit_aed`: independent POS acquiring limits.
- Volume figures: "last 30 days" is relative to the data's as-of date, not today's date. `volume_change_vs_prior_30d_pct` compares it with the 30 days before. `volume_change_6m_pct` compares the latest complete month with the first of the last six complete months.
- `dormant_streak_days`: consecutive trailing days with POS terminals dormant (zero volume).
- `card_mix_30d`: share of last-30-day volume on days labelled Mass / Premium / Super Premium / Debit / Business. It is a per-day label, not a split by transaction.
- Rates: `current_rate_pct` is the client's current merchant rate; `rate_change_recommended` says whether the pricing model recommends a change. When it is true, the suggested rate is only ever given as a range, `suggested_rate_range_pct` (the model's estimate plus or minus 0.10 points, rounded to 0.05, illustrative): quote the range, never a single figure. When it is false, no change is recommended and no suggested rate or range may be quoted. `rate_rationale` is the supplied explanation.
- `suggested_working_capital_limit_aed`: the bank's supplied sizing for this client. It is the ONLY supplied amount; it is the upper bound for any sized lending amount.
- `opportunity_tier` / `opportunity_label`: supplied opportunity ranking (1 Prime, 2 Strong, 3 Moderate, 4 Low priority).
- `products_held`: products the client already has. `ntb_candidates`: new-to-bank cross-sell candidates supplied by the bank, with rationale.
- `attention_*`: a rule-based attention score and reason computed from the client's POS data (dormancy, volume decline, limit pressure, idle balance, rate review, risk).

## 2. Allowed products (the ONLY product names that may be suggested; exact spelling)
"""


def _sections() -> dict[str, str]:
    """The page in three parts: `core` (data dictionary and allowed products), `packages` (section 3) and `loans` (section 4)."""
    packages = PACKAGES_DOC.read_text(encoding="utf-8") if PACKAGES_DOC.exists() else ""
    loans = LOANS_DOC.read_text(encoding="utf-8") if LOANS_DOC.exists() else ""
    return dict(
        core=(HEADER + render_allowed_table()
              + "\n\nRows marked NOT PITCHABLE are real bank products that cannot be offered because they need data we do not hold.\n"),
        packages="\n\n## 3. Packages, charges and cards (Emirates NBD public documents)\n" + _demote(packages),
        loans="\n\n## 4. Business loans (Emirates NBD public page)\n" + _demote(loans) + "\n")


def build() -> str:
    s = _sections()
    return s["core"] + s["packages"] + s["loans"]


# Which questions need which part. The whole page is about 3,400 tokens, a large share of an 8K window, so a question gets only the
# parts it needs. A question that needs none gets nothing, and the model is told to say "not available" for what is not given.
_PRODUCTS = re.compile(r"\b(products?|smarttrade|businessonline|payroll|wps|trade finance|catalogue|catalog)\b", re.I)
_PACKAGES = re.compile(r"\b(packages?|fees?|charges?|tariffs?|minimum balance|fall[- ]below|debit cards?|credit cards?|card fees?)\b", re.I)
_LOANS = re.compile(r"\b(loans?|financing|finance|tenure|repay\w*|term loan|fleet|vehicle|equipment|interest)\b", re.I)


def for_question(question: str, *, always_core: bool = False) -> str:
    """The parts of the knowledge page a question needs. `always_core` keeps the data dictionary and allowed products (merchant chat)."""
    parts = _sections()
    wants_packages, wants_loans = bool(_PACKAGES.search(question)), bool(_LOANS.search(question))
    out = []
    if always_core or wants_packages or wants_loans or _PRODUCTS.search(question):
        out.append(parts["core"])
    if wants_packages:
        out.append(parts["packages"])
    if wants_loans:
        out.append(parts["loans"])
    return "".join(out)


def _demote(md: str) -> str:
    """Push the source documents' headings down two levels so the page keeps one outline."""
    return "\n".join(("##" + line) if line.startswith("#") else line for line in md.splitlines())


def write() -> str:
    text = build()
    KNOWLEDGE_PATH.write_text(text, encoding="utf-8")
    return text


def text() -> str:
    if not KNOWLEDGE_PATH.exists():
        return write()
    return KNOWLEDGE_PATH.read_text(encoding="utf-8")


if __name__ == "__main__":
    t = write()
    print(f"Wrote {KNOWLEDGE_PATH} ({len(t):,} chars, ~{len(t) // 4:,} tokens)")
