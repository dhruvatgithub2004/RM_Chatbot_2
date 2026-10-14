# Improvement tracker

One page to see what has been fixed, what is open, and where the evidence is. Each improvement has its own file with the problem, the change, before-and-after numbers, tests, limits and likely judge questions.

Last updated: 7 October 2026. Backend tests: 194 passing (96 before improvements 01 to 08).

## Status

| # | Improvement | Gap in `HALLUCINATION_CONTROLS.md` | Status | Headline result | Details |
|---|---|---|---|---|---|
| 01 | The prompt fits the model's window; answers are faster | 1 | **Done** | Prompt read by the model: a cut 4,098 of about 20,000 tokens became a full 1,000 to 3,300. Median uncached chat 5.2 s. | [01_context_fit_and_latency.md](01_context_fit_and_latency.md) |
| 02 | Every figure in a model answer must be in the data | 2 | **Done** | 8 of 9 wrong-figure tests blocked (was 0 of 9); 0 false blocks in 1,059 correct answers; 2 real errors caught in 49 real answers | [02_number_grounding.md](02_number_grounding.md) |
| 07 | Dashboard "Top performers", step 3: the largest merchants by card volume, with shares of portfolio and city volume | none (new feature) | **Done** | Top 10% by 30-day card volume (15 merchants hold 63.6% of volume); top 5 shown; ranked by volume because turnover has ties; 11 new tests | [07_top_performers.md](07_top_performers.md) |
| 08 | Dashboard "Dormant reactivation", step 4: merchants with inactive terminals now, ranked by earlier monthly volume | none (new feature) | **Done** | Brief's 30 to 90 days would be empty (longest run 24 days), so "inactive now" is used; 10 merchants, top 5 shown; 6 new tests | [08_dormant_reactivation.md](08_dormant_reactivation.md) |
| 06 | Dashboard "Cross-sell targets", step 2: merchants that lack a product we can offer; the loan as a second line | none (new feature) | **Done** | 65 candidates (15 also growing), 53 also qualify for a loan; top 5 shown; AI decides the offer where it has run; 12 tests | [06_cross_sell_targets.md](06_cross_sell_targets.md) |
| 05 | Dashboard "Act now", step 1: the five highest-value churn risks | none (new feature); uses the figure and rate-range work | **Done** | Rules pick and rank from the data (22 at risk, 15 high-value); AI writes the step where it decided; 12 new tests | [05_act_now_churn_risk.md](05_act_now_churn_risk.md) |
| 04 | The suggested merchant rate is shown as a range, not one exact figure | n/a (accuracy of figures shown) | **Done; live since the backend restart** | Range = model estimate ±0.10 points, rounded to 0.05; exact rate not shown or sent to the model for any of 150 clients; 16 new tests | [04_rate_ranges.md](04_rate_ranges.md) |
| 03 | The RM can dig into a suggestion ("Why this?") and rate it useful or not | 5 (shown, not blocking), 9 | **Done** | Evidence panel with live checks and an explanation check; ratings saved with a snapshot and summarised by AI vs rules; 15 new tests | [03_review_and_feedback.md](03_review_and_feedback.md) |

## The other gaps

| Gap | What | Status | Notes |
|---|---|---|---|
| 3 | Invented product names in chat are not caught | Open | |
| 4 | Pattern rules skip negated sentences and cover few topics | Open | |
| 5 | The pitch "why" and "next step" text is not fact-checked | Partly | Improvement 03 checks it with the figure check and shows the result in the "Why this?" panel. It is not yet blocked or retried at generation time |
| 6 | The model-based checks use the same small model | Open | `evals/rails_judge_eval.py` exists; no result recorded |
| 7 | The semantic cache can return an answer to a similar but different question | Open | |
| 8 | The fallback answer matches word fragments and can answer the wrong question | Open | "generate" matches "rate" |
| 9 | Nothing measures correctness over time | Partly | `evals/figure_replay.py` replays real answers through the figure check, and RMs can now rate suggestions (improvement 03); there is still no question set with known answers |
| 10 | The facts the model is given can be stale or wrong | Open | |
| New | The deterministic fallback can recommend a product the client already holds when there is no stored decision | Open | Found in improvement 02; see its section 7 |
| New | Long replies reach the 350-token cap and are cut off without a notice | Open | Found in improvement 01; see its section 6 |

## What the two improvements add up to

| Measure | Before | After |
|---|---|---|
| Tokens in the portfolio prompt | about 20,000, silently cut to the last 4,098 | 400 to 3,800 (1,000 to 1,500 for typical questions), nothing cut |
| What the model lost when the prompt was cut | Its rules and the knowledge page | Nothing |
| Time the model spends reading the prompt | about 2 s | 0.1 to 0.4 s (1.3 s with the fee table) |
| Merchant chat, first turn | 7,200 to 7,800 estimated tokens, over the limit on a follow-up | 3,900 to 4,500, fits on a follow-up for all 150 clients |
| Typical uncached chat | 21.7 s average (older runs) | 5.2 s median (2.0 to 9.7 s) |
| Wrong percentage, day count, small AED amount or client count in an answer | Reached the RM | Blocked; the RM gets the data-only answer |
| Wrong AED amount of 1,000 or more | Logged only | Blocked |
| Blocked answers in the audit log | The violation only | The violation, and the blocked text |
| Token counts per chat | Not recorded | Recorded in the audit log |
| Automated tests | 96 | 188 |
| Can an RM see why a suggestion was made, and say whether it helped? | No | Yes: evidence panel and Yes / No rating, with a running summary |

## How to re-check the numbers

Run from `backend/`.

| Command | Needs the model? | Shows |
|---|---|---|
| `python -m pytest tests -q` | No | All 188 tests |
| `python -m evals.prompt_sizes` | No | Prompt size per question against the limit, merchant sizes for all 150 clients |
| `python -m evals.latency_probe` | Yes | Tokens read, seconds to read, tokens written, seconds to write, wall time |
| `python -m evals.figure_replay` | No | Which real audited answers the figure check would now block, with the figures |

## When you add the next improvement

1. Measure the problem first and put the evidence in the file.
2. Write the file as `NN_short_name.md` with the same sections: problem, what changed, how it works, results (before and after), tests, what is not solved, judge questions, changelog.
3. Add a row to the status table above and update the gap table.
4. Keep every number traceable to a command in the last section, or say it came from a one-off run.
