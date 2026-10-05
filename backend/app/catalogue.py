"""Product catalogue: the *facts* about what the bank sells (names, published caps and minimums).

Single source of truth for two things:
  1. the "Allowed products" table rendered into the consolidated knowledge page the LLM reads, and
  2. the factual validation of whatever the LLM proposes (name must exist, amount must respect published limits).
It contains NO eligibility or pitching policy - deciding who gets what is the LLM's job.
Sources: structured_data/business_banking_packages_and_charges.md and
         structured_data/enbd_business_loans_public_reference.md (both from emiratesnbd.com).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    name: str
    kind: str                 # lending | cross_sell | not_pitchable
    min_aed: float | None = None
    max_aed: float | None = None
    sized: bool = False       # True: the amount may be set, and must not exceed the client's supplied sizing limit
    tenure: str = ""
    note: str = ""


PRODUCTS: list[Product] = [
    # ── lending the RM can pitch ─────────────────────────────────────────────
    Product("Working capital facility", "lending", min_aed=250_000, sized=True,
            note="From AED 250,000 (published minimum); no published maximum. The client's supplied working-capital limit is the sizing basis."),
    Product("Small Business Loan", "lending", min_aed=50_000, max_aed=300_000, sized=True, tenure="up to 36 months",
            note="SME loan, AED 50,000 to 300,000."),
    Product("Merchant Loan (POS)", "lending", max_aed=5_000_000, sized=True, tenure="up to 48 months",
            note="For POS merchants; up to AED 5 million; complimentary life insurance. How it is serviced is not published."),
    Product("Commercial Vehicle Loan", "lending", max_aed=7_000_000, tenure="not stated",
            note="Finances 90% of cost, new and used (trucks, buses, pick-ups, vans, trailers). No supplied amount: do not state one."),
    Product("Construction Equipment Loan", "lending", max_aed=5_000_000, tenure="max 36 months",
            note="Finances 85% of equipment cost. No supplied amount: do not state one."),
    Product("Fleet Financing", "lending", tenure="up to 60 months",
            note="Up to 80% of fleet value, new and used vehicles. No supplied amount: do not state one."),
    Product("Term Loan", "lending", max_aed=20_000_000,
            note="Term loans up to AED 20 million. No supplied amount: do not state one."),
    # ── cross-sell (new-to-bank for the client if not already held) ───────────
    Product("Payroll / WPS Services", "cross_sell", note="Payroll / Wages Protection System services."),
    Product("Trade Finance (smartTRADE)", "cross_sell",
            note="Online trade-finance portal for Letters of Credit, Letters of Guarantee and trade loans; about 50% saving on trade finance fees vs over-the-counter."),
    Product("businessONLINE", "cross_sell", note="Digital cash-management platform for accounts, payments and liquidity."),
    # ── listed by the bank but NOT pitchable from the data we hold ───────────
    Product("Semi Secured Business Loan", "not_pitchable", max_aed=5_000_000, tenure="up to 60 months",
            note="Needs residential/commercial property as security. We hold no property data."),
    Product("Business Loan Against FD", "not_pitchable",
            note="Needs the client's Fixed Deposit (up to 90% of it). No client holds an FD in our data."),
    Product("Loans Against Property", "not_pitchable", max_aed=20_000_000,
            note="Needs property. We hold no property data."),
    Product("Commercial property loan", "not_pitchable", max_aed=20_000_000,
            note="For buying ready-built commercial property. No signal in our data."),
]

BY_NAME = {p.name: p for p in PRODUCTS}
PITCHABLE = {p.name for p in PRODUCTS if p.kind in ("lending", "cross_sell")}


def aed(n: float | None) -> str:
    return "—" if n is None else f"AED {n:,.0f}"


def render_allowed_table() -> str:
    rows = ["| Product (exact name) | Type | Min | Max | Tenure | Notes |", "|---|---|---|---|---|---|"]
    for p in PRODUCTS:
        typ = {"lending": "Lending", "cross_sell": "Cross-sell", "not_pitchable": "NOT PITCHABLE"}[p.kind]
        rows.append(f"| {p.name} | {typ} | {aed(p.min_aed)} | {aed(p.max_aed)} | {p.tenure or '—'} | {p.note} |")
    return "\n".join(rows)


def holds(held, product: str) -> bool:
    """True if a client's held-product list already contains `product`.

    The held-products data uses shorter names than the catalogue in places ('smartTRADE' vs 'Trade Finance (smartTRADE)'), so an
    exact comparison misses real overlaps. Used by the suggestion validation, the rule fallback and the ingest check.
    """
    p = product.lower()
    return any(h.lower() == p or h.lower() in p for h in held)


def validate_amount(product: str, amount: float | None, supplied_limit: float) -> tuple[bool, float | None, str]:
    """Factual check of an LLM-proposed amount. Returns (ok, amount_to_store, note)."""
    p = BY_NAME[product]
    if not p.sized:
        return True, None, "unsized product: amount dropped" if amount else ""
    if amount is None:
        return False, None, "sized product needs an amount"
    amount = float(amount)
    cap = min(x for x in (p.max_aed, supplied_limit) if x is not None)
    if p.min_aed is not None and cap < p.min_aed:
        return False, None, f"supplied limit {supplied_limit:,.0f} is below {p.name} minimum {p.min_aed:,.0f}"
    if amount > cap:
        return True, cap, f"amount clamped from {amount:,.0f} to {cap:,.0f}"
    if p.min_aed is not None and amount < p.min_aed:
        return True, min(cap, p.min_aed), f"amount raised to the {p.name} minimum"
    return True, round(amount), ""
