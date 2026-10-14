# Improvement 03: the RM can dig into a suggestion and say whether it was useful

| | |
|---|---|
| **Status** | Done, 6 October 2026 |
| **Related gap** | Gap 5 in `HALLUCINATION_CONTROLS.md` (the pitch "why" text is not fact-checked): now checked and shown to the RM, not yet blocking. Also gap 9 (nothing measures usefulness). |
| **Tests** | 15 new in `backend/tests/test_feedback.py`; full suite 137 passing. The frontend typechecks. |
| **Try it** | Dashboard or Suggestions: **Why this?** opens the evidence, **Useful? Yes / No** saves a rating. Demo link: `/?review=<client id>` opens a client's panel on load. |

## 1. What the RM asked for

"Give the RM the option to dig further and see whether what they are being pitched, recommended or shown is actually useful."

That became two things, which answer two different questions:

| Question | What was built |
|---|---|
| **Is this suggestion sound?** | A **Why this?** panel on every suggestion: the data behind it, the checks re-run on current data, and the AI's own explanation checked against the client's figures |
| **Has it been useful?** | **Useful? Yes / No** buttons, saved with a snapshot of the suggestion, and a running summary by who decided (AI or rules) and by product |

## 2. What the RM sees

**On the Dashboard board, the Dashboard tables and the Suggestions table**, for any client that has a suggestion:

- **Why this?** opens the panel. On the board, the opened card widens to the full row so the panel is readable.
- **Useful? Yes / No.** Clicking the chosen answer again removes the rating. A "No" offers an optional reason: Already offered, Not relevant for this client, Figures look wrong, Bad timing, Other.
- **A summary line** at the top of the Dashboard and Suggestions: "Rated so far: 5 useful, 2 not useful (71% useful). AI-decided: 4 of 5 useful. Rule-based: 1 of 2 useful."

**The panel has six parts:**

| Part | Content | Where it comes from |
|---|---|---|
| What is suggested | Kind, product, amount, AI or Rules, and how it was decided (for AI: its priority out of 100; for rules: the attention score) | The stored decision |
| Its explanation, as written | The suggestion's reason and next step, followed by a check | The AI's text, then a code check |
| The client's data behind it | Up to 10 facts, with the four most relevant to this kind of suggestion in bold | The database. Lending leads with the supplied limit and turnover; cross-sell with the supplied candidates and products held; retention with terminal and volume trends |
| Attention signals | Each signal with its points | The scoring rules |
| Checked just now, on current data | Ticks and crosses | Re-run when the panel opens |
| How useful RMs have found this | Ratings of the same product and the same decider | The saved ratings |

## 3. How it works

**The explanation check.** Every figure in the AI's written reason and next step is looked for in the client's own data, using the figure check from improvement 02. The result is shown as "✓ Figures match" or "⚠ Check", with the figures that were not found. The check does not hide or change the text.

**Checks re-run now, not repeated from when the suggestion was made.**

| Check | Kind |
|---|---|
| The product is in the catalogue and can be pitched | Check |
| The client does not already hold it | Check |
| The amount is within the product's published maximum and the client's supplied limit | Check |
| The amount meets the product's published minimum | Check |
| A retention action is backed by dormant terminals or falling volume | Check |
| For lending: the client is not in the High risk segment | **Caution** |
| For lending: the client's terminals are not dormant | **Caution** |

The two cautions come from the rule-based engine's policy. The AI engine is not bound by them, so a lending pitch to a High-risk or dormant client is flagged for the RM's judgement and is not blocked.

**Ratings.**

- A rating is saved with a snapshot: product, amount, who decided, the model, the priority, the verdict and the reason.
- One row per client and suggestion. Rating again replaces it.
- A rating belongs to the suggestion it was given for. If the engine later suggests a different product for the same client, the new suggestion shows no rating and the old rating is kept.
- Ratings are stored in their own tables. Ingest rebuilds every other table from the CSV files, so a data reload would have erased them otherwise.
- Every rating, change and removal is written to the audit log.

## 4. What changed

| File | Change |
|---|---|
| `backend/app/feedback.py` (new) | Saving, replacing, clearing and summarising ratings; the track record |
| `backend/app/evidence.py` (new) | Builds the panel: facts ordered by relevance, live checks, explanation check |
| `backend/app/models.py`, `db.py` | `ClientFeedback` table on its own base, `FeedbackBase`, so ingest does not drop it |
| `backend/app/readers.py` | Dashboard and Suggestions rows carry the rating of the suggestion currently shown |
| `backend/app/main.py` | Four endpoints (below) |
| `backend/app/guard_rules.py` | AED figures no longer carry a trailing space into messages |
| `frontend/components/Review.tsx` (new) | The controls, the panel and the summary line |
| `frontend/components/Dashboard.tsx`, `Suggestions.tsx`, `App.tsx` | Place them; the `?review=` demo link |
| `frontend/lib/api.ts`, `types.ts`, `app/industry.css` | API calls, types, panel styling |

| Endpoint | Purpose |
|---|---|
| `GET /api/clients/{id}/evidence` | The panel data |
| `POST /api/clients/{id}/feedback` | Rate the current suggestion `useful` or `not_useful`, with an optional reason (clipped to 300 characters) |
| `DELETE /api/clients/{id}/feedback` | Remove the rating |
| `GET /api/feedback/summary` | Counts overall, by AI or rules, by product, and the reasons given for "not useful" |

A client with no suggestion cannot be rated (the API returns 422 and the buttons are not shown).

## 5. Results

**On the live database, all 150 clients.** The evidence was built for every current suggestion (16 AI-decided, 70 rule-based):

| Result | Count |
|---|---|
| Explanations with a figure not found in the client's data | 0 of 86 |
| Failed checks or cautions | 0 |

So today the panel will mostly confirm the suggestions, and none were found to be unsound. The tests below show the checks do flag problems when they exist.

**Live walk-through** on the top opportunity (Dunn Medical Center, lending, AED 460,000, AI priority 94): the panel showed the supplied limit of AED 460,000, turnover of AED 200,000, a balance of AED 113,264 (57% of turnover), 33% of the POS limit used, and six passing checks. The rating was saved, appeared on the dashboard row, counted in the summary and in the panel's track record, then was removed. The test rating was deleted from the live database afterwards. Its entries remain in the append-only audit log.

## 6. Tests

15 tests in `test_feedback.py`:

- Ratings are in tables a data reload does not rebuild
- A rating is saved with a snapshot, and rating again replaces it
- The rating comes back on dashboard and suggestion rows, and can be cleared
- A changed suggestion does not inherit the old rating, and the old rating is kept
- A client with no suggestion cannot be rated
- Bad requests are refused: unknown verdict, unknown client, over-long reason clipped
- Ratings are audited
- The summary counts by who decided, product and reason; an empty summary has no share
- The evidence shows the suggestion, the data, signals and checks, with the key facts first
- Each kind of suggestion leads with the facts that matter for it
- A figure in the AI's explanation that is not in the data is listed (AED 9,999,999, 77% and 99 days in the test), and a grounded explanation is clean
- The checks catch an amount above the supplied limit, a product already held, and a retention call with no signal
- Lending to a High-risk client is flagged as a caution
- The track record counts ratings of the same product and decider

## 7. What is not solved

- **No sign-in.** There is one shared set of ratings, not one per RM. The summary cannot say who rated.
- **Not tested by clicking.** The pages were typechecked and checked in a screenshot of the opened panel. The buttons were exercised through the API, not clicked in a browser.
- **A rating says "useful", not "won".** It does not record whether the RM pitched the product or the client accepted. That would be the stronger measure of usefulness.
- **The ratings do not yet change what is suggested.** They are shown and summarised only. Feeding them back into the suggestion engine is a possible next step.
- **The AI priority's three parts are not stored,** so the panel shows the total out of 100 and says what it is made of, not the split.
- **The explanation check is lenient for the single client:** it confirms a figure appears somewhere in that client's data, not that it is attached to the right field.
- **The rule-based fallback text is not rephrased:** it is shown as written.
- **The summary has no time dimension or trend.**

## 8. Questions a judge may ask

**"How does an RM know whether to trust a suggestion?"**
They open Why this?. It shows the client's own figures, the signals, the checks re-run on current data, and whether every figure in the AI's explanation is in the data.

**"How do you know suggestions are actually useful?"**
The RM rates them. We keep the rating with a snapshot of what was suggested and show how useful AI-decided and rule-based suggestions have been, and by product. Today there are no ratings, because the feature is new. The summary line says so.

**"Does the AI mark its own homework?"**
No. The facts and checks are computed from the data in code. The only AI text, the explanation, is shown as written and then checked against the data.

**"What if the AI suggests lending to a risky or dormant client?"**
It is not blocked, but the panel shows a caution that the rule-based engine would not pitch it.

**"Does a data reload wipe the ratings?"**
No. They are in separate tables that ingest does not rebuild, and there is a test for that.

## 9. Changelog

- 6 Oct 2026: added the evidence endpoint and panel, ratings with snapshots and a summary, the live checks and the explanation check; moved ratings out of the tables ingest rebuilds; fixed the trailing space in AED figure messages.
