# Improvement 06: "Cross-sell targets" on the dashboard, step 2

| | |
|---|---|
| **Status** | Done, 7 October 2026, in two passes (section 9). Step 2; the other merchant types come later, one at a time. |
| **What it is** | A section at the top of the dashboard, above "Act now" (it was built second; the display order was changed on 7 October so it comes first): the five merchants that do not yet hold a product the bank can offer them. |
| **Tests** | 12 in `backend/tests/test_cross_sell.py`. Full suite 177 passing. Frontend typechecks. |

## 1. What the RM sees

A section "Cross-sell targets" with five cards in a row. Each card shows:

- Rank, merchant name, industry and city, and the value tier.
- **Why it is a target**: first the product gap ("No Payroll / WPS Services on file"), then any growth figures in bold ("Using 77% of its monthly POS limit").
- **What to offer**, tagged **AI** or **Rules**: the cross-sell product. The AI engine's own explanation shows when the AI wrote it.
- A muted second line when the merchant also qualifies for a loan: "Also qualifies for: Working capital facility · up to AED 12,250,000". The loan is never the headline.
- A "View profile" button. The whole card opens the profile.

A fold-out line, "How a merchant gets on this list", states the rule. There are no filters.

## 2. What counts as a cross-sell target

A merchant is listed when **both** hold:

| Condition | Rule |
|---|---|
| Not at risk | It is not a churn risk. Those need retention first and are on the Act now list |
| A product it lacks | It does not yet hold a cross-sell product the bank can offer it: a supplied new-to-bank candidate that it does not already hold, or a cross-sell product the AI engine chose for it |

**The selection is not driven by POS.** A merchant does not need to be growing or near its POS limit to be listed.

**Ranking**: estimated monthly revenue (turnover times rate) **plus any growth in that revenue** since the prior 30 days. A growing merchant is lifted by the amount it has actually grown, so growth lifts the rank without an invented multiplier. Revenue figures are not shown on the cards, and the rate is synthetic, so they are illustrative.

**Growth-ready** (card volume up 10% or more against the prior 30 days, or 70% or more of the monthly POS limit used) is still computed. It adds a bullet to the card, lifts the rank through the growth term, and briefs the AI engine. It does not decide who is listed.

**The loan** comes from the same pitch the Opportunities view used (the AI engine's lending decision where it made one, otherwise the rule-based pitch). It is shown only as a second line.

The thresholds are policy parameters set against the demonstration data and need product sign-off before real use.

## 3. Who is on the list today

65 merchants are candidates. 15 of them are also growing or close to their POS limit, and 53 also qualify for a working-capital facility. The top five:

| # | Merchant | Why | Offer | Also qualifies for |
|---|---|---|---|---|
| 1 | Rice Learning Center | No payroll product; using 77% of its POS limit | Payroll / WPS Services | Working capital facility, up to AED 12,250,000 |
| 2 | Brown Builders | No payroll product | Payroll / WPS Services | Working capital facility, up to AED 12,250,000 |
| 3 | King Tech Store | No payroll product | Payroll / WPS Services | Working capital facility, up to AED 12,250,000 |
| 4 | Baird Hospitality Group | No payroll product | Payroll / WPS Services | Working capital facility, up to AED 12,250,000 |
| 5 | Short Salon | No payroll product | Payroll / WPS Services | Working capital facility, up to AED 1,560,000 |

All five are rule-based. Only one of them is also a POS-growth case.

## 4. Where the AI comes in, and where it does not

- **Rules choose and rank the merchants,** from the supplied candidates, the products held and the revenue figures.
- **The AI chooses the product and writes the reason** where the suggestion engine has made a cross-sell decision for the merchant. Otherwise the card shows the first supplied candidate, tagged "Rules".
- **Today all five say "Rules".** Only 16 AI decisions exist and the model service is off.
- **To get AI decisions:** with the model running, run `python -m app.suggest_llm --segments` from `backend/`. The engine's prompt describes the growth-ready segment.

## 5. What changed

| File | Change |
|---|---|
| `backend/app/segments.py` | The `growth_ready` segment and its reasons; the cross-sell definition text |
| `backend/app/readers.py` | `cross_sell_targets()`: the product-gap selection, the ranking, the loan second line |
| `backend/app/main.py` | `GET /api/dashboard/cross-sell` |
| `backend/app/suggest_llm.py` | One line in the prompt describing the `growth_ready` segment |
| `frontend/components/CrossSell.tsx` (new) | The section |
| `frontend/components/Dashboard.tsx`, `ActNow.tsx`, `lib/types.ts`, `lib/api.ts` | Place it; share the bold-figures helper; types and the API call |

## 6. Tests

12 tests: the growth-ready rule matches each of the 150 merchants' own figures and never overlaps churn risk; every merchant with a product it lacks is a candidate and no churn risk is; the selection is not driven by POS growth (most candidates have no growth signal, and the top five are not all growth cases); a product the merchant already holds is never offered; the list is five merchants ranked by revenue plus growth, and nobody left out scores higher than someone included; the card leads with the product gap; a loan is only ever a second line and matches the pitch; the offer is the first supplied candidate unless the AI decided; the AI's cross-sell decision is used when it exists; a lending or no-action decision does not remove the merchant; the endpoint returns the data behind each card; the engine is told about the segment.

## 7. What is not solved

- **Every card offers payroll.** The supplied candidates are 69 payroll and 20 trade finance, and the five highest-revenue candidates all lack payroll. The catalogue has only three cross-sell products (payroll, trade finance, business online), and no supplied candidate is business online.
- **Premium-tier upgrades are not covered.** The package minimum balances are text in the knowledge page, not structured data.
- **Card and insurance products** are not in the catalogue.
- **The AI wrote none of the five offers.** See section 4.
- **No ratings on these cards yet.**
- **The first supplied candidate is taken as the offer** when there are several. There is no ranking between a merchant's own candidates.
- **Four of the supplied candidates are for merchants in the High risk segment.** The rule-based NTB path has no risk filter, and neither does this list.
- **Thresholds are assumptions** (10% growth, 70% of the limit), taken from the existing attention score.

## 8. Questions a judge may ask

**"Isn't this just POS growth again?"**
No. A merchant is listed because it lacks a product we can offer. POS growth is shown when it applies and lifts the rank by the revenue the merchant has actually added, but 50 of the 65 candidates have no growth signal at all.

**"Why payroll for every card?"**
The supplied data has far more payroll candidates than trade-finance ones, and the highest-revenue merchants lack payroll. The catalogue only has three cross-sell products. We say so rather than invent offers.

**"What about the loan?"**
A merchant that also qualifies for a working-capital facility shows it as a second line. It is no longer the headline.

**"Who decides the product?"**
The AI engine, where it has run. Otherwise the supplied candidate, labelled as rule-based. Rules decide who is on the list.

## 9. Changelog

- 7 Oct 2026, first pass: selected growth-ready merchants (POS volume up 10% or limit 70% used) that had a lending or cross-sell product. All five cards ended up being working-capital loans.
- 7 Oct 2026, second pass, after the observation that it was showing only POS-driven lending: selection by the product a merchant lacks; ranking by revenue plus growth; the loan as a second line; backend restarted.
