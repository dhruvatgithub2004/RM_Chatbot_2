# Improvement 04: the suggested merchant rate is shown as a range

| | |
|---|---|
| **Status** | Done, 7 October 2026, and live: the `segments` module that blocked the backend now exists (improvement 05) and the backend was restarted. Section 7 is kept for the record. |
| **Why** | A single suggested rate such as 1.67% reads as more precise than the model behind it. |
| **Tests** | 16 new in `backend/tests/test_rate_ranges.py`, 2 existing assertions updated. 153 tests pass (run with the unfinished `segments` module stubbed in memory, section 7). |
| **Decisions** | Width ±0.10 points. Marginal cases keep "change recommended", with the range shown. All five places below. |

## 1. What the RM sees

| Where | Before | After |
|---|---|---|
| Profile, rate card | Current 2.42% → Suggested **1.67%** | Current 2.42% → Suggested **1.55%–1.80%**, with "Illustrative range: the model's estimate ±0.10 points, rounded" |
| Dashboard flag, attention reason | "Rate review: 2.49% → 2.14% recommended" | "Rate review: current 2.49%, model range 2.00%–2.25%" |
| Rationale text (9 exact figures) | "interchange 0.65% + spread 1.02pp = 1.67%… reduction to 1.67%" | "The model puts this merchant's rate at about 1.55%–1.80% (an estimated card cost of about 0.65% plus a spread of roughly 1.0 points). The current rate, 2.42%, is above that range: retention risk, consider a proactive reduction. Main spread drivers: facility leverage (pushes it up), volume volatility (pulls it down)." |
| "Why this?" panel | "2.42% now; 1.67% recommended" | "2.42% now; model range 1.55%–1.80% (illustrative)" |
| Chat and fallback answers | "2.63% → 2.45%" | "2.63% now, model range 2.35%–2.55%" |

A client whose current rate is already inside the range keeps "change recommended", as decided, and its rationale says the case is marginal. That is 11 of the 110 recommended changes. For the other 99 the current rate is outside the range.

## 2. How the range is made

`low = floor((estimate − 0.10) / 0.05) × 0.05` and `high = ceil((estimate + 0.10) / 0.05) × 0.05`. The width is 0.20 to 0.25 points, and the exact estimate is always inside.

**The width is an assumption, not a measured prediction interval.** The model is trained on a synthetic cohort, and the files needed to measure its real error (the cohort, the metrics file and the facilities file) are not in the repository. The ±0.10 is twice the 0.05-point noise the model script puts into its synthetic training data, which is the only uncertainty quantified anywhere in the project. It is one constant in `backend/app/rates.py`, and the UI states the basis.

## 3. What changed

| File | Change |
|---|---|
| `backend/app/rates.py` (new) | The range, the rewritten rationale, the flag wording, masking of an exact rate in model-written text, and a one-off migration |
| `backend/app/readers.py` | The client detail returns `suggested_low_pct`, `suggested_high_pct` and `band_pp`, and no `suggested_pct`; portfolio rows carry the range. The exact value is kept only to order lists by size of change |
| `backend/app/scoring.py` | New ingests write the range into the attention flag |
| `backend/app/copilot.py` | The model sees `suggested_rate_range_pct` and is told to quote the range only; fallback answers show the range; the answer check allows the range figures and not the exact one |
| `backend/app/suggest_llm.py` | The suggestion engine receives the range, and its prompt says to quote the range, never a single figure |
| `backend/app/evidence.py` | The "Why this?" rate fact shows the range |
| `backend/app/guard_rules.py` | The "suggested rate quoted when no change is recommended" rule also catches a quoted model range |
| `backend/app/knowledge.py` | The data dictionary in the knowledge page describes the range |
| `frontend/components/Profile.tsx`, `lib/types.ts` | Shows the range and the note; tolerates an older API with no range (shows "—") |

**What stays exact:** `client.suggested_rate_pct` in the database, the `rate_change_recommended` rule (0.10-point threshold) and the model script. The exact value is needed for the rule and the audit trail. It is not shown to the RM and not sent to the language model.

## 4. Text already stored in the database

Most of the rate wording is stored text, so a one-off command rewrote it in place. `python -m app.rates` copies the database first, then rewrites:

- The attention flag text for the 110 clients that have one (in `client_priority`).
- Rule-based decisions that had copied the old flag wording into their explanation (22 rows).
- One AI-written explanation that quoted an exact rate (MER2150: "reduce the merchant rate to 1.96%" became "…to 1.85%–2.10%").

Run on the live database on 7 October. Two backups exist: `rm_copilot.db.bak-20261007-125739-before-rate-ranges` and `…-125829-…`. A scan of every text column afterwards found no old wording. The command is safe to run again. Numeric columns are not touched.

The rationale is rewritten when read, not stored, so it needs no migration.

## 5. Results

**All 150 clients checked.** The exact modelled rate does not appear in any of these, except where it happens to equal the current rate or a range edge:

| Path | Clients where the exact rate still appears |
|---|---|
| Client detail from the API, including the rationale | 0 |
| The merchant chat context sent to the model | 0 (22 before the extra migration step) |
| The portfolio chat prompt for a rate question | 0 |
| The fallback chat answers | 0 |
| The dashboard attention reason | 0 |
| The "Why this?" panel | 0 |

Every rationale in the data (150 of 150) parsed and was rewritten in the detailed format, so none fell back to the short one.

## 6. Tests

16 new tests: the range rounding (every rate from 1.00 to 3.00), position against the range, the rewritten rationale (rounded figures, no exact figures, idempotent, marginal and no-change variants, fallback), the flag wording, masking, the client API returning a range and no exact rate, marginal recommendations kept with the range, the attention flag for every recommended client, the exact rate never reaching the chat prompt, the fallback answers or the suggestion engine's payload, the evidence panel, the guardrail catching a quoted range for a client with no change, an answer quoting the range passing the figure check while the exact figure is blocked, and the migration (rewrites once, leaves numbers alone).

## 7. What is not finished, and why

- **Restart the backend.** The backend running now was started before this change and still serves the old exact figures. Restarting it with the new code needs the `segments` module, which another piece of work is still adding: `suggest_llm.py` imports it and the file does not exist yet, so the backend cannot start. Until it is restarted, the Profile card shows "—" for the suggested rate and the old rationale. It does not crash.
- **The tests were run with that module stubbed in memory only.** No file was written for it. Run the suite normally once the module exists.
- **I did not see the new rate card rendered.** It compiles and handles a missing range, and the API payload is checked, but the new card has not been looked at with a restarted backend.
- **The range width is an assumption** and is the same for every client (section 2).
- **AI explanations written later** might still round an exact rate to a different form (for example "1.9%"). The suggestion engine is only given the range, so it should not quote the exact figure, but this is not enforced when it writes.
- **Cached chat answers** with exact rates are replaced on their own, because the prompt changed.

## 8. Questions a judge may ask

**"Why a range?"**
The rate comes from a model trained on synthetic data. One number such as 1.67% implies precision the model doesn't have, so we show the model's estimate plus or minus 0.10 points, rounded.

**"Where does 0.10 come from?"**
It is twice the noise in the synthetic training data. We say plainly that it is an assumption and not a measured interval, and that it is one constant that can be changed.

**"Does the range change what is recommended?"**
No. The recommendation rule is unchanged. For 11 of 110 recommendations the current rate already sits inside the range, and those are marked as marginal in the explanation while still saying a change is recommended.

**"Can the AI still quote an exact rate?"**
It is never given one, so it has nothing exact to quote. The answer check also treats the exact figure as not in the data.

## 9. Changelog

- 7 Oct 2026: added `rates.py`; changed the readers, scoring, co-pilot, suggestion engine, evidence panel, guardrail rule, knowledge page and Profile card; migrated stored text in the live database (with backups); wrote 16 tests.
