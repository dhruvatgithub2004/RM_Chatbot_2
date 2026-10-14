# RM Co-pilot — Product & Policy Knowledge Page

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
| Product (exact name) | Type | Min | Max | Tenure | Notes |
|---|---|---|---|---|---|
| Working capital facility | Lending | AED 250,000 | — | — | From AED 250,000 (published minimum); no published maximum. The client's supplied working-capital limit is the sizing basis. |
| Small Business Loan | Lending | AED 50,000 | AED 300,000 | up to 36 months | SME loan, AED 50,000 to 300,000. |
| Merchant Loan (POS) | Lending | — | AED 5,000,000 | up to 48 months | For POS merchants; up to AED 5 million; complimentary life insurance. How it is serviced is not published. |
| Commercial Vehicle Loan | Lending | — | AED 7,000,000 | not stated | Finances 90% of cost, new and used (trucks, buses, pick-ups, vans, trailers). No supplied amount: do not state one. |
| Construction Equipment Loan | Lending | — | AED 5,000,000 | max 36 months | Finances 85% of equipment cost. No supplied amount: do not state one. |
| Fleet Financing | Lending | — | — | up to 60 months | Up to 80% of fleet value, new and used vehicles. No supplied amount: do not state one. |
| Term Loan | Lending | — | AED 20,000,000 | — | Term loans up to AED 20 million. No supplied amount: do not state one. |
| Payroll / WPS Services | Cross-sell | — | — | — | Payroll / Wages Protection System services. |
| Trade Finance (smartTRADE) | Cross-sell | — | — | — | Online trade-finance portal for Letters of Credit, Letters of Guarantee and trade loans; about 50% saving on trade finance fees vs over-the-counter. |
| businessONLINE | Cross-sell | — | — | — | Digital cash-management platform for accounts, payments and liquidity. |
| Semi Secured Business Loan | NOT PITCHABLE | — | AED 5,000,000 | up to 60 months | Needs residential/commercial property as security. We hold no property data. |
| Business Loan Against FD | NOT PITCHABLE | — | — | — | Needs the client's Fixed Deposit (up to 90% of it). No client holds an FD in our data. |
| Loans Against Property | NOT PITCHABLE | — | AED 20,000,000 | — | Needs property. We hold no property data. |
| Commercial property loan | NOT PITCHABLE | — | AED 20,000,000 | — | For buying ready-built commercial property. No signal in our data. |

Rows marked NOT PITCHABLE are real bank products that cannot be offered because they need data we do not hold.


## 3. Packages, charges and cards (Emirates NBD public documents)
### Emirates NBD — Business Banking Packages & Schedule of Charges
Source: emiratesnbd.com/en/business-banking/business-packages; cdn Business Banking Schedule of Charges PDF (06/2025)
Emirates NBD Bank (P.J.S.C.), licensed by the Central Bank of the UAE.

#### Package Tiers (7 variants)
| Package | Min. Monthly Avg Relationship Balance | Fall-Below Fee | Monthly Account Service Fee |
|---|---|---|---|
| Connect (startups/Professional License, online-only) | Nil | Nil | Free (30 days), then AED 261.45/month |
| Proprietor | AED 50,000 | AED 262.50/month | Free |
| Prime | AED 50,000 | AED 157.50/month | AED 103.95/month |
| Preferred | AED 200,000 | AED 315/month | Free |
| Prestige | AED 500,000 | AED 787.50/month | Free |
| Platinum | AED 3,500,000 | AED 1,575/month | Free |
| Emirati Business | AED 25,000 | AED 157.50/month (first 6 months waived for new-to-bank) | Free |

Account opening fee: Free (all packages). Package upgrade/downgrade: Free.

#### Teller & Cash Handling (selected)
- Free teller transactions/month range from 1 (Connect) up to 60 (Platinum), thereafter AED 10.50–26.30/transaction depending on package.
- Bulk cash deposit/withdrawal: 0.05%–0.26% depending on package and amount tier (AED 0.5M–1M+ bands).
- Free CDM (cash deposit machine) transactions: 90/month (unlimited for Proprietor and Platinum).

#### Cheques
- First cheque book free (all packages); thereafter AED 26.30–52.50 (Prestige/Platinum/Emirati Business: unlimited free).
- Cheque returned charges: AED 105 (Proprietor) up to AED 367.50 (Connect); AED 315 for most mid/upper tiers.

#### Transfers
- Local TT via online banking: Free (all packages).
- Local TT via branch: AED 5.25 (Proprietor) to AED 52.50 (most other tiers); Free for Platinum.
- International TT via online: Free (Proprietor/Emirati Business) to AED 52.50 (Preferred/Prime).

#### Trade & FX
- Trade Tariff: Standard (Connect/Proprietor/Prime/Preferred) vs. Preferential (Prestige/Platinum/Emirati Business).
- Foreign currency cash deposit/withdrawal: 1.32% (Proprietor) down to 0.53% (Platinum/Emirati Business).
- Full trade finance fee schedule referenced separately at emiratesnbd.com (Trade Tariff document).

#### Account Closure & Compliance
- Account closure within 6 months: AED 105 (most tiers) up to AED 1,050 (Platinum).
- Trade License renewal grace period: 2 months, then AED 315–420/month penalty.
- Direct Debit (UAEDDS) Central Bank registration: AED 3,150 one-time (all packages).

#### Business Debit Cards (from emiratesnbd.com/en/cards/debit-cards/)
- **Visa Business Debit Card** — standard tier, no annual fee, no replacement fee; 1.84% foreign currency transaction fee.
- **Visa Signature Business Debit Card** — adds value-added offers (accounting, digital marketing, productivity tools) plus complimentary airport lounge access via the Visa Airport Companion app.
- **Visa Infinite Business Debit Card** — premium tier: global lounge access, valet parking, hotel perks, insurance, concierge services (part of ENBD's VIP Privilege Program, a MENA-first for a business debit card).
- **Emirati Visa Signature Business Debit Card** — premium tier for the Emirati Business package.

#### Digital Trade & Cash Management (from emiratesnbd.com/en/business-online, en/media-center)
- **smartTRADE** — online trade finance portal: submit and track Letters of Credit, Letters of Guarantee, and trade loans digitally; real-time status updates; customers save roughly 50% on trade finance fees versus over-the-counter requests when initiated through the portal.
- **businessONLINE** — digital cash management platform covering accounts, payments, and liquidity across the client's banking relationship.

#### Business Financing (from emiratesnbd.com/en/business-banking/working-capital)
- Working capital facilities from AED 250,000.
- Term loans up to AED 20 million.
- Overdrafts, trade finance lines, and equipment loans available.
- Non-funded lines: Letters of Credit and Letters of Guarantee for trade.
- Supply Chain Finance: accelerated invoice payment financing.
- Emirates NBD has an MoU with Emirates Development Bank (EDB) providing credit guarantee coverage up to 50% of facility amount for SME lending — max AED 5M (larger SMEs) / AED 500K (smaller customers).

## 4. Business loans (Emirates NBD public page)
### Emirates NBD — Business Loans (public reference)
Source: https://www.emiratesnbd.com/en/business-banking/long-term (Business Banking > Business Loans). Retrieved 2026-10-02 by rendering the public page.
Emirates NBD Bank (P.J.S.C.) is licensed by the Central Bank of the UAE. Figures below are quoted from the page; **no interest/profit rates or fees are published on this page.**

#### Business Loans for small and medium entities (SME)
| Product | Amount | Tenure | Other stated terms |
|---|---|---|---|
| Merchant Loan (POS) | Up to AED 5 million | Up to 48 months | Complimentary life insurance |
| Small Business Loan | Up to AED 300,000 (minimum AED 50,000) | Up to 36 months | "Attractive interest rates" (no figure) |
| Semi Secured Business Loan | Up to AED 5 million | Up to 60 months | Equity release against existing residential or commercial property |
| Business Loan Against FD | Up to 90% of the fixed deposit amount | Max 48 months | Secured on the client's Fixed Deposit |

#### Business Vehicle Loans
| Product | Amount | Tenure | Other stated terms |
|---|---|---|---|
| Commercial Vehicle Loans | Up to AED 7 million; finances 90% of cost, new and used, incl. insurance premiums | not stated | Trucks, heavy buses, multi-utility vehicles, pick-ups, light/medium/heavy commercial vehicles, trailers, vans |
| Construction Equipment Loans | Up to AED 5 million; 85% of equipment cost and insurance | Max 36 months | New and used equipment |
| Fleet Financing | Up to 80% of fleet value | Up to 60 months | New and used vehicles |
| Auto Loans | not stated | not stated | Executive/commercial fleet, specialised trucks |

#### Property-backed loans
| Product | Amount | Tenure | Other stated terms |
|---|---|---|---|
| Commercial property (retail space and office loan) | Up to AED 20 million | not stated | Purchase of ready-built commercial property |
| Loans Against Property (Business Banking Property Power Loan) | Up to AED 20 million; max 70% of market value (UAE nationals) / 60% (expatriates) | Max 15 years | Commercial or residential property |

#### Eligibility and documents (as shown on the page)
- Vehicle and equipment loans: LLC, Sole Proprietor Establishments, Free Zone Sole Proprietor Establishments, Free Zone Companies, Branches of Foreign Companies in the UAE. Documents: 6 months bank statements and audited financials (if applicable), passport and visa of owner/director/partner, trade licence and MOA, power of attorney, plus fleet details or an equipment inventory.
- Property-backed loans (individuals): self-employed and salaried; minimum monthly salary AED 30,000; max 65% of property value (property loan); completed freehold/transferable property; 12 months statements; audited financials for 2 years above AED 1 million.
- The page does not attribute a separate eligibility block to Merchant Loan (POS), Small Business Loan, Semi Secured or Loan Against FD.

#### Not on this page
Interest/profit rates, fees, minimum turnover, credit criteria, and how Merchant Loan (POS) is serviced (e.g. repayment from POS settlements).

Related (from the earlier packages document): working capital facilities from AED 250,000; term loans up to AED 20 million; overdrafts, trade finance, equipment loans; Supply Chain Finance.
