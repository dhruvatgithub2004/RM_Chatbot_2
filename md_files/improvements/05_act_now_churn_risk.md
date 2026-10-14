# Improvement 05: "Act now" on the dashboard, step 1: high-value churn risks

| | |
|---|---|
| **Status** | Done, 7 October 2026. First of several steps; the other merchant types come later, one at a time. |
| **What it is** | The top of the dashboard shows the five merchants an RM should act on now. Today that means the five highest-value churn risks. |
| **Tests** | 12 new in `backend/tests/test_segments.py`; full suite 165 passing, with nothing stubbed. Frontend typechecks. |
| **Also fixed** | `app/segments.py` did not exist although `suggest_llm.py` imports it, so the backend could not start. It exists now, which also made the rate-range work (improvement 04) visible. |

## 1. What the RM sees

A section on the Dashboard, "Act now: High-value churn risks", with five cards in a row. It was built first but is shown second, under the cross-sell targets (display order changed on 7 October). Each card shows:

- Rank, merchant name, industry and city.
- Value tier (High or Medium).
- **Why it is flagged**, as bullet points with the figures in bold: inactive terminals, volume down against the prior 30 days, volume below the merchant's own earlier average.
- **What to do**, tagged **AI** or **Rules**, with the step in bold. The AI's own explanation shows when the AI wrote it.
- A "View profile" button. The whole card opens the profile.

The cards no longer show the estimated monthly revenue or the revenue lost against baseline. The list is still ranked by that lost revenue, and both figures are still in the `/api/dashboard/act-now` response. A fold-out line, "How a merchant gets on this list", states the rule. There are no filters on this section.

The rest of the dashboard (the nine opportunity boxes, the tables, the Opportunities / All tabs and the search) is **hidden**, as requested. The code is still in `Dashboard.tsx` behind `SHOW_ALL_MERCHANTS = false`; set it to `true` to bring it back. The header line "29 clients flagged for attention this week" stays.

## 2. What counts as a high-value churn risk

**At risk**: any one of these.

| Trigger | Rule | Why this stands in for what was asked |
|---|---|---|
| Sudden drop | Card volume over the last 30 days is down 10% or more against the prior 30 days | "Sudden drop in transaction volume" |
| Missed activity | POS terminals inactive now | "Missed order cycles". **The data has card activity, not orders**, so inactive days is a stand-in |
| Below baseline | Last 30 days at least 15% below the merchant's own average over the earlier complete months (up to 6, leaving out the latest month, which overlaps the last 30 days), **and not rising** | "Declining revenue compared to their historical baseline" |

The "not rising" guard keeps out merchants already recovering. Without it, Brown Builders ranked second although its volume was up 5.6% on the prior 30 days.

**High value**: estimated monthly revenue in the top two thirds of the portfolio (tiers High and Medium). Estimated monthly revenue is average monthly turnover times the current rate. It is an estimate, not booked revenue, and the rate is synthetic, so the figures are illustrative.

**Ranking**: estimated monthly revenue lost against the merchant's own baseline, largest first. This ranks a large merchant that has collapsed above a large one with a mild dip and above a small one that has collapsed. Ranking by revenue alone would have put Arellano Tech Store, down only 10%, first.

These thresholds are policy parameters set against the demonstration data and need product sign-off before real use.

## 3. Who is on the list today

22 merchants are at risk, and 15 of them are Medium or High value. The top five:

| # | Merchant | Value | Revenue lost vs baseline | Volume vs prior 30 days | Inactive |
|---|---|---|---|---|---|
| 1 | Cruz Beauty Lounge | High | AED 21,756 a month | down 29% | 8 days |
| 2 | Arellano Tech Store | High | AED 8,557 | down 10% | no |
| 3 | Miller Technologies | High | AED 7,766 | down 43% | 14 days |
| 4 | Bell Kitchen | High | AED 4,302 | down 8%, but 33% below its baseline | no |
| 5 | Bowers Grocery | High | AED 2,912 | down 46% | 14 days |

## 4. Where the AI comes in, and where it does not

- **Rules choose and rank the merchants.** The list can be checked against the merchants' own figures, and a model does not decide who is on it. A language model picking five of 150 merchants would be hard to verify.
- **The AI writes the recommended step.** If the suggestion engine has made a retention decision for the merchant, the card shows it, tagged "AI", with its explanation. Otherwise the card shows rule-based wording, tagged "Rules". A stored decision of another kind (for example a lending pitch) is not shown on this card.
- **Today four of the five cards say "Rules".** Only Bowers Grocery has a stored AI retention decision, and it was made before this segment existed, so it is not written with the segment in mind. The model service is off, so I could not generate new ones.
- **To get AI-written steps for all 22 at-risk merchants:** with the model running, run `python -m app.suggest_llm --segments` from `backend/`. The engine's prompt already tells it about segments and asks for a retention call before any pricing action.

## 5. What changed

| File | Change |
|---|---|
| `backend/app/segments.py` (new) | Assigns each client its facts and its segment, picks and ranks the list. Provides what `suggest_llm.py` reads from it |
| `backend/app/readers.py` | `act_now()`: the list with each merchant's facts and its action |
| `backend/app/main.py` | `GET /api/dashboard/act-now` |
| `frontend/components/ActNow.tsx` (new) | The section |
| `frontend/components/Dashboard.tsx` | Shows it at the top; adds the missing `engage` label so the typecheck passes again |
| `frontend/lib/types.ts`, `api.ts` | Types and the API call |

## 6. Tests

12 new tests in `test_segments.py`: every client has the fields the suggestion engine reads; value tiers are exact thirds; the churn rule matches each client's own figures across all 150; a recovering merchant is not listed; the baseline leaves out the latest month; the reasons name the figures; the list is five Medium or High merchants ranked by revenue lost, and nobody left out lost more than someone included; a low-value merchant is never listed; the rule-based step appears without an AI decision; the AI's retention decision is used when it exists and other decisions are not; the endpoint returns the data behind each card; the suggestion engine receives the segment and falls back to a retention call.

## 7. What is not solved

- **"Missed order cycles" are not measured.** There is no order data. Inactive POS days is the stand-in, and the card says "No card activity".
- **Revenue figures are estimates** (turnover times a synthetic rate).
- **The AI wrote only one of the five steps.** See section 4.
- **No ratings on these cards yet.** The Yes / No rating and "Why this?" panel from improvement 03 work on suggestions, and are not on this section. The card shows its evidence directly instead.
- **The other four merchant types** (cross-sell targets, stalled onboarding, top performers, dormant reactivation) are not built. Stalled onboarding cannot be built with this data (no recent sign-ups, no sign-up date or first-transaction date).
- **The old Opportunities / All view is hidden, not deleted.** One switch in `Dashboard.tsx` (`SHOW_ALL_MERCHANTS`) brings it back. The Yes / No rating and "Why this?" panel are still available on the Suggestions screen.
- **Dormant merchants are included here.** Inactive terminals count as a churn trigger because you listed missed activity under churn. If dormant reactivation later becomes its own step, the two will need to be separated.

## 8. Questions a judge may ask

**"Is the AI choosing who to call?"**
No. Rules choose and rank the merchants from the data, so the choice can be checked. The AI writes the recommended step where it has decided one, and the card says which it is.

**"What does high-value mean?"**
The top two thirds of the portfolio by estimated monthly revenue, which is turnover times the rate. It is an estimate. The ranking uses the revenue lost against the merchant's own baseline, so a collapse in a valuable merchant ranks first.

**"How do you measure missed order cycles?"**
We don't have orders. We use days with no card activity at all, and we label it that way.

**"Why is a merchant with a mild 10% dip on the list?"**
Arellano Tech Store is among the largest merchants, so even a 10% fall is AED 8,557 a month, more than the collapses of several smaller merchants.

## 9. Changelog

- 7 Oct 2026: removed the estimated monthly revenue line and the revenue-lost figure from the cards.
- 7 Oct 2026: hid the Opportunities / All view and the nine opportunity boxes, so the dashboard shows only the Act now list.
- 7 Oct 2026: added `segments.py`, `act_now()`, the endpoint and the Act now section; added the "not rising" guard after Brown Builders ranked second while recovering; five cards in one row; backend restarted on the new code.
