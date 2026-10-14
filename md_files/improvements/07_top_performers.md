# Improvement 07: "Top performers" on the dashboard, step 3

| | |
|---|---|
| **Status** | Done, 7 October 2026. Step 3; the other merchant types come later, one at a time. |
| **What it is** | A third section on the dashboard, below "Cross-sell targets" and "Act now": the five largest merchants by card volume, among the top performers that drive the bulk of the portfolio. |
| **Tests** | 11 in `backend/tests/test_top_performers.py`; two earlier tests loosened (section 6). Full suite 188 passing. Frontend typechecks. |

## 1. What the RM sees

A section "Top performers" with five cards in a row. The line under the title says how concentrated the volume is: "The 15 top performers hold 63.6% of the portfolio's card volume." Each card shows:

- Rank, merchant name, industry and city, and a "Top performer" tag.
- **Why it is a top performer**, with the figures in bold:
  - Ranked 1 of 150 merchants by card volume.
  - Its share of the portfolio's card volume (for example 7.3%).
  - Its share of its own city's card volume (for example 22.2% of Sharjah's). This answers the "regional volume" part of the brief.
  - The trend: "Card volume down 3% against the prior 30 days".
- **What to do**, tagged **AI** or **Rules**: the relationship check-in step. The AI engine's own explanation shows when the AI wrote it.
- A "View profile" button. The whole card opens the profile.

A fold-out line, "How a merchant gets on this list", states the rule. There are no filters.

## 2. What counts as a top performer

The **top 10% of merchants by card volume over the last 30 days**, which is 15 of 150. The dashboard shows the five largest of them.

**Card volume, not turnover.** The supplied average monthly turnover has ties: nine merchants have exactly the same figure (6.0% of the portfolio each). Ranking on it would make "top five" an arbitrary pick among nine. Card volume over the last 30 days differs for every merchant, so the ranking has no ties. It is also literally "high volume".

**A top performer can also be a churn risk or growth-ready.** The merchant then carries both codes. If it is a churn risk, its card shows the retention step instead of the check-in, adds "Also a churn risk, so retention comes first", and follows the AI engine's rule that a top performer at risk needs retention first. Churn risk and growth-ready never overlap with each other.

The 10% cut is a policy parameter set against the demonstration data and needs product sign-off before real use.

## 3. Who is on the list today

| # | Merchant | City | Share of portfolio volume | Share of city volume | Trend |
|---|---|---|---|---|---|
| 1 | King Tech Store | Sharjah | 7.3% | 22.2% | down 3% |
| 2 | Rice Learning Center | Dubai | 7.2% | 18.6% | up 8% |
| 3 | Garcia Salon | Ras Al Khaimah | 6.9% | 43.6% | down 6% |
| 4 | White Motors | Ras Al Khaimah | 6.8% | 43.4% | down 2% |
| 5 | Green Wellness Center | Sharjah | 6.8% | 20.8% | down 5% |

Four of the five are slightly down on the prior 30 days. None of the five is a churn risk. Two of the top 15 are in the High risk segment, and three are churn risks (they sit further down the top-performer ranking).

Rice Learning Center and King Tech Store also appear in the cross-sell list. The sections are independent, so a merchant can be on more than one.

## 4. Where the AI comes in, and where it does not

- **Rules choose and rank the merchants** from card volume. The list can be checked against each merchant's figures.
- **The AI engine writes the step** where it made an "engage" decision for the merchant (or a retention decision, for a top performer at risk). Otherwise the card shows rule-based wording, tagged "Rules".
- **Today all five say "Rules".** Only 16 AI decisions exist, and the model service is off.
- **To get AI decisions:** with the model running, run `python -m app.suggest_llm --segments` from `backend/`. The engine's prompt now briefs it in card volume: it is asked to name the merchant's volume rank and its share of the portfolio's and its city's card volume.

## 5. What changed

| File | Change |
|---|---|
| `backend/app/segments.py` | The `top_performer` segment; volume rank and shares (portfolio and city) for every merchant; the definition text; a helper |
| `backend/app/readers.py` | `top_performers()`: the list, the reasons, the step |
| `backend/app/main.py` | `GET /api/dashboard/top-performers` |
| `backend/app/suggest_llm.py` | The engine is briefed with volume rank and shares; its check-in fallback wording and the "engage" prompt line use card volume |
| `frontend/components/TopPerformers.tsx` (new) | The section |
| `frontend/components/Dashboard.tsx`, `lib/types.ts`, `lib/api.ts` | Place it; types and the API call |

## 6. Tests

11 tests: the top performers are exactly the top 10% by card volume and the ranking has no ties; the shares are the merchant's share of the portfolio's and its city's card volume; the supplied turnover does have ties at the top (which is why card volume is used); a top performer keeps another segment code; the list is the five largest by card volume with the right counts; the card shows the rank, shares and trend; without an AI decision the step is the rule-based check-in; the AI engine's "engage" decision is used and other kinds are not; a top performer that is a churn risk gets retention first; the endpoint returns the data behind each card; the suggestion engine is briefed in card volume and can fall back to a check-in.

Two earlier tests were loosened because a merchant can now carry two segment codes: they asserted the codes were exactly one, and now assert the first is the expected one.

## 7. What is not solved

- **There is no check-in due date.** The data has no record of when the RM last spoke to a merchant, so the list cannot say who is overdue. The page says so. A "mark as contacted" log would fix this; it would be new input, not new data.
- **The list is the same big merchants every week** apart from small shifts in volume. With no contact record, it cannot rotate.
- **No ratings on these cards yet.**
- **The AI wrote none of the five steps.** See section 4.
- **The 10% cut and the 30-day window are assumptions.**
- **"Regional" means city.** The data has a city for each merchant and nothing finer.
- **Revenue figures are not shown,** as with the other sections.

## 8. Questions a judge may ask

**"Why card volume and not turnover?"**
The supplied turnover has ties: nine merchants share the same figure, so a top five by turnover would be arbitrary. Card volume over the last 30 days has no ties.

**"How do you know these drive the bulk of the volume?"**
The 15 top performers hold 63.6% of the portfolio's card volume, and the card shows each merchant's own share of the portfolio and of its city.

**"Who needs a check-in this week?"**
We can't say. We have no record of the last contact. The list shows who matters most and how each is trending, and says it can't show who is overdue.

**"What if a top performer is at risk?"**
It gets the retention step first, the card says it is also a churn risk, and it is also visible in the churn-risk list when it ranks high enough there.

## 9. Changelog

- 7 Oct 2026: added the `top_performer` segment, volume rank and shares, the list, the endpoint and the dashboard section; briefed the AI engine in card volume; loosened two tests; backend restarted.
