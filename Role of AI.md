# Role of AI — RM Co-pilot

This document says exactly where AI is used in the RM Co-pilot, what it is allowed to decide, what plain code decides instead, and where the human stays in charge. It is written from the code as it stands. For the safety controls around these components, see [`RESPONSIBLE_AI.md`](RESPONSIBLE_AI.md).

---

## 1. In one paragraph

The product is a deterministic analytics layer (data checks, computed facts, attention scoring, ranking) with an AI layer on top. AI is used in four places: two chat co-pilots, a per-client suggestion engine, and an offline rate model. It decides the suggested action for every client (what to pitch, or whether to protect the relationship), shown on the Dashboard and the Suggestions screen, and it explains and answers questions in the chat. It does not compute the facts it talks about, does not rank the attention list, does not execute anything, and every recommendation is reviewed by the RM. If the AI is switched off or fails, the app still works, with plainer answers.

## 2. Component map

| Component | Uses AI? | What it does | Who decides |
|---|---|---|---|
| Data ingest and validation | No | Loads CSVs, validates rows, quarantines bad ones, writes the quality report | Code |
| Client facts (volume trend, dormancy, limit use, card mix, tenure) | No | Computed from the POS and profile data | Code |
| Attention score, flag and dashboard ranking | No | Rule-based points on dormancy, volume trend, limit pressure, idle balance, risk segment and rate review | Code (policy thresholds set by the team) |
| Profile, filters, card mix, charts | No | Display of computed facts | Code |
| Rate suggestion (current rate, suggested rate, rationale) | **Yes, offline ML** | A Ridge regression predicts the acquirer spread, added to a calculated interchange cost; the results are stored in the merchant file | Model output, shown as supplied |
| **Suggestion engine** (what to pitch) | **Yes, LLM** | Decides one action per client: lending, cross-sell, retention or none, with product, reason, next step and a priority built from three scored parts | LLM proposes, code validates facts and preconditions, RM decides |
| **Dashboard "Suggested action" column** | **Yes, LLM** | Shows the suggestion engine's decision (kind, product, amount, next step, and an AI or Rules tag) beside each client's attention reason | The suggestion engine; code validates; RM decides |
| **Portfolio co-pilot** (chat) | **Yes, LLM** | Answers questions across all clients | LLM words the answer, from supplied data |
| **Merchant co-pilot** (chat) | **Yes, LLM** | Answers questions about one client | LLM words the answer, from that client's data |
| **Guardrails** (NVIDIA NeMo Guardrails: decision boundary, grounding check) | No | Deterministic rails check the question and the answer against the data | Code |
| **Guardrail judges** (NeMo `self check input` and `self check output`) | **Yes, LLM** | A short yes/no policy check of the question and of the answer, on the app's own model | LLM judges; code decides what to do with the verdict |
| Suggestion validation, scope guard, rate limit, audit log | No | Enforce facts and limits around the AI | Code |
| Fallback answers and fallback pitches | No | Used when the LLM is off or fails | Code |

## 3. Where AI is used

### 3.1 Portfolio co-pilot
- **Job:** answer an RM's questions across the whole book, such as who is flagged, who has dormant terminals, who to pitch first, or what a package costs.
- **Input to the model:** the rules prompt, the product knowledge page, one compact row per client (150 rows with name, package, risk segment, rank, score, reason, volume trend, dormant days, balance, rates, supplied lending limit, products held, new-to-bank candidates, the engine's pitch and next action), the top 25 pitches in order, and the last 12 messages of the conversation.
- **What it must do:** answer only from that data and the knowledge page, quote figures as given, and say so when something is not available.
- **Where:** `backend/app/copilot.py`.

### 3.2 Merchant co-pilot
- **Job:** the same, for one client opened from their profile.
- **Input to the model:** the rules prompt, the knowledge page, and that one client's full detail as JSON (profile, rate, products, behaviour, monthly volumes and the last 30 days of daily data, masked card number). No other client's data is included.
- **Extra step:** a question naming another client is refused by code before any model call.
- **Where:** `backend/app/copilot.py`.

### 3.3 Suggestion engine
- **Job:** for each of the 150 clients, decide the single best thing for the RM to do now.
- **Input to the model:** the knowledge page (including the table of allowed products) and one client's data. Three code-computed fields guide the decision: `attention_signal_codes` (which attention signals the client has), `peer_percentile` (the client's rank, 0 to 100, among all clients for turnover, balance, supplied limit and 30-day volume) and `pitchable_products_not_held` (the products the model may choose from for this client).
- **Output from the model:** JSON with `kind` (lending, cross_sell, retention or none), `product`, `amount_aed`, `why` (citing the client's own numbers), `next_action`, and three integer scores: `opportunity` (0 to 40), `signal` (0 to 30) and `fit` (0 to 30). Code adds the three into the 0 to 100 priority, so every priority can be explained by its parts.
- **What AI decides:** which client gets which action, the wording of the reason, and the three scores that order the Suggestions screen.
- **What code enforces:**
  - the product is in the catalogue, is pitchable, and is not already held (names matched tolerantly, so `smartTRADE` counts as holding `Trade Finance (smartTRADE)`);
  - any amount respects the product's published limits and the client's supplied limit;
  - **retention only with a behavioural signal:** dormant terminals or falling volume (`dormant`, `decline_30d` or `decline_6m`). A rate review or an idle balance alone is not accepted, because it would mean giving away margin without a behavioural reason;
  - a rejected answer is retried up to twice more with the reason; a third failure falls back to the rule-based pitch, marked `source: rules`. If that rule-based pitch is a product the client already holds, the client gets no pitch.
- **Where:** `backend/app/suggest_llm.py`, `backend/app/catalogue.py`. Run by `python -m app.ingest` or `python -m app.suggest_llm`. Results are checked with `python -m evals.ai_vs_rules` (section 10).

### 3.4 Guardrail judges (NeMo)
- **Job:** two short policy checks. One screens the RM's question for jailbreaks, requests to ignore the rules, requests for the system prompt, persona switching and abuse. The other screens the answer for claimed actions, guarantees, leaked instructions and claims that the data is real.
- **Input to the model:** only the question, or only the answer, inside a fixed policy prompt (`backend/app/rails/prompts.yml`). The model replies Yes (block) or No. It never sees the client data.
- **Model:** the same one as the chat (`LLM_MODEL`), called through the app's own `llm.complete`, so the judges follow the app if it moves to a local model.
- **What AI decides:** whether a question or answer breaks the policy. **What code decides:** what happens next (refusal, or replacing the answer with the data-only answer), and every hard check, which is deterministic.
- **Where:** `backend/app/guardrails.py`, `backend/app/rails/`. Quality is measured with `python -m evals.rails_judge_eval`.

### 3.5 Rate model (offline ML)
- **Job:** produce the suggested merchant rate and its rationale: `suggested rate = blended Visa interchange + predicted spread`.
- **Interchange part:** a calculation from the Visa UAE interchange table, weighted by each merchant's card-type mix. No ML.
- **Spread part:** a Ridge regression on seven merchant features (turnover, growth, volume volatility, chargeback ratio, premium-card share, facility leverage, risk segment), trained on a synthetic cohort of 800 rows.
- **How the app uses it:** the script (`ml_rate_model.py`) runs outside the app and writes its results into `merchant_profiles_v3.csv`. The app loads and displays them as supplied. The app does not run or retrain the model.
- **Limit:** the training cohort and the spread are synthetic, so the model recovers a rule that was written into the data. Its accuracy says nothing about real pricing, and rates are illustrative.

## 4. Where AI is not used

- Ingest, validation and the data quality report.
- Every fact the AI later quotes: volume change, dormant days, limit use, card mix, balances.
- The attention score, the "flagged" status and the dashboard order. (The Dashboard's "Suggested action" column is the AI's, but the order of the rows is not.)
- The profile screen, filters and charts.
- The rule-based pitch used as a fallback.
- Checking suggestions, refusing cross-client questions, rate limiting and the audit log.
- The hard guardrails: refusing requests to approve, send or change anything, and checking an answer against the data (listed clients must match the question, no suggested rate without a recommended change, no recommending a held or not-pitchable product, no claimed actions). These are plain Python in `backend/app/guard_rules.py`; NeMo only runs them.

This split is deliberate. Numbers the RM may act on come from code that can be tested. AI is used for judgement across many signals and for explaining in plain language.

## 5. Who decides what

| Decision | AI | Code | RM |
|---|---|---|---|
| Which clients need attention | | Scores and flags them | Chooses whom to call |
| What to pitch to a client | Proposes product, reason, next step, priority | Rejects invented, held or out-of-range products | Accepts, changes or ignores it |
| The amount of a loan to offer | Proposes within limits | Caps it to published and supplied limits | Decides the offer |
| The merchant rate | Model suggests it, offline | Shows it as supplied | Decides any rate change |
| How a fact is worded in chat | Writes the answer | Supplies the facts | Judges whether it is right |
| Whether an answer reaches the RM | A judge flags policy problems | Checks the answer against the data and replaces it if it fails | Judges what is shown |
| Whether anything is executed | Never | Never | Always |

No output of the AI triggers an action. There is no automatic pitch, rate change or limit approval.

## 6. Models and settings

| Item | Value |
|---|---|
| Provider | OpenAI or Anthropic, selected with `LLM_PROVIDER` |
| Chat model | `LLM_MODEL`, default `gpt-4o-mini` (OpenAI) or `claude-opus-5-5` (Anthropic) |
| Suggestion model | `SUGGESTION_MODEL` if set, otherwise the chat model |
| Chat limits | up to 1,500 output tokens, 45 s timeout, OpenAI temperature 0.2 |
| Suggestion limits | up to 500 output tokens, 60 s timeout, JSON output required |
| Training | No model is trained or fine-tuned on this data. The LLMs are used as supplied by the provider. The Ridge model is trained on a synthetic cohort only. |
| Guardrails | `GUARDRAILS_ENABLED`, `GUARDRAILS_LLM_CHECKS` (the two judges), `GUARDRAILS_TIMEOUT`. Each judge adds one short model call per question |
| Keys | In `backend/.env`, which is not committed |

## 7. What the RM sees

- Chat replies from the LLM are labelled "AI-generated · may contain errors · verify before acting".
- Replies built without the LLM are labelled "Data-only answer".
- The Suggestions screen says whether rows were decided by the AI engine (and with which model) or by rules.
- The Dashboard's "Suggested action" column shows each client's decision with an "AI" or "Rules" tag (the tooltip names the model), and a note says the action was decided by the AI suggestion engine, checked in code, and that the RM decides.
- The sidebar marks all data as synthetic.

## 8. Without the AI

| AI component unavailable | What happens |
|---|---|
| LLM key missing or the call fails (chat) | Chat returns a data-only answer built from computed facts |
| LLM fails or breaks a factual rule (suggestions) | The client gets the rule-based pitch, marked as such |
| Suggestions never generated | The Suggestions screen uses the rule-based pitch for every client, and the Dashboard's "Suggested action" column shows "—" |
| Rate model not re-run | The rates already in the merchant file stay in use |

The dashboard, profiles, filters and scoring are unaffected in every case.

## 9. Limits of the AI in this prototype

- **Synthetic data.** Nothing here has been tested on real customers. Rates, spreads and scores are illustrative.
- **Model quality.** With `gpt-4o-mini`, the latest suggestion run decided 145 of 150 clients with the LLM and sent 5 to the rule fallback. Section 10 shows its decisions are varied and obey the engine's rules, but there is no ground truth, so it does not show they are right. Known weaknesses: it now pitches 77% of clients (it was 29%), which makes it less selective and leans on the priority to order them; the top of the Suggestions list is dominated by nine clients whose turnover is the same capped AED 3.5M in the data, so it has only two distinct amounts; and retention next steps still mostly say "discuss a rate reduction", which follows the rate model's synthetic signal. In chat it can misread a comparison or list the wrong clients (the guardrails catch the cases they can parse). A stronger model can be set with `SUGGESTION_MODEL` and `LLM_MODEL`.
- **Fixed knowledge.** The knowledge page is rebuilt from the bank documents on ingest. The AI knows nothing newer than that page and the loaded data.
- **No judgement on policy.** Scoring thresholds, pitch exclusions (for example no lending pitch to High-risk clients) and the minimum facility size are policy parameters written in code and awaiting sign-off. The AI does not set them.
- **Provider processing.** With an LLM configured, client data and questions are sent to the provider. The provider's retention and training terms have not been reviewed for this project.

## 10. Evidence: the AI's decisions compared with the rules

`python -m evals.ai_vs_rules` reads the loaded database (no model calls) and compares the stored AI decisions with what the plain rule-based logic would do for the same 150 clients. Figures from the latest run (5 Oct 2026, `gpt-4o-mini`, synthetic data):

| Measure | Rule-based | AI suggestion engine |
|---|---|---|
| Clients given a pitch | 86 (57%) | 115 (77%): 55 lending, 60 cross-sell |
| Decision types available | Pitch only | Lending, cross-sell, retention (32 clients) and none (3 clients) |
| Distinct products pitched | 3 | 5 |
| Products agree where both pitch (67 clients) | n/a | 13% |
| Top 10: distinct products | 1 | 3 |
| Top 10: distinct amounts | 3 | 2 |
| Top 10: clients in common | 5 of 10 | 5 of 10 |
| Retention decisions with a dormant or falling-volume signal | n/a | 32 of 32 |
| Pitches of a product the client already holds | possible (see 11) | 0 |
| Decided by the model, not the fallback | n/a | 145 of 150 |
| Flagged clients (29): decision | n/a | 15 retention, 8 cross-sell, 6 lending |

Priority spread (the model's priority, model-decided clients only):

| | Before 5 Oct | After |
|---|---|---|
| Distinct values across 150 clients | 14 | 39 |
| Share of clients scored exactly 55 or 65 | 77% | 12% |
| Range | 5 to 78 | 17 to 93 |
| Correlation with the rule attention score | 0.21 | 0.33 |
| Correlation with the opportunity tier | 0.38 | 0.45 |
| Correlation with the supplied limit | 0.16 | 0.49 |

**What this shows.** The AI's decisions differ a great deal from the rules: it picks different products, it uses a decision the rules cannot make (retention, and "none"), it matches the flagged clients to protective actions, and it separates clients by priority. Under the rules, the top five pitches were identical in product, amount and reason (`BLOCKERS_AND_PENDING_INPUTS.md`, item 13).

**What it does not show.** "Different" is not "better". There is no ground truth, no RM-labelled set and no outcome data, so there is no measure of whether the AI is right. A small set of clients labelled by an experienced RM, with the AI and the rules both scored against it, is the missing evidence. Two results also cut against the AI: the top 10 has fewer distinct amounts than before (nine clients share the same capped turnover, so they get the same AED 5M cap), and it pitches most clients, so selectivity rests on the priority.

## 11. Change log

### 5 Oct 2026: the AI decision moves onto the Dashboard, retention is gated, priority is calibrated

**Why.** The scoring rubric for Role of AI asks that AI be central and contribute through meaningful decisioning. Measurement showed two weaknesses. First, the landing screen (the Dashboard) was rule-based, so the AI's decision was only visible on a secondary screen. Second, the engine's decisions were weak: 102 of 150 clients got "retention", including 83 clients with no attention flag, almost all driven by one signal (the rate model's "your rate is above the modelled rate, so retention risk"). That signal is synthetic, and acting on all such recommendations would cut margin (see `business impact.md`, section 5). 77% of priority scores were exactly 55 or 65, so the Suggestions order leaned on tie-breaks.

**What changed.**
1. **Dashboard shows the AI decision.** The dashboard API now returns a `decision` for each client (kind, product, amount, next step, priority, source, model) and `decisions_source`. The Dashboard has a new "Suggested action" column with a kind tag, the product and amount, the next step, and an "AI" or "Rules" tag, plus a note saying the AI decided and the RM decides. The row order is still the rule-based attention rank. Files: `backend/app/readers.py`, `frontend/components/Dashboard.tsx`, `frontend/lib/types.ts`.
2. **Retention needs a behavioural signal.** Enforced in code (`RETENTION_CODES` in `suggest_llm.py`), stated in the prompt, and fed back to the model as the reason on a retry. A rate review or idle balance alone no longer qualifies.
3. **Priority is the sum of three scored parts.** The model returns `opportunity` (0 to 40), `signal` (0 to 30) and `fit` (0 to 30), and code adds them. Each client's payload now includes `peer_percentile` (turnover, balance, supplied limit, 30-day volume, ranked across all 150 clients) so the model can anchor "size" instead of guessing, and the prompt asks for the full range.
4. **The model chooses from a code-computed list.** `pitchable_products_not_held` is built in code for each client.
5. **Bug fix: held-product matching.** The data names a product `smartTRADE` where the catalogue says `Trade Finance (smartTRADE)`, so the old exact-name check could never see that a client already held it. One shared, name-tolerant matcher (`catalogue.holds`) is now used by the suggestion validation, the rule fallback, the guardrails and ingest.
6. **Rule fallback never pitches a held product.** The supplied new-to-bank candidate file contains candidates the client already holds, so the fallback returns "no pitch" in that case.
7. **Ingest now reports the data problem.** Its "candidate already held" check compared exact names and reported none. With tolerant matching it finds 10 of 89 candidates already held, so a new warning, `ntb_candidate_already_held`, appears in the quality report. The rows are kept, since the check only warns.
8. **Retry budget.** A rejected answer gets up to two retries (it was one), so a rule violation can be corrected instead of falling back immediately.
9. **Repeatable evaluation.** `backend/evals/ai_vs_rules.py` reproduces the section 10 numbers from the database.
10. **Tests.** 15 new tests (75 to 90 in total) cover the retention rule, the priority parts and clamping, peer percentiles, held-name matching, the rule fallback, the payload fields and the dashboard decision.

**Results.** Dry run on 40 clients first (retention 27 to 11, scores at 55 or 65 from 80% to 10%), then the full run.

| | Before | After |
|---|---|---|
| Decided by the model / rule fallback | 148 / 2 | 145 / 5 |
| Decision mix | 102 retention, 31 cross-sell, 13 lending, 4 none | 32 retention, 60 cross-sell, 55 lending, 3 none |
| Retention for unflagged clients | 83 | 17 (all with a behavioural signal) |
| Clients given a pitch | 44 | 115 |
| Priority scores at exactly 55 or 65 | 77% | 12% |
| Distinct priority values | 14 | 39 |
| Top 10 distinct products / amounts | 4 / 6 | 3 / 2 |

**Trade-offs and side effects.**
- The engine pitches far more clients (115, up from 44). Its priority now orders them better, but it is less selective.
- The top 10 got less varied in amounts, because nine clients share the capped AED 3.5M turnover and receive the same Merchant Loan (POS) cap.
- Fallbacks rose from 2 to 5, because the rules are stricter. The causes are the retention gate and "sized product needs an amount" or a limit below a product's minimum.
- The proposed lending limits total AED 39.7M across 55 lending decisions (15 Merchant Loan (POS), 35 Small Business Loan, 5 working capital facility), up from AED 7.7M. They are proposed limits, not revenue; the largest three account for 56%. `business impact.md` is updated.
- Retention next steps still lean on "discuss rate reduction", since the supplied rate rationale frames it that way.

**Not changed.** The attention ranking and flags are still rules. The chat co-pilots, guardrails and audit log are unchanged. Every fact the AI quotes still comes from code; the loan amounts it proposes are clamped to published and supplied limits.

**Still open.** Labelled evaluation against an RM; a stronger model for the batch (`SUGGESTION_MODEL`); handling the capped turnover in the data; and a decision on whether the engine should pitch fewer clients.

## 12. Summary

| | |
|---|---|
| AI recommends | what to pitch, why, what to do next, in what order, and shows it on the Dashboard and the Suggestions screen |
| AI explains | the data, the products and the rates, in plain language |
| AI predicts | the rate spread, offline and on synthetic data |
| Code computes | every number the AI quotes |
| Code enforces | product, amount and scope rules around the AI |
| The RM decides | everything that is acted on |
