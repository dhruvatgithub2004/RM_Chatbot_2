# Improvement 02: every figure in a model answer must be in the data

| | |
|---|---|
| **Status** | Done, 6 October 2026 |
| **Closes** | Gap 2 in `HALLUCINATION_CONTROLS.md` (only large AED amounts were checked, and only softly) |
| **Tests** | 12 new in `backend/tests/test_figure_grounding.py`, 4 existing tests updated; full suite 122 passing |
| **Re-run the numbers** | `python -m evals.figure_replay` from `backend/` (offline) |

## 1. The problem

The output check for numbers covered only AED amounts of 1,000 or more, and a miss was only written to the audit log, so the wrong answer still reached the RM. Percentages, day counts, small amounts and client counts were not checked at all.

**Tested before the change** (a wrong answer given to the old rules, with the real portfolio data as context):

| Wrong answer | Old result |
|---|---|
| "Volume up 85% vs prior 30 days" | Passed |
| "Dormant for 99 days" | Passed |
| "A monthly fee of AED 450" | Passed |
| "A balance of AED 7,777,777" | Logged, not blocked |
| "99 of 150 clients are flagged" | Passed |

These are the figures RMs read most: "down 43%", "dormant 14 days", "110 of 150 clients".

## 2. What changed

| File | Change |
|---|---|
| `backend/app/guard_rules.py` | New `check_figures`, `numbers_in`, typed percentage and day pools; `ungrounded_number` is now a hard rule; each client carries the figures the model was shown for it |
| `backend/app/copilot.py` | Builds those per-client figures from the portfolio rows, and checks portfolio answers against the totals in the prompt |
| `backend/app/main.py`, `copilot.py` | The text of a blocked answer is written to the audit log (never shown to the RM) |
| `backend/tests/test_guardrails.py` | Four tests updated: two that expected a soft finding now expect a block, and two had their toy context extended with the figures their answers quote |

## 3. What is checked

An answer is blocked when it contains any of these and the figure is not in the data the model was given:

| Kind of figure | Examples it catches | Counts as in the data when |
|---|---|---|
| AED amount of 100 or more | "AED 7,777,777", "AED 450", "AED 1.225M" | It matches a figure the model was shown, to the precision the answer states |
| Percentage | "85%", "1.50%", "0.813%" | It matches a percentage the model was shown (fractions are also read as percentages: 0.43 as 43%) |
| Day count | "dormant for 99 days" | It matches a day count the model was shown, or is a comparison window (30 or 60 days) |
| Month count | "over 9 months" | It is in the data, or is 6 or 12 |
| Client count | "99 of 150 clients", "12 clients" | It is in the header or the listing line, equals the number of clients the answer names, or the RM wrote it |

**Where each figure is looked up.** The model's answer is checked against:

- The totals and counts in the prompt header, and the line that counts what was listed
- The knowledge page text, when it was sent
- The figures of every client the answer names (their balance, volume change, rate, limit, dormant days, and the numbers inside their reason and next-action text)
- Any number the RM wrote in the question, so "Can a client take AED 50,000?" can be answered with "AED 50,000"

**Rules that make it precise:**

- **Rounding is allowed only to the precision the answer states.** "AED 27k" can stand for 27,153 and "AED 53.5M" for 53,451,120. "AED 54.5M" cannot. Before, any "k" or "M" figure had a flat 6% tolerance.
- **Types are kept apart in the portfolio chat.** A percentage can only match a percentage and a day count only a day count, so "10 days" does not pass because 10 clients are dormant.
- **Scaled numbers are understood** in the reference, so "up to AED 5 million" in the knowledge page grounds "AED 5,000,000".
- **Digits inside identifiers are ignored**, so `MER2001` does not count as the number 2001.
- **Shares are in the header**, for example `flagged_for_attention=29 (19%)`, so "about 19% are flagged" is grounded. Totals are in the header too, so the model does not have to add anything up.

**What happens on a block:** the model's answer is discarded and the RM gets the data-only answer, with the notice that the AI answer failed an accuracy check. The blocked text is written to the audit log with the figures that failed.

## 4. Results

### On wrong answers (battery of 9, real data)

| Wrong answer | Before | After |
|---|---|---|
| "Volume up 85%" | Passed | **Blocked** |
| "Dormant for 99 days" | Passed | **Blocked** |
| "A fee of AED 450" | Passed | **Blocked** |
| "A balance of AED 7,777,777" | Logged only | **Blocked** |
| "99 of 150 clients are flagged" | Passed | **Blocked** |
| "12 clients have dormant terminals" (10 do) | Passed | **Blocked** |
| "Current rate is 1.50%" | Passed | **Blocked** |
| "Dormant for 10 days" (10 is a client count elsewhere) | Passed | **Blocked** |
| "Volume down 7%" for a client whose figure differs, where 7% also appears as the dormant share in the header | Passed | **Passed** (known limit, section 6) |

8 of 9 are now blocked.

### On correct answers: no false blocks

| Test | Result |
|---|---|
| 9 hand-checked correct answers: exact figures, rounded to thousands, totals in millions, shares, the RM's own number | All pass |
| **1,059 deterministic answers** (9 portfolio questions, then 7 questions for each of the 150 clients), which are correct by construction. Run once by hand on the live database | **0 wrongly blocked** |
| The same check inside the test suite: 9 portfolio questions and 7 questions for every 4th client (275 answers) | 0 wrongly blocked |
| Every correct answer a rounding could produce, "AED 53.5M" and "AED 53 million" for a 53.45M total | Pass |

### On real model answers

Replaying the model answers in the audit log through the new rule (49 answers):

| Answer | What the rule objected to | Verdict |
|---|---|---|
| Cross-sell candidates (old oversized prompt) | "AED 1.225M" | Real error. No client has that limit; the data says 12,250,000, so the model was ten times out |
| Lending opportunities (old oversized prompt) | "AED 1,400,00" | Real error: a malformed amount |

The other 47 pass, including all 28 answers produced after improvement 01.

### Live catch

In a 12-question run through the real API, one answer was blocked: the model listed volume changes as "-0.813%", "-0.648%" and so on, reading the stored fractions as percentages. The true figures are 81.3% and 64.8% declines, so the RM would have been shown numbers 100 times too small. They got the data-only answer instead.

## 5. Tests

12 new tests in `test_figure_grounding.py`:

- Wrong percentages, day counts, AED amounts (including small and malformed ones) and client counts are blocked
- A blocked figure is a hard violation named `ungrounded_number`
- Correct figures pass: exact, rounded to thousands, shares, portfolio totals
- Rounding is allowed only to the stated precision (53.5M passes, 54.5M and 53.8M block)
- The comparison windows and the RM's own numbers pass; the same number not in the question blocks
- A percentage cannot pass on a day count or client count
- In the single-client chat, figures are checked against that client's data and the knowledge page
- Scaled numbers are read correctly; identifier digits are ignored
- **275 deterministic answers are never blocked** (the suite's share of the 1,059-answer hand sweep)

Changed: two guardrail tests that expected a soft finding now expect a block, two others had figures added to their toy context, and one also checks that the blocked text is audited and not returned.

## 6. What is not solved

- **A figure that coincides with a different portfolio-wide figure can pass.** The "7%" case: a wrong 7% for one client passes because the header has a legitimate 7% (the dormant share). Closing it needs the check to work sentence by sentence, deciding which client or total each figure belongs to. Not done.
- **In the single-client chat the check is looser.** The pool is the client's whole record, which has many numbers, so a wrong figure that happens to equal some other number in that record can pass. Percentages and day counts are not typed there.
- **A correct answer that needs a figure we did not supply can be blocked.** For example a sum or ratio the header does not carry. The RM then gets the data-only answer, which is correct but plainer. In 1,059 deterministic answers and 49 real model answers this did not happen on a correct answer, but the sample is small.
- **Not checked:** amounts under AED 100, numbers written as words ("three clients"), dates, and counts that are not of "clients", "merchants" or "customers".
- **Clients in the same answer share a pool.** A figure that belongs to client A but is written beside client B can pass if it is in A's data.
- **Product names in chat** are still not checked against the catalogue (Gap 3).

## 7. A side finding

While running the 1,059-answer sweep on the test database, the deterministic answer for client MER2089 recommended Trade Finance (smartTRADE), which that client already holds. The supplied cross-sell file lists products clients hold (the ingest report already warns `ntb_candidate_already_held`). The model-answer rules would block this, but the deterministic fallback is not checked by them. It does not affect the live database, where the stored decisions already handle held products. It is recorded as a follow-up.

## 8. Questions a judge may ask

**"Isn't blocking answers too aggressive?"**
We measured it. Of 1,059 answers that are correct by construction (run by hand; 275 of them are in the test suite), none was blocked. Of 49 real model answers, 2 were blocked and both contained real errors, one of them ten times out. When an answer is blocked the RM still gets a correct data-only answer.

**"What does the RM see when an answer is blocked?"**
The data-only answer, labelled as such, with a notice that the AI answer failed an accuracy check. The blocked text and the figures that failed go to the audit log for review.

**"Can the model do arithmetic and be blocked for it?"**
The header carries the totals, counts and shares, so it does not need to. A figure it works out itself that is not in the data is blocked.

**"Is the wrong-figure check itself tested?"**
Yes: nine wrong answers (eight blocked, one known limit) and nine correct ones in a hand-checked battery, and the test suite carries the figure tests plus a 275-answer false-block sweep.

**"What about wrong figures in the pitch 'why' text on the dashboard?"**
Not covered yet. This check runs on chat answers. The pitch text is Gap 5.

## 9. Changelog

- 6 Oct 2026: replaced the soft AED check with typed, hard figure checks; blocked answers are audited with their text; tolerance tightened to the stated precision; sweep, replay and live runs recorded here.
