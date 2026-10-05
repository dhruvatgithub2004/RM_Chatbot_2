# Business impact — RM Co-pilot

This document sizes the business impact of the RM Co-pilot from the data in the prototype and states the assumptions behind every figure. **All data is synthetic** (150 demonstration merchants, as of 3 Aug 2026), so the figures show how the value is built and how large it is *per 150 merchants*. They are not forecasts for any real portfolio. Where a number is an assumption and not a result, it is labelled as one.

---

## 1. Summary

| Lever | What the data shows | Confidence |
|---|---|---|
| **Retention** | 15 merchants have lost 10% or more of their volume in 30 days and 10 have dormant terminals. The volume they stopped processing is AED 2.27M a month, worth about AED 22.6k a month of margin | Calculated from data; recovery rate is an assumption |
| **Growth** | The engine proposes a lending or cross-sell pitch for 115 merchants (55 lending, 60 cross-sell), with AED 39.7M of proposed lending limits | Calculated; conversion is unknown |
| **Pricing** | The rate model recommends cuts for 93 merchants. Applying all of them would *reduce* monthly revenue by about AED 178k | Calculated; a risk to manage, not an upside |
| **RM productivity** | Replaces reading 150 merchants' data with a ranked list | Assumption; needs a measured baseline |
| **Governance** | Grounded, checked and logged recommendations | Qualitative |

**The honest headline:** the clearest and most defensible value is *seeing* at-risk and under-served merchants early and consistently. The tool does not create revenue by itself, since the RM does. The size of the benefit depends on how often RMs act and how often those actions work, which only a pilot can measure (section 7).

## 2. The baseline: the book in the prototype

| Measure | Value | How it is derived |
|---|---|---|
| Merchants | 150 | Merchant file |
| POS volume, last 30 days | AED 53.5M | Sum of daily POS volume |
| POS volume, prior 30 days | AED 55.7M | Same, 30 days earlier (book down 4.0%) |
| Gross merchant-fee revenue per month | about AED 1.28M | Last-30-day volume x each merchant's current rate |
| Margin over interchange per month | about AED 0.59M | Volume x (current rate minus modelled interchange cost) |
| Merchants flagged for attention | 29 (19.3% of the book, AED 19.1M of volume, 35.7% of the total) | Rule-based attention score |
| Merchants in the High risk segment | 11 | Merchant file |

Interchange is calculated from the Visa UAE table. The rates and the spread are synthetic, so margins are illustrative.

## 3. Lever 1: retention

### What the data shows
| Group | Merchants | Volume last 30 days | Volume prior 30 days | Change |
|---|---|---|---|---|
| Dormant terminals now | 10 | AED 3.59M | AED 5.43M | down AED 1.84M (-34%) |
| Volume down 10% or more | 15 | | | down AED 2.27M |

- 13 of the 15 declining merchants are already on the flagged list. The dashboard's ranking is therefore doing what it was designed to do.
- The monthly margin on the volume those 15 merchants stopped processing is about **AED 22.6k a month**.
- The 10 dormant merchants carried about **AED 53k a month** of margin in the prior 30 days. This is the most at risk if their terminals do not come back.

### Scenario: what recovery is worth
The tool surfaces these merchants earlier and with a stated reason and next step. The value is the share of the lost volume that RM action wins back. **The recovery rates below are assumptions for illustration, not predictions.**

| Share of the AED 22.6k monthly margin recovered | Per month | Annualised run-rate |
|---|---|---|
| 25% | AED 5.6k | AED 68k |
| 50% | AED 11.3k | AED 135k |
| 75% | AED 16.9k | AED 203k |

These are small in absolute terms because the demonstration book has only 150 merchants and a monthly margin of about AED 0.59M. The ratio is what carries over: **at-risk margin is about 3.8% of the book's monthly margin** (22.6k of 591k). On a real book, scale it by the real margin and re-measure the share.

## 4. Lever 2: growth (lending and cross-sell)

### What the engine proposes
| Decision | Merchants |
|---|---|
| Retention (protect the relationship, only where there is dormancy or falling volume) | 32 |
| Cross-sell | 60 |
| Lending | 55 |
| Nothing worth pitching | 3 |

| Product pitched | Merchants | Proposed limits |
|---|---|---|
| Payroll / WPS Services | 52 | n/a |
| Small Business Loan | 35 | AED 4.2M in total (median AED 100k) |
| Merchant Loan (POS) | 15 | AED 18.6M in total (median AED 100k) |
| Trade Finance (smartTRADE) | 8 | n/a |
| Working capital facility | 5 | AED 16.9M in total (median AED 1.4M) |

These figures changed on 5 Oct 2026 when the engine was changed so that "retention" needs a dormant-terminal or falling-volume signal (see `Role of AI.md`, section 11). Before, it chose retention for 102 merchants and pitched only 44. The engine now pitches most of the book (115 of 150), so the larger pipeline below reflects broader pitching, not a larger opportunity.

**Read this carefully.** The AED 39.7M is the *proposed credit limits*, a pipeline size and not revenue. Turning it into revenue needs the margin on each loan, the take-up rate, and credit approval, none of which are in the data. The three largest limits account for 56% of it (the largest single one is AED 12.25M), and several are for merchants whose turnover is the same AED 3.5M value, shared by 9 merchants, that looks like a cap in the data. Treat the amount as illustrative.

### Why the targeting is the benefit
Each pitch is a product the merchant does not already hold, within the product's published limits (checked by code), with a reason that cites the merchant's own numbers. The expected gain is fewer wasted calls and better-aimed ones. Conversion cannot be estimated from synthetic data.

## 5. Lever 3: pricing (handle with care)

The rate model compares each merchant's current rate with a modelled rate (interchange plus a predicted spread).

| Direction | Merchants | Monthly revenue effect if every one were applied |
|---|---|---|
| Reduce | 93 | -AED 178k |
| Hold | 40 | -AED 4k (small gaps, within 0.10 percentage points of the model rate) |
| Increase | 17 | +AED 1.7k |
| **Net** | 150 | **-AED 180k a month, about 30% of the AED 591k margin** |

**Implication:** blanket use of the rate suggestions would cost margin. The value is in *selective* use: offering a reduction to a merchant at real risk of leaving, or reviewing an under-priced account at renewal, always as the RM's decision. Because the spread model is trained on synthetic data, these rates are illustrative and should not be presented as a pricing opportunity. The pricing figures here are a reason to keep the RM in control, not a benefit claim.

## 6. Lever 4: RM productivity and consistency

Today, knowing who to call this week means reading each merchant's data. The Co-pilot replaces that with a ranked list, a reason and a next step, and answers follow-up questions in seconds.

The time saved has not been measured. The formula to fill in with the bank's own figures:

`hours saved per RM per month = reviews per month x (minutes today - minutes with the tool) / 60`

| Input | Where it comes from |
|---|---|
| Merchants an RM covers | The bank's RM allocation (the demonstration data has 25 RMs for 150 merchants, about 6 each, which is unrealistically small) |
| Reviews per merchant per month | Current RM practice |
| Minutes per review today | A time study with a few RMs |
| Minutes per review with the tool | The same RMs in a pilot |

Consistency is the second benefit: every merchant is scored every time, including small ones that attention tends to skip, using the same rules and the same product knowledge.

## 7. How to prove it: a pilot

The prototype shows what the tool recommends. It cannot show whether recommendations win business. A pilot should measure:

| Question | Measure | Design |
|---|---|---|
| Does it find at-risk merchants? | Share of flagged merchants whose volume fell or who left, versus unflagged | Back-test on historical data first, then run live |
| Does acting on it retain volume? | Volume trend of contacted versus not-contacted flagged merchants | Compare RMs using the tool with matched RMs not using it |
| Do the pitches convert? | Conversion of suggested pitches versus RMs' own pitches | Track every pitch and outcome |
| Does it save time? | Minutes to prepare a review | Time study before and during the pilot |
| Do RMs trust it? | Share of suggestions accepted; share of answers corrected | Audit log and RM feedback |
| Is it safe? | Rate of wrong or ungrounded answers | Review a sample from the audit log weekly |

Back-testing the attention score on history is the cheapest first step. It needs only past POS data and the outcomes (merchants who left or declined).

## 8. Costs to weigh against the benefit

| Cost | Size, from the prototype |
|---|---|
| Suggestion run | About 4,300 input tokens per merchant, about 650k tokens for 150 merchants, one batch per data refresh |
| Portfolio chat | About 17,600 tokens per question for 150 merchants (the whole book is sent each time) |
| Merchant chat | About 5,100 tokens per question |
| Pricing | Apply the provider's current price list to these token counts |
| Build and run | Data feeds, hosting, security review, support, and RM training (see `feasability.md`) |

Token counts are estimated as characters divided by four. They grow with the number of merchants unless the design in `feasability.md` section 3.3 is adopted.

## 9. What this document does not claim

- No claim of time saved, revenue gained or churn avoided in a real portfolio.
- No claim that the pitch pipeline will convert. The AED 39.7M is proposed limits.
- No claim that the suggested rates are a pricing opportunity.
- The attention score is rule-based and its thresholds await business sign-off (see `BLOCKERS_AND_PENDING_INPUTS.md`, item 5), so the count of flagged merchants may change.

## 10. Where the numbers come from

| Figure | Source |
|---|---|
| Volumes, dormancy, declines | `client_fact` table, built from `pos_daily_acquiring_v3.csv` |
| Margins and rate gaps | `merchant_profiles_v3.csv` (current rate, interchange, rate gap) |
| Flags, decisions, pitches, limits | `client_priority` and `client_suggestion` tables |
| Prompt sizes | Measured on the live knowledge page and context builders |
