# Improvement 08: "Dormant reactivation" on the dashboard, step 4

| | |
|---|---|
| **Status** | Done, 7 October 2026. Step 4; the other merchant types come later, one at a time. |
| **What it is** | A fourth section on the dashboard, below "Top performers": the five merchants with the most valuable history whose POS terminals have gone quiet. |
| **Tests** | 6 in `backend/tests/test_dormant.py`. Full suite 194 passing. Frontend typechecks. |

## 1. What the RM sees

A section "Dormant reactivation" with five cards. The line under the title says how many merchants have inactive terminals now (10). Each card shows:

- Rank, merchant name, industry and city, and the value tier.
- **Why it is a target**, with the figures in bold: days the terminals have been inactive, the merchant's earlier monthly card volume (AED), and the fall in card volume against the prior 30 days.
- **What to do**, tagged **AI** or **Rules**: "Reactivate the POS terminals: check the hardware, then call the client", or the AI engine's own retention step where it made one.
- A "View profile" button. The whole card opens the profile. A fold-out line states the rule. There are no filters.

## 2. What counts as dormant, and the decision that differs from the brief

The brief says "inactive 30 to 90 days". **That rule would give an empty list**: the longest inactive run in the data is 24 days and none reaches 30. The list is instead the merchants whose **terminals are inactive now** (10 merchants, 6 to 24 days). This is stated on the page.

**Ranking:** the merchant's own average monthly card volume over its earlier complete months. This is the nearest figure we have to historical value. It is not true lifetime value (there is no revenue history), and the page says so.

**Overlap with Act now:** every dormant merchant is also a churn risk, so three of the five here also sit on the Act now list. The sections are independent, as with cross-sell and top performers; here the dormant card gives the specific terminal fix, and Act now covers high-value risks of every kind.

## 3. Who is on the list today

| # | Merchant | City | Inactive | Earlier monthly volume | Trend |
|---|---|---|---|---|---|
| 1 | Cruz Beauty Lounge | Ajman | 8 days | AED 3,593,495 | down 29% |
| 2 | Miller Technologies | Sharjah | 14 days | AED 674,336 | down 43% |
| 3 | Fisher Suites | Sharjah | 12 days | AED 265,930 | down 46% |
| 4 | Bowers Grocery | Abu Dhabi | 14 days | AED 243,878 | down 46% |
| 5 | Williams Cargo | Dubai | 15 days | AED 172,587 | down 49% |

Williams Cargo shows an AI-written step (an existing stored retention decision); the other four are rule-based.

## 4. Where the AI comes in

Rules choose and rank the merchants from the facts. The AI engine writes the step where it made a retention decision for the merchant; otherwise the card shows rule-based wording tagged "Rules". To generate more AI decisions, with the model running: `python -m app.suggest_llm --segments` from `backend/`.

## 5. What changed

| File | Change |
|---|---|
| `backend/app/segments.py` | `dormant_now` and `earlier_monthly_volume_aed` per merchant; `dormant_targets()`; the definition text. Segment codes are unchanged |
| `backend/app/readers.py` | `dormant_reactivation()` |
| `backend/app/main.py` | `GET /api/dashboard/dormant` |
| `frontend/components/DormantReactivation.tsx` (new) | The section |
| `frontend/components/Dashboard.tsx`, `lib/types.ts`, `lib/api.ts` | Place it; types and the API call |

## 6. What is not solved

- **The 30 to 90 day rule can't be tested on this data.** If real data has longer runs, the threshold needs a product decision.
- **No lifetime value.** Earlier volume is a stand-in.
- **No record of reactivation attempts**, so the list can't say who has already been called.
- **The cause is unknown.** Inactive terminals can mean broken hardware, a closed shop or a switch to a competitor. The card says what to check, not which it is.
- **Only 16 AI decisions exist**, so most steps are rule-based.

## 7. Questions a judge may ask

**"Why not 30 to 90 days?"** No merchant in the data has been inactive 30 days; the longest is 24. Using the brief's rule would show nothing, so we use "inactive now" and say so.

**"Is this just the churn list again?"** Partly: every dormant merchant is a churn risk. This list is narrower and ranked by historical volume, and it gives the terminal-specific action.

## 8. Changelog

- 7 Oct 2026: added dormant flag and earlier volume to the segment facts, the list, the endpoint and the dashboard section; 6 tests; backend restarted.
