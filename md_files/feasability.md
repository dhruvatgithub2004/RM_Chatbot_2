# Feasibility — realistic data and architecture assumptions

This document answers one question: **could the RM Co-pilot run on a real bank's data and infrastructure, and what would we have to assume or build to get there?** It separates what the prototype proves from what it assumes, rates each assumption honestly, and names the gaps. Measurements come from the running prototype. Extrapolations are labelled as such.

---

## 1. Verdict

| Question | Answer |
|---|---|
| Is the concept feasible? | **Yes.** Every input it needs (POS activity, merchant profile, products held, product catalogue) is data a bank's acquiring and relationship systems already hold. |
| Is the prototype production-ready? | **No.** It is a working end-to-end prototype on 150 synthetic merchants with a single-file database, no login, and a full rebuild on every data load. |
| Biggest data risks | Card-level detail (the prototype only has a per-day card label), a real credit or risk rating (the prototype's is synthetic), and real historical pricing to train a rate model. |
| Biggest architecture risks | The portfolio chat sends the whole book to the model on every question, which does not scale. There is no authentication or per-RM scoping. Ingest rebuilds all tables. |
| Biggest non-technical risk | Sending client data to an external AI provider needs the bank's approval (data protection, model risk). | this is solved by taking local llm

## 2. Data

### 2.1 What the prototype uses

| Dataset | Grain | Size | Role |
|---|---|---|---|
| `merchant_profiles_v3.csv` | One row per merchant | 150 rows, about 35 columns | Profile, package, balance, limits, risk segment, current and suggested rate, supplied lending limit |
| `pos_daily_acquiring_v3.csv` | One row per merchant per day | 36,000 rows (240 days per merchant, Dec 2025 to 3 Aug 2026) | Volume, transaction count, chargebacks, terminal status, card label |
| `merchant_products_held_v2.csv` | One row per merchant, one 0/1 column per product | 150 rows, 11 products, 656 held | What each client already has |
| `ntb_cross_sell_candidates.csv` | One row per merchant and candidate product | 89 rows | New-to-bank cross-sell candidates with a rationale |
| Product and charge documents | Text | About 12k characters, consolidated | The "knowledge page" the AI reads |

### 2.2 Assumptions about real data, rated

Confidence means: how likely the real source gives us this as assumed.

| # | Assumption in the prototype | In a real bank | Confidence | Gap or action |
|---|---|---|---|---|
| D1 | POS activity arrives as **daily aggregates per merchant** | The acquiring platform holds settlement and transaction data; a daily roll-up is routine | High | Agree the feed and its timing with the acquiring team |
| D2 | **Terminal status** (Active or Dormant) per day | Terminal management systems record activity; dormancy can be derived from no-transaction days | High | Confirm the definition of dormant |
| D3 | A **card type label per day** (Mass, Premium, Super Premium, Debit, Business) | Card type exists per transaction through the card BIN. A per-day label is a prototype simplification | Medium | The card mix panel is by days carrying each label, not by transaction. Real card mix needs transaction-level BIN data |
| D4 | **All volume is Visa** in the rate model | Merchants also take Mastercard, domestic and wallet schemes | Low | Needs scheme per transaction and each scheme's interchange table |
| D5 | **Merchant master** (name, industry, package, balance, limits, city) | Held in CRM and core banking | High | Data-sharing agreement; masking rules |
| D6 | **Products held** as 0/1 flags per product | Core banking holds this | High | Map the bank's product codes to the catalogue |
| D7 | **Risk segment and "synthetic score"** | The bank has an internal rating or behavioural score | Medium | Replace with the real rating; check it is fit for this use. In the data, risk segment does not track the score, which a real source should resolve |
| D8 | **New-to-bank candidates supplied** as a file | In production someone has to produce them, for example by a propensity model or product rules | Low | A candidate-generation method must be built or provided |
| D9 | **Lending limit supplied** per merchant | Limits come from credit policy and are not a multiple of turnover | Low | In the prototype the limit is a tier multiple of turnover, and turnover appears capped at AED 3.5M for 9 merchants. Use credit-approved limits or a limit model |
| D10 | **Current rate** per merchant | Contract and pricing system hold negotiated rates | High | Feed from the pricing system |
| D11 | **Interchange cost** from the published Visa UAE table | Public scheme tables exist, but the bank's actual scheme and processing fees may differ | Medium | Replace with the bank's real cost of acceptance |
| D12 | **Rate spread** predicted by a model trained on **800 synthetic rows** | Real negotiated-rate history exists | Low | Retrain on real history. Today's accuracy is by construction and says nothing about reality |
| D13 | **Product catalogue and charges** as a document | The bank maintains these; they change | High | Set an owner and a refresh process for the knowledge page |
| D14 | **Facility balances** for the rate model's leverage feature | Held in lending systems | Medium | The model script expects a facilities file that is not in the repository |

**Summary:** the profile, POS, products, rates and catalogue inputs (D1, D2, D5, D6, D10, D13) are realistic. The inputs that would need real work are the card-level detail (D3, D4), the credit and risk view (D7, D9), the cross-sell candidates (D8) and the rate model's training data (D12).

### 2.3 Data quality handling (built)
Ingest checks required columns, value ranges, valid card types, unique keys, and known merchants, and quarantines bad rows. The last load put 0 of 36,000 POS rows into quarantine and raised five named warnings (for example, duplicate business names, and risk segment not tracking the score). A real feed will be messier, and this mechanism is the part that carries over.

### 2.4 Volume and freshness

| Item | Prototype | Assumed real book (extrapolation, not measured) |
|---|---|---|
| Merchants | 150 | 10,000 to 50,000 |
| POS rows | 36,000 (240 days x 150 merchants) | 3.7M to 18M per year (10,000 to 50,000 merchants x 365 days) |
| Database | SQLite, about 4 MB | A standard relational database handles this without special design |
| Refresh | Manual load; data as of 3 Aug 2026 | Nightly batch is enough: RMs act on weekly signals |

Data volume is not the constraint. The two real constraints are the AI context size (section 3.3) and the time to regenerate suggestions (section 3.4).

## 3. Architecture

### 3.1 Today

```
 CSV files ──► ingest (Python) ──► SQLite ──► FastAPI ──► Next.js UI
 (4 files +      validate, compute   (rebuilt     |           (dashboard, profile,
  product docs)  facts, score,       on every     |            suggestions, co-pilot)
                 call the LLM        load)        |
                 for suggestions                  └──► LLM provider (OpenAI or Anthropic)
```

Built and working: validation, computed facts, scoring, per-client AI suggestions with factual validation, two chat co-pilots, audit log, rate limit, 42 automated tests.

### 3.2 Assumed production shape

```
 Acquiring / CRM / core banking / pricing
        │  nightly extract (agreed feeds)
        ▼
 Staging + validation ──► Relational DB (RM-scoped views) ◄── scheduled jobs:
        │                          ▲                          facts, scores,
        │                          │                          suggestions (changed
        ▼                          │                          merchants only)
   Data quality report      FastAPI service ──► Bank-approved LLM endpoint
                                   │                (private deployment or gateway)
                      SSO login ───┤
                                   ├──► Audit log sink (immutable)
                                   └──► Next.js UI
```

| Layer | Prototype | Production assumption |
|---|---|---|
| Feeds | Four CSV files | Scheduled extracts from source systems with an agreed data contract |
| Store | SQLite file | Managed relational database; incremental updates; history retained |
| Compute | Run by hand, or at the end of ingest | Scheduler, with only changed merchants recomputed |
| API | FastAPI, open to anyone who can reach it | Same service behind single sign-on, with each RM limited to their own merchants |
| AI | Public OpenAI or Anthropic API | A bank-approved endpoint (private deployment or gateway), with a documented data-handling agreement |
| Audit | Local JSON Lines file | Central, immutable log with retention rules |
| Secrets | `.env` file, not committed | Secrets manager |
| UI | Next.js, development server | Built and served behind the bank's gateway |

### 3.3 What does not scale, measured

**Portfolio chat.** Each question sends the product page plus one row for every merchant to the model. Measured: 57.8k characters for 150 merchants, about 386 characters per merchant, so about 96 tokens each (characters divided by four).

| Merchants in the prompt | Approx. tokens per question | Comment |
|---|---|---|
| 25 (one RM's book, if that size) | about 2.4k (plus 3.1k for the product page) | Comfortable |
| 150 (prototype) | about 14.5k | Works today |
| 1,000 | about 96k | Slow, costly, near the limits of many models |
| 10,000 | about 965k | Not possible in one prompt |

*Production assumption:* scope the chat to the RM's own book, which also matches access control, and let the model query the data through a small set of safe tools (filter, rank, look up a client) in place of reading every row. The merchant chat is fine as built: about 5.1k tokens per question regardless of book size.

### 3.4 Suggestion batch time
Regenerating all 150 suggestions took about 3.5 minutes with four parallel workers (about 1.4 seconds per merchant overall), and about 650k input tokens. Extrapolating at the same rate, 10,000 merchants would take about 4 hours. Mitigations: recompute only merchants whose data changed, raise concurrency within the provider's rate limits, and run it overnight.

### 3.5 Prototype design choices that would have to change

| Choice | Why it works now | What production needs |
|---|---|---|
| Ingest drops and rebuilds every table | Simple; everything is re-derived from the CSVs | Incremental upserts and migrations. Today a reload also **wipes the stored AI suggestions**, and they must be regenerated. Production should keep history |
| No authentication | Single-user demo | Single sign-on and per-RM row-level scoping |
| Thresholds written in code | Fast to build | Approved, versioned policy parameters with an owner |
| Rate model is a script run outside the app | Keeps the app simple | A scheduled, versioned model pipeline with monitoring, retrained on real data |
| In-memory rate limit | Fine for one process | Shared store so limits hold across several servers |
| Audit log is a local file | Easy to inspect | Immutable central log; consider whether to store question and answer text |

## 4. AI assumptions

| # | Assumption | Status |
|---|---|---|
| A1 | The bank permits sending client data to an LLM provider, or runs a private endpoint | **Not yet agreed.** Needs a data-protection and model-risk review. The prototype uses synthetic data only |
| A2 | A small, inexpensive model is adequate for chat and suggestions | **Partly.** `gpt-4o-mini` works, but an earlier version chose "retention" for 102 of 150 merchants, and it once misclassified a merchant as dormant in chat. With a code-enforced retention rule it now chooses retention for 32, all with a behavioural signal, and the guardrails catch the list errors they can parse. A stronger model is one setting away (`LLM_MODEL`, `SUGGESTION_MODEL`) |
| A3 | Facts come from code and the model only words and judges | **True by design.** Facts are computed in code, quoted by the model, and every AI pitch is validated |
| A4 | The system still works if the AI is down | **True.** Chat falls back to data-only answers and suggestions to rule-based pitches |
| A5 | Provider can be swapped | **True.** One switch between OpenAI and Anthropic; the bank's own endpoint would be a third option |
| A6 | Answer quality can be monitored | **Not built.** There is an audit log but no evaluation set. See `RESPONSIBLE_AI.md`, roadmap item 7 |
| A7 | Cost is acceptable | **Unknown.** Token counts are measured (section 3.3 and `business impact.md` section 8). Price depends on the provider and model chosen |

## 5. Security and compliance assumptions

| Area | Prototype | Needed before real data |
|---|---|---|
| Access | None | Single sign-on; each RM sees only their merchants |
| Data sent to the AI | Client name, balances, volumes, products, masked card number (synthetic) | A minimisation review: send only what each question needs; mask where possible |
| Residency and retention | Provider default | Bank-approved region and retention terms |
| Audit | Local file | Central, immutable, with retention policy |
| Secrets | `.env`, not committed. An API key was once pasted into a chat | Rotate that key; use a secrets manager |
| Model governance | Documented in `RESPONSIBLE_AI.md` and `Role of AI.md` | Register the models; validate and review them under the bank's model-risk policy |

## 6. Feasibility by component

Effort is a rough size from the gap, not a commitment: **S** is days, **M** is weeks, **L** is a quarter or more.

| Component | State | Gap to production | Effort |
|---|---|---|---|
| Ingest and data checks | Working | Real feeds, incremental loads, history | M |
| Computed facts and attention score | Working | Business sign-off on thresholds; back-test | S to M |
| Dashboard, profile, filters | Working | Per-RM scoping; performance on a larger book | S |
| Suggestion engine | Working | Real candidate generation (D8), real limits (D9), stronger model, calibration | M |
| Merchant co-pilot | Working | Authentication; evaluation set | S to M |
| Portfolio co-pilot | Working at 150 merchants | Per-RM scoping and tool-based data access | M |
| Rate model | Script, synthetic training | Real history, real costs, scheduled pipeline | L |
| Audit, rate limit, guards | Working | Central log, shared limiter, red-team tests | S to M |
| Authentication and access control | Missing | Single sign-on, row-level security | M |
| Hosting, monitoring, support | Missing | Standard platform work | M |

## 7. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| The AI says something wrong in a chat | Facts come from code; answers are labelled "verify before acting"; an evaluation set and audit review catch regressions |
| Client data leaves the bank | Private or approved endpoint; send only what is needed; documented agreement |
| Recommendations do not match real conditions (data is synthetic) | Back-test the attention score on real history before any live use |
| Rate suggestions are mistaken for advice | Keep them labelled illustrative; retrain on real data; the RM decides |
| Thresholds and rules lack sign-off | Assign an owner; version them; review after the pilot |
| Cost grows with the book | Scope chat to the RM's book; recompute only what changed; choose model by value |

## 8. Suggested path

| Phase | What happens | Exit test |
|---|---|---|
| 0. Access | Agree feeds and the data-handling position; pick a pilot team and an approved AI endpoint | Data contract signed; AI route approved |
| 1. Shadow | Run on real data for a small group of merchants; RMs see outputs but do not rely on them | Attention score back-tested; wrong-answer rate measured |
| 2. Pilot | A few RMs use it in their weekly routine, with a comparison group | Measures in `business impact.md` section 7 collected |
| 3. Scale | Authentication, scoped chat, scheduled jobs, monitoring, retrained rate model | Pilot targets met; security and model-risk sign-off |

## 9. What the prototype proves, and what it does not

**Proves:** the end-to-end idea works. Data is validated, facts are computed in code, the AI decides within enforced rules, the RM sees ranked and explained recommendations, and the system degrades safely when the AI fails.

**Does not prove:** that the data will look this way in a real bank, that the recommendations are right for real merchants, that RMs will use it, or that it creates revenue. All of that is for the pilot.
