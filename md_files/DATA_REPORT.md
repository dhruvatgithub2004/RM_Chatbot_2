# Data Report: Input Data Files

Written 8 October 2026 from the files in `structured_data/` as they stand. Every figure was computed from the CSVs (150 merchants, 36,000 daily POS rows). The "real-world" comparisons are my general knowledge of UAE merchant acquiring. I did not check them against a source, so treat them as sanity checks, not benchmarks.

**Short verdict.** The data is a well-built synthetic set. Merchant records are internally consistent, and the daily POS series carries industry-specific behaviour (ticket size, transactions per day, weekday pattern, volatility). It has real gaps: negotiated rates do not vary with merchant size, there is no seasonality or Ramadan effect, the portfolio drifts downward, and the top-end turnover is a capped placeholder. The volume changes ("lifts") are in a believable range for the middle of the portfolio but too thin on the upside.

---

## 1. What the files are

| File | Rows | What it holds |
|---|---|---|
| `merchant_profiles_v3.csv` | 150 | One row per merchant: identity, industry/MCC, legal form, licence authority, package, RM and branch, balance, turnover, score, risk segment, limits, current and suggested rate, interchange, margin, opportunity tier. 36 columns. |
| `pos_daily_acquiring_v3.csv` | 36,000 | One row per merchant per day, 240 consecutive days (7 Dec 2025 to 3 Aug 2026): volume, transaction count, chargeback count and ratio, average ticket, terminal status, card type. |
| `merchant_products_held_v2.csv` | 150 | 0/1 flags for 11 bank products. |
| `merchant_rate_waterfall_v1.csv` | 150 | Breakdown of each suggested rate: interchange + base spread + eight driver contributions. |
| `merchant_opportunity_reasons_v1.csv` | 150 | Opportunity tier with z-scores and the top three reasons. |
| `ntb_cross_sell_candidates.csv` | 89 | New-to-bank product candidates (75 merchants): Payroll/WPS (69 rows), Trade Finance via smartTRADE (20 rows). |
| `business_banking_packages_and_charges.md`, `enbd_business_loans_public_reference.md`, `rm_product_knowledge.md` | text | Product and fee reference used by the chat. Not numeric inputs. |

The project's own `backend/data_quality_report.json` shows 0 quarantined rows and 5 warnings (duplicate business names, independent limits, risk segment not tracking score, 38 clients with a suggested rate but "no change", 64 clients below the smallest facility size).

Completeness: no nulls in the profile or POS files, no duplicate merchant-day keys, every merchant has exactly 240 days.

---

## 2. Features of the data

### 2.1 Portfolio shape

| Item | Value |
|---|---|
| Merchants | 150 across 16 industries (one MCC per industry) |
| Industry sizes | Construction 15, Grocery 14, Wholesale 12, Salons 11, five industries at 9–10, down to Jewelry 5 |
| Cities | Dubai 65, Sharjah 40, Ras Al Khaimah 18, Ajman 16, Abu Dhabi 11 |
| Legal forms | LLC 34, Branch of Foreign Co 29, FZE 29, Sole Est. 22, FZCO 18, Civil Co 18 |
| RMs / branches | 25 RMs (3 to 13 merchants each), 8 branch IDs in use |
| Tenure | 0.75 to 6.0 years, median 3.4 |
| Risk segment | Low 91, Medium 48, High 11 |
| Packages | Prime 39, Preferred 39, Connect 29, Prestige 19, Proprietor 13, Platinum 9, Emirati Business 2 |
| Terminals | 1: 9, 2: 70, 3: 24, 4: 47 |

### 2.2 Money fields (profile file)

| Field | Min | Median | Mean | Max |
|---|---|---|---|---|
| Monthly turnover (AED) | 3,403 | 200,000 | 388,972 | 3,500,000 |
| Account balance (AED) | 745 | 47,343 | 141,360 | 2,053,840 |
| Current rate (%) | 2.27 | 2.39 | 2.41 | 2.68 |
| Blended interchange (%) | 0.54 | 1.30 | 1.23 | 1.71 |
| Margin over interchange (pp) | 0.62 | 1.12 | 1.17 | 2.01 |
| Credit score (synthetic) | 354 | 627 | 628 | 899 |

### 2.3 Daily POS series

| Item | Value |
|---|---|
| Portfolio card volume | AED 57.4M per month (30.4-day basis); AED 453M over the 240 days |
| Daily volume per merchant | median AED 4,494, mean 12,590, max 274,141 |
| Transactions per day | median 4, mean 51, max 2,580 |
| Chargebacks | 1,559 total; 2.2% of merchant-days have one; per-merchant mean ratio 0.21% |
| Dormant terminal days | 128 days across 10 merchants, all in July–August 2026, all with zero volume |
| Zero-volume days | all 128 are the dormant days; no active day has zero volume |

### 2.4 Product holdings

Everyone holds a Current Account and Merchant Acquiring. Business Online 82%, Business Credit Card 43%, Fixed Deposit 29%, Cash Management 25%, smartTRADE 17%, FX 14%, Rewards Card 13%, POS Loan 9%, Small Business Loan 5%. Merchants hold 2 to 8 products (median 4).

---

## 3. How the data is realistic

1. **Industry fingerprints are right.** Median daily transactions and ticket by industry: Restaurants 103 tx at AED 68; Grocery 74 tx at AED 63; Salons 43 tx at AED 162; Fitness 25 tx at AED 215; Auto Repair 13 tx at AED 480; against B2B/professional types (Wholesale, Logistics, IT, Real Estate, Construction) at about 1 tx/day with AED 2,000 to 6,000 tickets. Retail-heavy industries have high count, low ticket; B2B have the opposite.
2. **Weekday pattern follows the business type.** B2B industries (Construction, Logistics, Wholesale, IT, Real Estate) run at 1.15–1.24x the average on Mon–Thu and Sun and drop to 0.44–0.57x on Fri and Sat. Consumer industries (Restaurants, Salons, Retail, Fitness, Grocery, Hotels, Jewelry) peak 1.12–1.20x on Fri and Sat. This is the right direction.
3. **Volatility is plausible.** Median coefficient of variation of daily volume is 0.31 (range 0.14 to 0.66). B2B merchants are the most volatile (about 0.4) and consumer ones the steadiest (0.2 to 0.3). Day-to-day autocorrelation is weakly positive (median 0.17).
4. **Heavy-tailed portfolio.** The top 10% of merchants (15) carry 63% of volume, the top 20% carry 75%, the bottom half 8.6%; Gini 0.69. A concentrated book like this is normal for acquiring.
5. **Pricing is tied to a real cost.** Interchange comes from each merchant's card mix and is the one non-illustrative column. It differs by industry in sensible ways (hotels, jewelry, IT at 1.4–1.7%; grocery 0.88–0.91%; real estate 0.54–0.65%). Rates sit 0.6 to 2.0pp above interchange.
6. **Cross-field consistency is high.**
   - Reported turnover tracks POS volume: log correlation 0.99; median POS-to-profile ratio 1.01.
   - Package tracks size: Proprietor/Prime/Connect for the small, Preferred/Prestige in the middle, Platinum for all nine merchants at AED 3.5M. Median balance rises with each tier (AED 12K, 23K, 79K, 173K, 994K).
   - Balance is 15–60% of monthly turnover. Monthly POS limit is 1.4–1.8x turnover. The largest single day reaches 30–70% of the daily limit and last-30-day volume 15–77% of the monthly limit, so nobody breaches a limit.
   - Average ticket equals volume divided by transactions to within AED 0.005.
   - City and licence authority never conflict (Sharjah DED only in Sharjah, RAKEZ only in RAK, and so on).
   - Half the merchants (75 of 150) have a cross-sell candidate, and the rationale text matches the profile (Payroll for high turnover, Trade Finance for B2B).
7. **A churn scenario is planted on purpose.** Ten merchants go dormant in July–August with volume falls of 23% to 81% over 30 days. That is a believable churn pattern and it exercises the Act-now logic.
8. **Chargeback rates are in a sane band.** All merchants average 0.18–0.33%, below common scheme monitoring thresholds of about 0.9–1%. The few large merchants have the most chargebacks in absolute count, as expected.

---

## 4. How the data is not realistic

| # | Issue | Evidence | Effect |
|---|---|---|---|
| 1 | **Turnover is a placeholder at the top and middle.** 58% of merchants (87) have exactly AED 50,000, 200,000, 500,000 or 3,500,000 as turnover. The median is therefore exactly 200,000, and 9 merchants sit at a hard cap of 3.5M. | Value counts: 200K ×36, 50K ×24, 500K ×18, 3.5M ×9 | Rank-by-turnover is meaningless (the project already ranks on POS volume for this reason). Rate tier, package, working-capital limit (460K, 100K, 1.4M, 12.25M) and POS limit all derive from these four numbers, so they cluster too. |
| 2 | **Negotiated rates do not scale with size.** Current rate runs 2.27–2.68% for everyone. The correlation of rate with log volume is -0.10, and Platinum merchants at AED 3.5M/month average 2.38% against 2.41% for the small ones. | rate by band: 2.41, 2.42, 2.40, 2.42, 2.38 | In practice, high-volume merchants pay much less than small ones. Here a AED 3.5M merchant is priced like a AED 50K one, so the rate-gap and "retention risk, reduce" outputs (93 of 150 flagged "Reduce") reflect a flat rate card, not a market. |
| 3 | **No seasonality or events.** Ramadan (about 18 Feb to 19 Mar 2026) shows ×0.89 to ×1.08 versus the month before (grocery 0.98, restaurants 0.98). Eid al-Fitr is ×1.03 and Eid al-Adha ×0.97 of average. There is no month-end or salary-week effect (weeks of month: 12.56K, 12.63K, 12.62K, 12.56K). | | Real F&B, grocery and gifts/jewelry see strong Ramadan and Eid lifts; none appear. |
| 4 | **Portfolio drifts down.** Mean daily volume falls from AED 13.3K (Dec) to 12.0K (Jul), about -10%. Comparing the last 60 days with the first 60, the median merchant is -3.7% and the *best* merchant is only +8.6%. Mean is -9.6%. | Monthly means 13.3, 13.1, 12.8, 12.7, 12.4, 12.4, 12.4, 12.0K | A real portfolio has genuine growers. Only 15 merchants are up 10% or more month-on-month. Some of the decline is driven by the dormant-terminal scenario and by sector declines such as Healthcare (-22%) and Construction (-18%) with no corresponding gainers. |
| 5 | **Card type is one label per day, not a mix.** Each row carries a single `card_type` and a merchant uses all five types across its 240 days, so a day's whole volume is attributed to one type. Ticket sizes then vary by card type (Business AED 1,816 median ticket at 1 tx, Debit AED 398 at 8 tx). | `groupby(merchant, date).size() = 1`; all 150 merchants have 5 types | Fine for portfolio-level mix, wrong at day level. A real feed would split volume per day by card type. |
| 6 | **Chargeback ratio is not derived from the counts.** `chargeback_ratio_pct` averages 0.21% on days when `chargeback_count` is 0 (97.8% of days). | non-zero ratio with zero count | The ratio is an independently generated field, not chargebacks ÷ transactions. Any analysis that recomputes it will disagree. |
| 7 | **Risk segment is not tied to score.** Score ranges overlap: High 387–813, Low 354–897, Medium 356–899, with similar means (646, 631, 618). Score vs volume trend correlation is -0.02. | the project's own warning | Credit score and risk class carry no behavioural signal. High-risk merchants have a lower median volume change (-3.0%) than Low (+1.1%), the only link. |
| 8 | **Terminals do not scale with volume.** Correlation of terminal count with log volume is -0.01. 4-terminal merchants are 31% of the book including AED 50K/month shops, and the 9 largest merchants mostly have 1 terminal. | 7 of 9 merchants above AED 1.5M have 1 terminal | Unlikely in practice. Not a problem for the app, since terminals are only used for dormancy. |
| 9 | **Several small-scale-for-industry figures.** Hotels: median AED 184K/month on 2 terminals and 3.4 tx/day. Grocery/supermarket: median AED 76K/month. Jewelry: median AED 62K with a AED 1.7K ticket and about 1 tx/day. Healthcare clinics: AED 63K/month. | by-industry table (section 5) | Plausible for tiny outlets, low for a hotel or a supermarket. The SME segment is mostly small independents, which is likely the intent. |
| 10 | **Dormancy and weekend rules.** All 128 dormant days fall in Jul–Aug, so no earlier history of terminal outages exists. B2B merchants dip on Fri–Sat, the old UAE weekend; since 2022 the federal weekend is Sat–Sun with a half-day Friday, so a Sunday dip would be expected for many B2B firms. | `dormant days by month: Jul 98, Aug 30` | Minor, but a reviewer who knows the UAE will notice. |
| 11 | **Other mechanical artefacts.** 2 pairs of duplicate business names; synthetic names ("Curtis Mart", "Hardy Style Co"); every merchant has the same base spread (0.9482pp) so the spread is purely driver contributions; balances and tenure are uniform-looking (balance/turnover bounded 0.15–0.60, tenure bounded 0.75–6.0 years); merchants cover only 8 of 14 branch IDs, with branch not tied to city. | | Signs of generation by rule. |

---

## 5. Diversity in behaviour, volume and revenue

### 5.1 Behaviour by industry

Volumes are POS-derived monthly figures (mean daily × 30.4). "Δ30d" is the median change in the last 30 days against the prior 30.

| Industry | n | Median monthly volume (AED) | Range (AED) | Median ticket (AED) | Tx / day | Daily CV | Δ30d | Interchange |
|---|---|---|---|---|---|---|---|---|
| Auto Repair & Services | 7 | 212,973 | 51.8K – 3.66M | 480 | 12.8 | 0.2 | -2.5% | 1.24–1.42% |
| Construction & Contracting | 15 | 93,273 | 3.1K – 2.48M | 3,068 | 1.0 | 0.4 | +6.4% | 1.16–1.40% |
| Education & Training | 9 | 177,347 | 38.5K – 3.92M | 1,241 | 3.5 | 0.3 | 0.0% | 0.65% |
| Fitness & Gyms | 10 | 211,644 | 52.6K – 3.82M | 215 | 25.0 | 0.3 | -1.5% | 1.17–1.41% |
| Grocery & Supermarket | 14 | 76,002 | 27.5K – 528K | 63 | 73.9 | 0.3 | -0.4% | 0.88–0.91% |
| Healthcare Clinics | 6 | 63,478 | 52.1K – 172K | 279 | 7.1 | 0.3 | -4.5% | 1.27–1.37% |
| Hospitality - Hotels | 8 | 183,643 | 50.5K – 3.35M | 1,691 | 3.4 | 0.2 | +0.6% | 1.50–1.71% |
| IT Services & Consulting | 10 | 137,576 | 2.8K – 641K | 4,479 | 1.0 | 0.4 | -0.2% | 1.40–1.61% |
| Jewelry & Watches | 5 | 62,014 | 40.1K – 430K | 1,687 | 1.1 | 0.3 | -0.9% | 1.50–1.64% |
| Logistics & Freight | 10 | 103,497 | 16.6K – 269K | 2,111 | 1.0 | 0.4 | +4.3% | 1.31–1.44% |
| Real Estate Services | 7 | 185,478 | 50.6K – 433K | 6,101 | 1.0 | 0.4 | +6.0% | 0.54–0.65% |
| Restaurants & Cafes | 9 | 210,849 | 52.1K – 511K | 68 | 103.3 | 0.3 | -5.8% | 1.14–1.31% |
| Retail - Electronics | 8 | 51,027 | 30.3K – 3.93M | 600 | 6.3 | 0.3 | -2.9% | 1.22–1.47% |
| Retail - Fashion & Apparel | 9 | 215,981 | 74.9K – 559K | 289 | 25.1 | 0.2 | +1.5% | 1.19–1.40% |
| Salons & Spas | 11 | 215,883 | 4.5K – 3.81M | 162 | 43.3 | 0.2 | -1.9% | 1.22–1.42% |
| Wholesale Trading | 12 | 154,178 | 15.0K – 419K | 5,072 | 1.0 | 0.4 | +6.7% | 1.24–1.42% |

Reading it: behaviour differs clearly between industries on ticket, frequency, weekday shape and volatility. Within an industry the spread is wide (e.g. Salons AED 4.5K to 3.8M). The B2B industries are the only ones with positive 30-day lifts (Construction, Real Estate, Wholesale, Logistics).

### 5.2 Size bands (POS volume)

| Band (monthly) | n | Median ticket | Median tx/day | Median daily CV | Median Δ30d | Avg rate | Median balance (AED) | High risk |
|---|---|---|---|---|---|---|---|---|
| < 50K | 24 | 814 | 1.0 | 0.37 | +2.1% | 2.41% | 12,195 | 4% |
| 50–150K | 49 | 480 | 3.9 | 0.31 | -0.6% | 2.42% | 23,267 | 10% |
| 150–500K | 59 | 1,289 | 4.7 | 0.30 | +1.1% | 2.40% | 78,693 | 5% |
| 0.5–1.5M | 9 | 193 | 89 | 0.22 | -3.2% | 2.42% | 172,581 | 11% |
| > 1.5M | 9 | 883 | 146 | 0.23 | -3.4% | 2.38% | 993,990 | 11% |

Volatility falls as size grows (0.37 → 0.22), which is the right direction. Rates stay flat across bands (see issue 2). The nine largest merchants have a negative median lift.

### 5.3 Revenue

Estimated from POS volume × current rate (gross) and × margin over interchange (net). These are modelled, not booked.

| Measure | Gross (AED/month) | Net of interchange (AED/month) |
|---|---|---|
| Portfolio total | 1.37M | 0.63M |
| Mean per merchant | 9,151 | 4,225 |
| Median per merchant | 3,759 | 1,643 |
| 10th / 90th percentile | 1,013 / 12,541 | 443 / 6,260 |
| Largest merchant | 99,597 | 65,059 |

Revenue diversity is wide (median to max about 26x gross) and follows the volume skew in section 3. It is driven almost entirely by volume because the rate barely moves.

---

## 6. How client behaviour is maintained over time

- **One persistent profile per merchant.** Each merchant keeps its own level, volatility and ticket for all 240 days. A merchant's volume scale stays within a stable band, which is why POS and reported turnover correlate at 0.99. The coefficient of variation per merchant spans 0.14 to 0.66 while the day-to-day pattern stays stable.
- **Industry rules persist.** The weekday profile, ticket and frequency of each industry hold in every month.
- **Drift is mild and mostly downward.** Month-on-month change across 900 merchant-months: median -0.7%, interquartile range -7.3% to +6.3%, 5th to 95th percentile -18% to +16%.- **Event behaviour is scripted.** Dormancy appears only in the last 5 weeks, in 10 merchants, and always coincides with a volume fall. Other merchants show no outages. This is clean for demonstration but it means "behaviour change" is one planted pattern, not a mixture of organic ones.
- **Some behaviour is not maintained.** Card mix is re-drawn each day, chargebacks are random noise (day-level ratio not tied to counts), and the credit score never reacts to behaviour.

---

## 7. Are volumes and lifts in an appropriate range for size and industry?

### 7.1 Volumes

| Check | Result |
|---|---|
| SME range | 91% of merchants (137) fall between AED 15K and 1.5M per month (9 above, 4 below). Reasonable for UAE SME acquiring. |
| Per-industry scale | Right for restaurants, salons, fitness, auto repair, fashion. **Low** for hotels, supermarkets, jewelry, electronics (median AED 51K) and clinics. |
| Large outliers | 9 merchants at AED 3.5M turnover are well-formed, and POS volume agrees (about AED 3.3M to 3.9M). They have 1–2 terminals only, which is low for that scale. |
| Tiny tail | Several merchants at AED 3–5K per month (e.g. MER2109 IT services at AED 2.8K) would be inactive in reality. |
| Ticket vs industry | Good. Grocery AED 63, restaurant AED 68, real estate AED 6.1K. |
| Volume vs terminals | Not coupled (see issue 8). |

### 7.2 Lifts (30 days against the prior 30)

| Statistic | Value |
|---|---|
| Median | +0.5% |
| 25th / 75th percentile | -4.3% / +5.7% |
| 10th / 90th percentile | -9.7% / +9.9% |
| 5th / 95th percentile | -27.7% / +13.2% |
| Min / max | -81% / +34% |
| Up 10% or more (growth-ready signal) | 15 merchants (10%) |
| Down 10% or more | 15 merchants (10%) |
| Down 25% or more | 9 merchants (6%), most of them the dormant-terminal cases |

Assessment:

- **Middle of the distribution is realistic.** A ±5% month-to-month band with a ±10% shoulder is typical for SME card volume.
- **Downside tail is realistic and mostly explained.** The fall of -25% or worse comes from the planted dormant merchants.
- **Upside is thin.** Only 15 merchants exceed +10% and the maximum is +34%. Growth-stage SMEs, new-outlet openings and seasonal peaks (Ramadan, DSF, Eid, summer for hotels) would produce more and larger lifts. Over the longer 60-day windows no merchant reaches +10%.
- **Lifts do not scale with size.** The nine largest merchants have the most negative median change (-3.4%) and the small ones the most positive (+2.1%). Newer, smaller merchants growing faster is plausible, but the effect here looks random rather than designed.
- **Industry direction is partly sensible.** B2B (+4% to +7%) outperforms F&B (-5.8% for restaurants). Healthcare and restaurants decline in a way with no obvious cause.
- **Rate-change lifts.** The rate model proposes a reduction for 93 merchants (62%), hold for 40 and increase for 17. With rates tightly clustered at 2.3–2.5%, this "Reduce" majority is an artefact of every merchant being priced above the modelled rate (mean gap +0.23pp), not a market finding. The suggested rate uses a synthetic spread model, and the project shows it only as a range.

---

## 8. Practical consequences for the app and recommended fixes

If the aim is a more convincing demonstration, in rough order of value:

1. **Replace the four turnover anchors** with a continuous lognormal tied to industry and package, then rederive POS limits and working-capital limits. This removes ties, the 3.5M cap, and the 460K/100K/1.4M/12.25M clustering.
2. **Make rates depend on size and risk.** A tiered card rate (e.g. 1.2–1.8% for volume above AED 1M, 2.0–2.7% for small merchants) would make "Reduce / Hold / Increase" meaningful.
3. **Add seasonality**: a Ramadan and Eid lift for F&B, grocery and jewelry; a summer dip for hotels; a month-end effect. Use a Sat–Sun weekend for B2B.
4. **Seed real growers.** Give 15–20% of merchants a sustained +10% to +40% trend so "growth-ready" and "top performer" have natural candidates, and let the big accounts also grow.
5. **Fix day-level fields.** Split volume across card types per day, and compute `chargeback_ratio_pct` as count ÷ transactions.
6. **Tie risk to behaviour.** Let score drive risk segment and let volatility, chargebacks and dormancy move the score.
7. **Scale terminals with volume** and raise volume for hotels, supermarkets and jewelry stores to their typical size.

None of these needs new code in the app. They are changes to whatever script generated the CSVs, which is not in the repository.

---

## 9. Limits of this report

- Everything above is computed on synthetic data. Nothing was compared with real UAE acquiring data.
- Real-world statements (pricing by size, Ramadan lift, the 2022 weekend change, scheme chargeback thresholds) are from my general knowledge and were not verified against a source.
- Monthly volumes use mean daily volume × 30.4 days. August 2026 is a partial month (3 days) and is excluded from month-on-month figures.
- The trend figures include the 10 dormant-terminal merchants. Excluding them would lift the portfolio median change slightly but would not change the shape.
