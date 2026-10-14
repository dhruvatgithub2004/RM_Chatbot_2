# RM Co-pilot: Project Summary

This summary was written from the source code, the loaded database and the data files as they stand on 6 October 2026. All data in the project is synthetic demonstration data. It is not real customer, credit bureau or compliance data.

## Contents

1. [Overview](#1-overview)
2. [What the RM sees](#2-what-the-rm-sees)
3. [Methodology](#3-methodology)
4. [Models used and their functions](#4-models-used-and-their-functions)
5. [Role of AI in this project](#5-role-of-ai-in-this-project)
6. [Controls and guardrails](#6-controls-and-guardrails)
7. [Project structure](#7-project-structure)
8. [Data](#8-data)
9. [Testing and evaluation](#9-testing-and-evaluation)
10. [Known limits](#10-known-limits)

## 1. Overview

RM Co-pilot is a web application for a bank Relationship Manager (RM) who looks after a portfolio of SME merchant clients, meaning businesses that accept card payments through the bank's POS terminals. The demo is set in the UAE and uses a fictional bank brand, "Northbridge". The product and fee knowledge comes from public Emirates NBD business banking pages.

**The problem.** An RM's information about a merchant sits in separate places: the client profile, daily POS acquiring data, products held, pricing and lending sizing. Working out each week which clients are slipping away, which are outgrowing their limits and which are ready for a lending or cross-sell conversation takes manual effort, so RMs tend to react late.

**What the product does.** It brings those sources together and answers three questions for the RM:

- Who needs my attention this week, and why?
- What should I offer each client, how much, and what is the reason?
- What does the data say about this client or this portfolio, in plain language?

**The design principle.** The system recommends and explains. The RM decides and acts. The co-pilot cannot approve, send, change or book anything, and it refuses when asked to.

**Technology.**

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript |
| Backend API | FastAPI, Pydantic, SQLAlchemy 2 |
| Database | SQLite (`backend/rm_copilot.db`) |
| Data processing | pandas, NumPy |
| Language model | Qwen3 8B, run locally through Ollama (default); Anthropic Claude as an alternative provider |
| Guardrails | NVIDIA NeMo Guardrails, plus deterministic Python rules |
| Response cache | ChromaDB (exact and semantic) |
| Pricing model | scikit-learn Ridge regression |
| Tests | pytest (188 test cases) |

## 2. What the RM sees

The app has four screens.

**Dashboard.** The dashboard shows lists of five merchants, in this order: **Cross-sell targets** first, then **Act now** (the high-value churn risks), then **Top performers**. They were built in a different order (churn risks first), and the display order is set in `Dashboard.tsx`. The **Act now** list is the five highest-value churn risks, shown as five cards: the value tier, why it is flagged (inactive terminals, volume down against the prior 30 days, volume below its own earlier average), and the recommended step tagged AI or Rules. Rules pick and rank the merchants from the data; the AI engine writes the step where it has decided one. There are no filters on this section. **Cross-sell targets** (step 2, shown first): five merchants that are not churn risks and do not yet hold a product the bank can offer (a supplied new-to-bank candidate, or a cross-sell the AI engine chose), ranked by estimated monthly revenue plus any growth in it. The card leads with the product gap, shows the offer tagged AI or Rules, and shows a working-capital facility the merchant also qualifies for as a second line. POS growth explains and lifts a merchant but does not decide who is listed. Then **Top performers** (step 3): the five largest merchants by card volume over the last 30 days, from the top 10% that hold 63.6% of the portfolio's card volume, each with its share of the portfolio's and its city's volume and its trend. Card volume is used because the supplied turnover has ties. A top performer that is also a churn risk gets the retention step. The page says there is no record of the last contact, so it cannot show who is overdue for a check-in. See `07_top_performers.md`. The other merchant types are added one step at a time. See `md_files/improvements/05_act_now_churn_risk.md` and `06_cross_sell_targets.md`.

The earlier Opportunities / All view (nine opportunity boxes, tables, tabs and search) is hidden for now behind one switch, `SHOW_ALL_MERCHANTS` in `Dashboard.tsx`, and is described below for reference. Set it to `true` to show it again. It had two tabs, **Opportunities** by default and **All**, both searchable by client or industry.

- **Opportunities** lists the clients that have a suggested action (lending, cross-sell or retention), strongest first. Strength is the priority the pitch decision engine gave the decision. Ties go to the better opportunity tier, then the larger supplied working-capital limit. Clients whose suggested action is "none" are not shown. The top 9 appear as a board of boxes; the rest follow in a table headed "More opportunities". Each box shows the rank, client, industry and city, the flag, the suggested action with its "AI" or "Rules" tag and next step, and a "View profile" link. Clicking anywhere on a box opens the client's profile.
- **All** lists every client by attention rank, with the same flag and suggested-action columns, including clients with no suggested action (tagged "No action").
- In both views the flag text is enlarged and its figures (days, percentages, AED amounts) are bold and coloured. The "30 days" in "vs prior 30 days" is left plain because it is the comparison window, not a finding. Client names in the tables are also links to the profile.
- The Opportunities tab covers every client with a suggested action, not only flagged ones. The header count ("N clients flagged for attention this week") still counts flagged clients only.

**Profile and analytics.** One page per merchant:

- Card and POS: masked card number, card type, monthly and daily POS limits, last-30-day volume and transaction count
- Profile and behaviour: balance, risk segment, package, products held
- Rate suggestion: current rate, the suggested rate as a range (the model's estimate ±0.10 points, rounded to 0.05, labelled illustrative; or "No change"), and a written rationale
- A 6-month volume chart and a pie chart of the card mix, as each card type's share of the last 30 days' card volume (percentages in the legend; hover a slice for the AED amount). Each card type keeps one fixed colour
- A merchant list that can be searched and filtered by balance range, segment, card type and product held

**Suggestions.** The top 10 merchants to pitch, each with a recommended product, an amount where the product is sized, and a reason that cites the client's own figures. The list can be filtered by product.

**Reviewing a suggestion (Dashboard and Suggestions).** Every suggestion has **Why this?** and **Useful? Yes / No**. *Why this?* opens the client's own data behind the suggestion, the attention signals, the validations re-run on current data (product pitchable, not already held, amount within limits, plus cautions for lending to a High-risk or dormant client), and a check that every figure in the AI's written explanation is in the client's data. *Useful?* saves the RM's rating with a snapshot of the suggestion and an optional reason; a summary line shows how useful AI-decided and rule-based suggestions have been. See `md_files/improvements/03_review_and_feedback.md`.

**Co-pilot chat.** Two modes:

- The portfolio co-pilot answers questions across all clients, for example "Which clients are flagged?" or "Lending opportunities?"
- The merchant co-pilot is scoped to one client and declines to discuss any other

Each reply is labelled as AI-generated, data-only, or blocked by a guardrail.

## 3. Methodology

The system works in five stages. The first three run offline when data is loaded. The last two run when the RM uses the app.

```
CSV files
   │
   ▼
1. Ingest and validate ──► quarantine bad rows, write data-quality report
   │
   ▼
2. Compute client facts (deterministic, from daily POS data)
   │
   ▼
3. Score and decide
   ├─ Attention score and action (rules)
   ├─ Rule-based pitch (rules)
   └─ Pitch decision (language model, checked in code, rule fallback)
   │
   ▼
4. Serve: dashboard, profile, suggestions (read from the database)
   │
   ▼
5. Chat: question ─► input rails ─► cache ─► model ─► output rails ─► RM
                                                          │
                                         failed check ────┴─► data-only answer
```

### Stage 1: Ingest and validate (`backend/app/ingest.py`)

- Reads four CSV files: merchant profiles, daily POS acquiring, products held, and new-to-bank cross-sell candidates.
- Applies hard validation. Rows that fail are quarantined and excluded: malformed IDs, duplicates, out-of-range scores and rates, invalid dates, dormant days that show activity, POS rows for unknown merchants.
- Applies soft checks that raise warnings without excluding data, for example POS volume above the daily limit, or a cross-sell candidate the client already holds.
- Records the file hashes, row counts and issues for each run, and writes `data_quality_report.json`.
- The load is idempotent: tables are rebuilt from the CSVs on every run.

### Stage 2: Compute client facts (`ingest.py`, `compute_facts`)

All dates are relative to the latest date in the data (the as-of date), not today's date. For each client the pipeline computes:

- Volume in the last 30 days, the prior 30 days, and the change between them
- 6-month trend across complete calendar months
- Whether terminals are dormant now, and the length of the dormant streak
- Share of the monthly POS limit used, and the peak day as a share of the daily limit
- Balance as a share of average monthly turnover
- Average ticket size, chargeback ratio, card mix, dominant card type and premium-card share
- Tenure in months

### Stage 3: Score and decide

**Attention score (`backend/app/scoring.py`).** A rule-based score from 0 to 100. Each signal adds points:

| Signal | Trigger | Points |
|---|---|---|
| Dormant terminals | Terminals dormant now | 40 to 50, rising with the streak length |
| 30-day decline | Volume down 10% or more vs prior 30 days | Up to 40 |
| 6-month decline | Volume down 15% or more over 6 months | 10 |
| Limit pressure | 70% or more of the monthly POS limit used | 15 to 25 |
| Idle balance | Balance at 50% or more of monthly turnover | 10 to 20 |
| 30-day growth | Volume up 10% or more | 10 |
| Rate review | A rate change is recommended | 10 |
| Risk segment | High or Medium | 15 or 5 |

A client scoring 30 or more is flagged. The strongest signal becomes the one-line reason on the dashboard, and the strongest actionable signal becomes the RM action: terminal reactivation, a relationship review call, or a POS limit increase.

**Rule-based pitch (`scoring.py`).** A lending pitch (working capital facility) applies when the supplied working-capital limit is AED 250,000 or more, terminals are not dormant, and the client is not in the High risk segment. Otherwise the first supplied cross-sell candidate is used. This is the fallback when the model's decision is unavailable.

**AI pitch decision (`backend/app/suggest_llm.py`).** Described in section 5.

### Stage 4: Serve (`backend/app/readers.py`, `main.py`)

Two reader classes shape the stored data for the API. `PortfolioReader` serves the dashboard, the directory, the suggestions list and the portfolio rows. For the dashboard's Opportunities view it keeps the clients whose stored decision is not "none" and sorts them by decision priority (`_opportunities` in `readers.py`). If no decisions have been generated yet, it falls back to clients with a rule-based pitch, ranked by attention score. `ClientReader` serves one client's detail. The merchant co-pilot builds its context from a single `ClientReader`, so data about other clients is never in the prompt.

### Stage 5: Chat (`backend/app/copilot.py`)

Each question goes through these steps:

1. **Scope check** (merchant chat only). If the question names another client, the co-pilot refuses before any model call.
2. **Input rails.** The question is checked for action requests and for prompt injection or abuse.
3. **Context building, sized to the model's window.** The prompt is built to fit the 8,192-token window, because the model server silently cuts an over-long prompt at its start and the model then loses its rules. The portfolio chat sends a header of totals and counts over all 150 clients plus only the clients the question is about (up to 8; pitch questions 5), with only the fields it needs and a line saying how many were not listed. Filter questions list every match by name. The merchant chat sends that client's record as compact JSON. The product knowledge page is sent in parts, and only the parts the question needs. Older chat turns are dropped first when the conversation is long. A prompt that still cannot fit is never sent; the RM gets the data-only answer. See `md_files/improvements/01_context_fit_and_latency.md`.
4. **Cache lookup.** An exact match is tried first, then a semantic match for single-turn questions.
5. **Model call.** The model answers under a system prompt of hard rules: answer only from the data and knowledge page, never invent figures, quote rates and pitches as given.
6. **Output rails.** The answer is checked against the data the model was given, including every figure in it (see the figure check below).
7. **Result.** A passing answer is returned and cached. A failing answer, or a model error, is replaced by a deterministic data-only answer.
8. **Audit.** One log line is written for the exchange.

## 4. Models used and their functions

| Model | Type | Where it runs | Function |
|---|---|---|---|
| Qwen3 8B (`qwen3:8b-rm`, 8K context, temperature 0.2) | Open-weight language model | Locally, through Ollama on port 11435 | Chat answers, per-client pitch decisions, and the two policy-check rails |
| Claude (Anthropic) | Hosted language model | Anthropic API, selected by configuration | Alternative provider for the same three jobs |
| Ridge regression (alpha 1.0) | Linear ML model | Offline script `ml_rate_model.py` | Predicts the acquirer spread that makes up the suggested merchant rate |
| Blended interchange calculation | Deterministic formula | Offline script `ml_rate_model.py` | Computes each merchant's interchange cost from its card mix |
| Attention score | Rule-based scoring | `scoring.py`, at ingest | Ranks clients and produces the reason and RM action |
| Rule-based pitch | Rules | `scoring.py`, at ingest | Fallback pitch when the model's decision is unavailable |
| Chroma default embedding model | Sentence embedding model | Locally, inside ChromaDB | Finds similar past questions for the semantic cache |

### The language model

One model does three jobs, all through a single function (`llm.complete` in `backend/app/llm.py`). Changing the provider or model in configuration changes all three together.

- **Chat.** Answers RM questions from the supplied data and knowledge page.
- **Pitch decision.** Returns one structured JSON decision per client.
- **Policy checks.** Answers Yes or No on whether a question or an answer breaks policy.

The local model is the default so that client data stays on the bank's own machine. A separate, stronger model can be set for the pitch-decision batch with `SUGGESTION_MODEL`.

### The rate suggestion model (`ml_rate_model.py`)

The suggested merchant rate is built from two parts:

```
suggested rate = blended interchange cost + predicted spread
```

- **Blended interchange** is a calculation with no machine learning. It applies the published Visa UAE interchange table (effective 19 December 2024) to the merchant's card mix, with merchant-category overrides and debit caps, weighted by volume.
- **Predicted spread** comes from a Ridge regression on seven features: log turnover, growth, volume volatility, chargeback ratio, premium-card share, facility leverage and risk segment. The spread is clipped to between 0.40 and 1.60 percentage points.
- **Recommendation.** If the current rate is at least 0.10 points above the modelled rate, the recommendation is to reduce. If it is at least 0.10 points below, the recommendation is to increase. Otherwise, hold.
- **Explainability.** The model is linear on purpose, so each rate breaks down exactly into interchange, a base spread and one contribution per feature. This breakdown is written to `merchant_rate_waterfall_v1.csv`, and a templated rationale naming the two largest drivers is stored with each client.
- **Limit.** The spread model is trained on a synthetic cohort of 800 merchants, because real negotiated rates are not public. Its holdout fit (R² of about 0.88) reflects that it recovers the rule used to generate the cohort. It is not evidence of real-world accuracy, and the rates are labelled illustrative. The script documents how to retrain on a bank's real rate history.

The script runs offline and writes its results into the merchant profile CSV. The backend reads those columns and does not run the model itself.

**Shown as a range.** Because the spread model is trained on synthetic data, the suggested rate is never shown as one figure. The app, the chat and the suggestion engine use a range: the model's estimate plus or minus 0.10 points, rounded outward to 0.05 (for example 1.55%–1.80%). The width is an assumption, twice the 0.05-point noise in the synthetic training data, and not a measured interval. The exact value stays in the database for the recommendation rule and the audit trail. See `md_files/improvements/04_rate_ranges.md`.

### The opportunity tier

Each client carries a supplied opportunity tier (1 Prime to 4 Low priority) and label. `merchant_opportunity_reasons_v1.csv` holds the z-scores and top three reasons behind each tier. The backend uses the tier and label from the profile file; it does not load the reasons file.

## 5. Role of AI in this project

AI is used in three places. In each one, code checks what the model produces, and a non-AI path exists if the model fails.

### Where AI is used

**1. Deciding the pitch for each client.**

- The model receives one client's data, the client's rank among peers on turnover, balance, supplied limit and volume, and the product knowledge page.
- It returns one decision: the kind (lending, cross-sell, retention or none), the product, the amount, a reason, a next step, and a priority.
- The reason must cite at least two of the client's own numbers.
- The priority is the sum of three parts the model gives separately: opportunity (0 to 40), signal (0 to 30) and fit (0 to 30). This makes the ranking explainable.
- Code validates the facts (see section 6). A rejected answer is sent back with the rejection reason. After three rejections the client falls back to the rule-based pitch and is marked "Rules".

**2. Answering questions in chat.**

- The model turns structured data into a readable answer and handles questions the fixed rules were not written for.
- It answers only from the data and knowledge page placed in its prompt.

**3. Screening questions and answers.**

- The same model acts as a policy checker on the input and the output, as an extra layer on top of the deterministic rules.

### Where AI is not used

| Function | How it is done |
|---|---|
| Data validation and client facts | Deterministic code |
| Attention score, flag and reason | Rules with fixed thresholds |
| RM action (reactivate, review call, limit increase) | Rules |
| Interchange cost | Formula from a published table |
| Rate rationale text | Template built from computed numbers |
| Product catalogue and published limits | Fixed table in code |
| Hard guardrail checks | Regular expressions and data lookups |
| Fallback chat answers | Deterministic responder quoting computed facts |

### Division of responsibility

| Party | Responsibility |
|---|---|
| The language model | Proposes a pitch and words an answer |
| The code | Enforces facts: which products exist, what the client already holds, what amounts are allowed, what the data says |
| The RM | Makes every decision and takes every action |

### How the RM can tell what came from AI

- "AI" and "Rules" tags on each suggested action
- A line on the Suggestions screen naming the model that made the decisions
- "AI-generated, may contain errors, verify before acting" under each model answer
- "Data-only answer" under each deterministic answer
- A notice when an AI answer failed an accuracy check and was replaced

## 6. Controls and guardrails

### The guardrail pipeline

Every chat exchange passes through four rails, two before the model and two after. They are configured in NVIDIA NeMo Guardrails (`backend/app/rails/`) and run in guardrails-only mode, so NeMo never sees the large data prompt.

| Stage | Rail | Type | What it does |
|---|---|---|---|
| Input | Check decision boundary | Deterministic | Blocks requests for the co-pilot to approve, send, change or book something |
| Input | Self check input | Model-based | Blocks prompt injection, requests to reveal the system prompt, role-play attempts, code, and abuse |
| Output | Check grounding | Deterministic | Checks the answer against the data the model was given, including every figure |
| Output | Self check output | Model-based | Blocks claimed or offered actions, guarantees, leaked instructions, and claims that the data is real |

### Deterministic output rules (`backend/app/guard_rules.py`)

These are the hard guarantees. An answer that breaks one is blocked.

| Rule | What it catches |
|---|---|
| `other_client` | A single-client chat answer that names another client |
| `condition_mismatch` | A list answer that includes a client who does not match the question's filter (dormant, risk segment, flagged, holds a product) |
| `forbidden_claim` | A claim that the co-pilot approved, sent or changed something; an offer to do so; a guarantee of an outcome; a reference to a bureau score |
| `rate_quote` | A suggested rate, or a model rate range, quoted for a client with no rate change recommended |
| `product_policy` | A recommendation of a product that is not pitchable, or one the client already holds |

One more rule is also hard since 6 October 2026: `ungrounded_number` blocks an answer that contains an AED amount of 100 or more, a percentage, a day or month count, or a client count that is not in the data the model was given. It was a soft rule that covered only AED amounts of 1,000 or more. Rounding is allowed only to the precision the answer states. See `md_files/improvements/02_number_grounding.md`.

### What happens when a check fails

- **Input blocked:** the RM gets a fixed refusal explaining that decisions and actions stay with them.
- **Output blocked:** the AI answer is discarded and replaced with a deterministic data-only answer. The RM is told this happened.
- **Model unavailable or timed out:** the RM gets the data-only answer with a notice.
- **NeMo unavailable or errors:** the deterministic rules run directly. The hard guarantees do not depend on NeMo or on a model.

### Controls on the pitch decision engine (`suggest_llm.py`, `catalogue.py`)

A model decision is rejected unless all of these hold:

- The kind is one of lending, cross-sell, retention or none
- The product is in the catalogue and is pitchable (10 of the 14 listed products)
- The product's type matches the kind
- The client does not already hold the product
- A retention decision is backed by dormant terminals or falling volume. A rate review or idle balance alone is not enough.
- A reason is present

Amounts are controlled separately:

- Only sized lending products may carry an amount
- An amount above the product's published maximum or the client's supplied working-capital limit is clamped down, and the change is noted
- An amount below the product's published minimum is raised to the minimum
- A decision is rejected if the client's supplied limit is below the product's minimum

### Scope and data controls

- The merchant co-pilot's prompt contains one client's data only
- Questions naming another client are refused before any model call
- The system prompt tells the model the data is synthetic and that the synthetic score is not a bureau score
- With the default local model, no client data leaves the machine

### Operational controls

| Control | Detail |
|---|---|
| Audit log | Append-only JSON Lines file. One line per chat (question, reply, mode, model, guardrail verdict, cache hit, latency, request ID), per suggestion decision and per guardrail error |
| Request ID | Returned with every chat reply so an RM can quote it |
| Rate limit | 30 chat requests per minute per client address, configurable |
| Input limits | Message text clipped to 8,000 characters; the last 12 messages are considered, and older ones are dropped first once the history passes 4,000 characters |
| Prompt budget | The prompt is estimated before each model call and never sent if it exceeds the window (limit 7,402 tokens); the event `prompt_over_budget` is audited |
| Token and timing record | The tokens read and written and the seconds taken, as reported by the model server, are written to the audit log for each chat. The text of a blocked answer is audited too, and never shown |
| Error handling | Provider error detail stays in the server log; the RM sees a generic notice |
| Response cache | Keyed on the full prompt, model and settings, so a cached answer is reused only for the same data and model. Entries expire after 24 hours. Answers are cached only after they pass the output rails |
| Data-quality gate | Invalid rows are quarantined at ingest, and the load is refused if no valid POS rows remain |
| Configuration switches | Guardrails, the model-based rails, the cache, the audit log and the rate limit can each be turned on or off by environment variable |

### Transparency in the interface

- A permanent "Synthetic data" badge with the as-of date
- A disclaimer under the chat box: answers can be wrong, verify before acting
- A label on every reply showing how it was produced

## 7. Project structure

```
RM_Chatbot_2/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app: 9 endpoints, audit wrapper for chat
│   │   ├── config.py          Settings, all overridable by environment variable
│   │   ├── db.py              SQLAlchemy engine and session
│   │   ├── models.py          11 database tables
│   │   ├── ingest.py          CSV validation, load, client facts, quality report
│   │   ├── scoring.py         Attention score, RM action, rule-based pitch
│   │   ├── segments.py        Merchant segments (churn risk, growth-ready, top performer) and the dashboard lists
│   │   ├── rates.py           Suggested rate shown as a range; rewrites stored rate wording
│   │   ├── catalogue.py       Product catalogue and amount validation
│   │   ├── knowledge.py       Builds the product knowledge page the model reads
│   │   ├── suggest_llm.py     AI pitch decision engine with validation and fallback
│   │   ├── readers.py         PortfolioReader and ClientReader (API data shaping)
│   │   ├── copilot.py         Chat: context building, scope guard, fallback answers
│   │   ├── llm.py             Provider switch (Ollama, Anthropic); records token counts
│   │   ├── evidence.py        The "Why this?" evidence and live checks for a suggestion
│   │   ├── feedback.py        RM ratings of suggestions and their summary
│   │   ├── prompt_budget.py   Token estimates and the prompt limit for the model's window
│   │   ├── guardrails.py      NeMo Guardrails integration and fallback
│   │   ├── guard_rules.py     Deterministic guardrail rules
│   │   ├── rails/             NeMo config: config.yml, rails.co, prompts.yml
│   │   ├── chat_cache.py      Exact and semantic response cache (ChromaDB)
│   │   ├── audit.py           Append-only audit log
│   │   └── ratelimit.py       Sliding-window rate limit
│   ├── evals/
│   │   ├── ai_vs_rules.py     Compares stored AI decisions with rule-based ones
│   │   ├── rails_judge_eval.py  Measures the two model-based rails
│   │   ├── prompt_sizes.py    Prompt size per question against the window (offline)
│   │   ├── latency_probe.py   Times the real model on the real prompts
│   │   └── figure_replay.py   Replays audited answers through the figure check (offline)
│   ├── tests/                 188 pytest test cases in 11 files
│   ├── OllamaModelfile        Defines the 8K-context local model variant
│   ├── run_ollama.ps1         Starts the local model service
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/                   Next.js layout, page and design-system styles
│   ├── components/
│   │   ├── App.tsx            Shell, navigation, chat state
│   │   ├── Dashboard.tsx      Opportunities board (default) and all-clients table
│   │   ├── Review.tsx         "Why this?" panel, Useful? Yes / No, rating summary
│   │   ├── Profile.tsx        Merchant profile and analytics
│   │   ├── Suggestions.tsx    Top 10 pitches
│   │   ├── Chat.tsx           Chat card for both co-pilots
│   │   └── Blueprint.tsx      Shared card components
│   └── lib/                   API client, formatters, types
├── structured_data/           Source CSVs and product knowledge documents
├── ml_rate_model.py           Offline rate suggestion model
├── design/                    Design-system assets and UI mock-up
├── md_files/                  Project documentation
└── .vscode/tasks.json         Setup and run tasks
```

### API endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/data/status` | Whether data is loaded, the as-of date, the disclaimer |
| `GET /api/dashboard/top-performers` | The five largest top performers by card volume, with their shares of portfolio and city volume and the step to take |
| `GET /api/dashboard/cross-sell` | The five merchants that lack a product we can offer, with the offer, any growth figures and a loan as a second line |
| `GET /api/dashboard/act-now` | The five merchants to act on now (step 1: high-value churn risks) with the data behind each |
| `GET /api/dashboard` | Clients with reasons and decisions. `filter=opp` returns clients with a suggested action ranked by decision priority; `all` returns every client by attention rank; `high` returns High risk clients |
| `GET /api/clients` | Merchant directory with filters |
| `GET /api/clients/filter-options` | Values and counts for the directory filters |
| `GET /api/clients/{merchant_id}` | One client's full detail |
| `GET /api/suggestions` | Top 10 pitches, optionally by product |
| `GET /api/suggestions/products` | Products with pitch counts |
| `GET /api/clients/{merchant_id}/evidence` | The data and live checks behind the client's current suggestion |
| `POST` / `DELETE /api/clients/{merchant_id}/feedback` | Rate the current suggestion useful or not useful, or remove the rating |
| `GET /api/feedback/summary` | How useful suggestions have been, overall, by AI or rules, by product, with the reasons given |
| `POST /api/copilot/portfolio` | Portfolio chat |
| `POST /api/copilot/clients/{merchant_id}` | Merchant chat |

### Database tables

| Table | Contents |
|---|---|
| `client` | Merchant profile, limits, rates, supplied lending sizing |
| `pos_daily` | One row per merchant per day |
| `client_product` | Products held |
| `ntb_candidate` | Supplied cross-sell candidates with rationale |
| `client_fact` | Computed facts per client |
| `client_monthly_volume` | Monthly volume and activity |
| `client_card_mix` | Card mix for the 30-day and 6-month windows |
| `client_priority` | Attention score, signals, action and rule-based pitch |
| `client_suggestion` | The pitch decision, its source (AI or rules) and model |
| `ingest_run`, `ingest_issue` | Load history and data-quality issues |
| `client_feedback` | RM ratings of suggestions, with a snapshot. On its own base, so a data reload does not erase it |

## 8. Data

All figures below are from the loaded synthetic dataset, as of 3 August 2026.

| Item | Value |
|---|---|
| Merchant clients | 150 |
| Industries | 16 |
| Cities | Dubai 65, Sharjah 40, Ras Al Khaimah 18, Ajman 16, Abu Dhabi 11 |
| RMs and branches | 25 and 8 |
| Daily POS rows | 36,000 (7 December 2025 to 3 August 2026) |
| Total POS volume | AED 453 million across 1.82 million transactions |
| Risk segments | 91 Low, 48 Medium, 11 High |
| Products-held rows | 656 |
| Cross-sell candidate rows | 89 |
| Rows quarantined at ingest | 0 |
| Clients flagged for attention | 29 |
| Clients with a suggested action in the stored decisions | 86 (16 from the model, 70 from the rule fallback) |
| Clients with no suggested action | 64 (not shown on the Opportunities tab) |
| Clients with dormant terminals | 10 |
| Clients with a recommended rate change | 110 |
| Clients with a rule-based lending pitch | 75 (AED 135.7 million of suggested limits) |

**Source files (`structured_data/`).**

| File | Used by |
|---|---|
| `merchant_profiles_v3.csv` | Ingest |
| `pos_daily_acquiring_v3.csv` | Ingest |
| `merchant_products_held_v2.csv` | Ingest |
| `ntb_cross_sell_candidates.csv` | Ingest |
| `business_banking_packages_and_charges.md` | Knowledge page |
| `enbd_business_loans_public_reference.md` | Knowledge page |
| `rm_product_knowledge.md` | Built by `knowledge.py`; read by the model |
| `merchant_rate_waterfall_v1.csv` | Output of the rate model; not loaded by the backend |
| `merchant_opportunity_reasons_v1.csv` | Supporting detail for the opportunity tier; not loaded by the backend |

## 9. Testing and evaluation

**Automated tests (188 test cases from 165 test functions, in `backend/tests/`).** All 188 passed on 7 October 2026, after improvements 01 to 07.

| File | Test cases | Covers |
|---|---|---|
| `test_backend.py` | 21 | Ingest counts, client facts, single-client scoping, pitch rules and validation, the API contract, the local model call, exact and semantic cache hits |
| `test_guardrails.py` | 33 | The guardrail rails and rules |
| `test_responsible_ai.py` | 26 | Prompt-injection and forged-history handling, the other-client scope guard, message clipping, hiding provider errors, the audit log, the rate limit |
| `test_decision_engine.py` | 16 | The pitch decision engine, the dashboard decision fields, and the Opportunities ranking (priority order, clients with no action excluded) |
| `test_context_budget.py` | 14 | Every prompt fits the window with the rules at the head; the header totals; which clients each question lists; knowledge parts; history trimming; merchant prompts for all 150 clients; the over-budget guard; token audit |
| `test_top_performers.py` | 11 | The top-10%-by-card-volume rule, the portfolio and city shares, the ranking without ties, the list, AI versus rule-based steps, retention first for a top performer at risk, the endpoint |
| `test_cross_sell.py` | 12 | The growth-ready rule, selection by the product a merchant lacks, ranking by revenue plus growth, the loan as a second line, AI versus rule-based offers, the endpoint |
| `test_segments.py` | 12 | The churn-risk rule against each client's own figures, tiers, the baseline, the Act now ranking, AI versus rule-based steps, the endpoint |
| `test_rate_ranges.py` | 16 | The rate range, the rewritten rationale and flag wording, the exact rate not reaching the screen or the model, the migration |
| `test_feedback.py` | 15 | Ratings saved with a snapshot and replaced, cleared, audited and summarised; a changed suggestion does not inherit a rating; the evidence, the live checks, the cautions and the explanation check |
| `test_figure_grounding.py` | 12 | Wrong percentages, days, AED amounts and counts are blocked; correct and rounded figures pass; typed pools; single-client chat; a sweep of 275 deterministic answers |


**Evaluation scripts (`backend/evals/`).**

- `ai_vs_rules.py` reads the stored decisions and reports coverage, decision mix, two rule checks that should both be zero (retention without a behavioural signal; pitching a held product), the spread of priorities, and how the AI's pitches differ from the rule-based ones. Its own notes state that different from the rules does not mean better, because there is no ground truth.
- `rails_judge_eval.py` runs the two model-based rails against small hand-written sets of good and bad messages and reports false blocks and misses. It should be re-run whenever the model changes.
- `prompt_sizes.py` prints the estimated prompt size for typical questions and for all 150 merchants against the window limit. Offline.
- `latency_probe.py` sends the real prompts to the local model and prints tokens read and written and the seconds each took.
- `figure_replay.py` replays the model answers in the audit log through the figure check and prints the ones it would now block.

## 10. Known limits

- **Synthetic data.** Nothing here has been validated against real customer outcomes.
- **Rate model accuracy.** The spread model recovers a synthetic pricing rule. Only the interchange figures are real.
- **AI coverage in the current database.** 16 of the 150 stored pitch decisions came from the model; the other 134 are the rule-based fallback. Re-running `python -m app.suggest_llm` from `backend/` regenerates them.
- **Mixed priority scales on the Opportunities tab.** Model decisions score 80 to 94 and rule-based fallbacks 0 to 55, so while only some clients are model-decided, every model-decided client ranks above every rule-based one. Generating decisions for all clients puts them on one scale.
- **Local model speed.** After improvement 01, uncached chats took a median of 5.2 seconds (2.0 to 9.7) over 21 runs, and cached answers about 0.3 to 1.5 seconds. Reading the prompt is now 0.1 to 0.4 seconds; most of the time is writing the reply at about 40 tokens a second. Older audit-log entries, before the fix, averaged about 22 seconds and 10 of 35 chats fell back to a data-only answer after roughly 100 seconds.
- **Long replies can be cut off.** A reply that reaches the 350-token limit stops mid-sentence with no notice. Pitch lists are capped at 5 clients to reduce this.
- **Answer checking is not complete.** Wrong figures are now blocked in most cases, but product names in chat, the pitch "why" text and negated sentences are not yet checked. `md_files/HALLUCINATION_CONTROLS.md` and `md_files/improvements/README.md` list each open gap.
- **No sign-in or access control.** Any user of the app sees every client. The RM and branch IDs in the data are not used to restrict access.
- **No integrations.** There is no link to a CRM or core banking system, and no tracking of whether a pitch was accepted.
- **Rate limit is prototype-grade.** It is held in memory per process and is shared across users behind the frontend proxy.
- **Policy thresholds.** The scoring thresholds were set against the synthetic data and need product sign-off before real use.
- **Opportunity tier and rate waterfall detail** exist as files but are not shown in the app.
