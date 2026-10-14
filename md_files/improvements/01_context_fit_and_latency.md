# Improvement 01: the prompt now fits the model's window, and answers are faster

| | |
|---|---|
| **Status** | Done, 6 October 2026 |
| **Closes** | Gap 1 in `HALLUCINATION_CONTROLS.md` (the portfolio prompt was larger than the model's context window) |
| **Also improves** | Chat latency, merchant-chat headroom, answer quality |
| **Tests** | 14 new in `backend/tests/test_context_budget.py`; full suite 122 passing |
| **Re-run the numbers** | `python -m evals.prompt_sizes` (offline) and `python -m evals.latency_probe` (needs the local model), from `backend/` |

## 1. The problem, as measured

We first estimated the portfolio prompt at about 12,800 tokens against an 8,192-token window, and assumed the model lost some of the data. Measuring on the real model (qwen3:8b through Ollama, `num_ctx` 8,192) showed the problem was worse and different.

**Test:** a prompt with a marker code at the very start (`HEADCODE=PINEAPPLE-17`) and one at the very end, followed by a question asking for both codes.

| Prompt size (characters) | Tokens the model server processed | What the model said |
|---|---|---|
| 8,055 | 2,918 | Both codes correct |
| 14,055 | 5,252 | Both codes correct |
| 18,055 | 6,876 | Both codes correct |
| 22,055 | **4,098** | Head code **invented** (`HEAD89`); tail code correct |
| 26,055 | **4,098** | Head code **invented** (`HEADStrong`) |
| 30,055 and 40,055 | **4,098** | Head code **invented** |

**What this shows:**

1. A prompt over the window is **silently cut at the start**. The server keeps only the last 4,098 tokens and reports no error.
2. The start of our prompt is the **rules and the knowledge page**. The data comes last, so the model kept the data and lost its instructions.
3. Client rows cost about **2.7 characters per token**, not 4. Measured: rules text 4.5, knowledge page 3.7, client rows 2.7, merchant JSON 2.4. The old portfolio prompt was about **20,000 tokens**, not 12,800.
4. The largest prompt that still passed uncut was about 8,000 tokens (21,042 characters) with a 350-token reply allowance.
5. The merchant chat was close to the edge too: 7,170 to 7,791 estimated tokens on the first turn, so a second turn pushed it over.

**What the cut did to real answers** (same five questions, old prompt):

| Question | Old answer | Truth |
|---|---|---|
| Portfolio summary | "Total Merchants: 50", prices in `$`, headings and emoji | 150 clients; the rules forbid headings |
| What are the package fees? | A generic paragraph about "costs associated with financial services" | The fee table was in the cut part |
| Which clients have the highest balance? | Baird Hospitality Group first, at AED 3,280,325 | Brown Builders, AED 2,053,840; Baird's balance is AED 1,254,908 |

## 2. What changed

| File | Change |
|---|---|
| `backend/app/prompt_budget.py` (new) | Token estimates per kind of text, the prompt limit, and the room left for data |
| `backend/app/copilot.py` | Question-specific data views, a header of totals, row limits, a budget cap, history trimming, a compact merchant context, an over-budget guard, token usage in the audit |
| `backend/app/knowledge.py` | The knowledge page is split into three parts and a question gets only the parts it needs; the full page is unchanged |
| `backend/app/readers.py` | Adds prior-30-day volume to the portfolio rows so the header can show the portfolio change |
| `backend/app/llm.py`, `main.py` | Record the token counts and timings the model server reports, and write them to the audit log |
| `backend/app/config.py`, `.env.example` | Three settings: `PROMPT_TOKENS`, `HISTORY_MAX_CHARS`, `PORTFOLIO_ROW_LIMIT` |
| `SYSTEM_RULES` | One added rule: when the header says clients were not listed, say the list is partial and quote the header counts |

The window stays at 8,192 tokens. That size was chosen for speed, and the fix keeps it: the prompt is sized to fit instead of the window being enlarged.

## 3. How it works

**The budget.** `prompt limit = floor(8192 × 0.95) − 350 (reply) − 30 (template) = 7,402 tokens`. Estimates use ratios rounded down (prose 3.5, data 2.4 characters per token), so they run high.

**A portfolio question now gets two things:**

1. **A header of totals over all 150 clients**, always sent:
   `clients=150 | flagged_for_attention=29 (19%) | dormant_terminals_now=10 (7%) | risk_high=11 | ... | rate_change_recommended=110 (73%) | lending_pitch=70 | cross_sell_pitch=14 | total_volume_last30d_aed=53,451,120 | ... | portfolio_volume_change_vs_prior30d=-4.0% | total_balance_aed=21,204,015`
2. **The rows of the clients the question is about**, with only the fields it needs, and a line saying how many were left out (`matching_clients=70 listed=5 ... | NOT LISTED: 65 more matching clients`).

**Which clients and fields, by topic:**

| Question is about | Clients listed | Fields | Order | Limit |
|---|---|---|---|---|
| Lending, cross-sell, pitches | Clients with a pitch (lending-only or cross-sell-only if the question says so) | pitch, rank, limit, opportunity, next action | Pitch rank | 5 |
| Rates | Clients with a recommended rate change | current rate, new rate | Size of change | 8 |
| Flagged, attention, why | Flagged clients | reason, score, action | Attention rank | 8 |
| Dormant | Dormant clients | days, volume change, reason | Days dormant | 8 |
| Risk | All, High risk first | risk, flagged, reason | Risk segment | 8 |
| Volume, growth, decline, limits | All | volume, change, limit used | The figure asked about | 8 |
| Balance | All | balance, package | Balance | 8 |
| Products, packages | All | package, products held | Attention rank | 8 |
| A city, package or industry named | That subset only | as above | as above | as above |
| A client named | That client's full record (up to 5 clients) | all fields | As named | none |
| A filter ("dormant and high risk") | Every client that meets all conditions | names and the filter fields | Attention rank | none |
| Anything else | Top clients | overview fields | Attention rank | 8 |
| A fee or product-catalogue question | None (answered from the knowledge page) | none | n/a | 0 |

**Knowledge page on demand.** The page is about 3,400 tokens. A question now gets: nothing (portfolio questions about clients), the data dictionary and allowed products (about 1,300 tokens), plus the packages section for fee and package questions, plus the loans section for loan questions. The merchant chat always gets the first part.

**Merchant context.** The chart-height block is dropped, and the 30-day daily series and the monthly series are written as short pipe-separated lines. Those two series were 45% of the JSON.

**Long conversations.** Older turns are dropped first once the history passes 4,000 characters. The newest question is always kept, so a long chat cannot push the rules out of the window.

**A safety net.** Before every model call the prompt is estimated. A prompt over the limit is never sent: the RM gets the data-only answer and an audit event `prompt_over_budget` is written.

## 4. Results

### Prompt size the model actually read

| Question | Before: tokens processed | After: tokens processed | Before: prompt was |
|---|---|---|---|
| Portfolio summary | 4,098 (cut) | 1,019 | about 20,000, cut to the last 4,098 |
| Lending opportunities? | 4,098 (cut) | 1,519 | about 20,500, cut |
| What are the package fees? | 4,098 (cut) | 3,347 | about 23,000, cut |
| Which clients have the highest balance? | 4,098 (cut) | 1,057 | about 20,000, cut |
| Which clients are flagged? | 830 | 994 | fit already |

The "After" numbers are the tokens the model server reported, so they are the full prompt with nothing cut.

### Latency, same questions, same script, same model

| Question | Before: read / wrote / total | After: read / wrote / total |
|---|---|---|
| Portfolio summary | 2.1 s / 350 tokens / 19.4 s (includes model load) | 0.3 s / 350 tokens / 9.3 s |
| Lending opportunities? | 1.9 s / 350 / 10.6 s | 0.3 s / 350 / 8.3 s |
| What are the package fees? | 1.9 s / 350 / 10.6 s | 1.3 s / 94 / **3.6 s** |
| Which clients have the highest balance? | 1.9 s / 350 / 10.4 s | 0.1 s / 120 / **3.0 s** |
| Which clients are flagged? | 0.4 s / 144 / 3.8 s | 0.4 s / 144 / 3.9 s |

Reading the prompt fell from about 2 s to 0.1–0.3 s for most questions. The remaining time is mostly **writing the reply**, at about 40 tokens per second. The short answers (balance, fees) now take 3 to 4 seconds. Long answers still take about 8 seconds because they use the whole 350-token reply allowance.

### Through the real API, with guardrails and cache on

30 chats over three runs (21 of them uncached):

| | Before (older audit-log entries) | After (this work) |
|---|---|---|
| Typical uncached model answer | 21.7 s average over 13 chats, up to 93 s | **5.2 s median, 2.0 to 9.7 s range** over 21 chats (two of them ended in a blocked answer, which still includes the model call) |
| Chats that fell back to a data-only answer because the model call failed or timed out | 10 of 35, taking 97 s on average and up to 122 s | 0 of 30 |
| Chats answered from the cache | 8 of 35 | 9 of 30 (0.3 to 1.5 s). In the final run 7 of 11 were cache hits, because the earlier run had cached them |

The "before" figures are from earlier sessions and were not a controlled comparison: the model may have been cold or busy then. The controlled comparison is the table above.

### Merchant chat

| | Before | After |
|---|---|---|
| First turn, estimated tokens | 7,170 to 7,791 | **3,860 to 4,451** (summary, risk, cross-sell); 6,639 at most when fees and loans are both asked |
| Follow-up turn | Over the limit | Fits for all 150 clients, in every knowledge case |
| Tokens the server read (live) | not measured | 4,192 to 4,277 |

### Answer quality, same questions

| Question | Before | After |
|---|---|---|
| Portfolio summary | "Total Merchants: 50", `$`, headings | 150 clients, 29 flagged (19%), 10 dormant, 11 High / 48 Medium / 91 Low, 110 rate changes, volume change -4.0%. All match the data. |
| What are the package fees? | Generic paragraph | The real package fees from the knowledge page |
| Which clients have the highest balance? | Wrong order, AED 3,280,325 | Brown Builders AED 2,053,840, Garcia Salon AED 1,823,675, Arellano Tech Store AED 1,660,121, Baird Hospitality AED 1,254,908, Cruz Beauty Lounge AED 993,991. Matches the database. |

### The estimator is safe

In 19 uncached calls, the estimate was above the token count the server reported every time, by 2% to 34%.

## 5. Tests

14 new tests in `test_context_budget.py`:

- Every portfolio prompt for 14 typical questions fits the limit and starts with the rules
- The old full dump did not fit, and the new prompt is under a fifth of its size
- The header counts cover all clients (clients, flagged, dormant, rate changes, total volume)
- Each topic lists the right clients in the right order (lending, cross-sell, rates, dormant, a city, balance, a named client)
- A partial list says so, and pitch questions list 5
- The room left in the window caps the rows
- A fee question gets the knowledge page and no client rows; knowledge parts are chosen by the question; the full page is byte-identical to before
- Long history drops the oldest turns and keeps the newest; one very long question is kept whole
- Every merchant prompt for all 150 clients fits on a follow-up turn, and uses compact context
- An over-budget prompt is answered from data and never sent to the model
- Token counts are audited and not returned to the browser

One existing test changed: the guardrail test that expected soft findings (see improvement 02).

## 6. What is not solved

- **Long replies still hit the 350-token cap.** One of four pitch answers in the last run reached it. A cut-off reply is not detected or marked. Next step: detect `reply_tokens` at the cap and say so, or shorten the per-client format.
- **Topic choice is keyword-based.** A question worded outside the patterns gets the overview (top 8 by attention rank) and the header. The header counts stay right, and the model is told to say "not available" for what it was not given, but it may list the wrong subset.
- **The ratios belong to this model.** If the model or its tokenizer changes, re-run `evals.latency_probe` and `evals.prompt_sizes` and update the ratios in `prompt_budget.py`.
- **A cold first request still pays the model load time.**
- **The merchant chat still sends the client's whole record** (about 2,200 tokens of JSON). It fits; it is not minimal.
- **We did not test a larger window.** A 16K window might also have fixed the cut, but it would not have fixed the prompt being mostly rows the question does not need.

## 7. Questions a judge may ask

**"Why not just raise the context window?"**
The window was kept at 8K for speed. The fix sends what the question needs: about 1,000 to 1,500 tokens instead of about 20,000. Reading 4,100 tokens took about 2 seconds; reading about 1,000 took 0.1 to 0.4 seconds. We did not test a bigger window, and it would still make the model read rows it does not need.

**"How do you know the prompt was being cut?"**
We put a marker code at the start and the end of prompts of increasing size and asked the model for both. Up to about 8,000 tokens it returned both. Above that the server reported 4,098 tokens processed and the model invented the start code.

**"If you only show 5 or 8 clients, is the answer incomplete?"**
The header always carries the counts and totals for all 150 clients, the data says how many matching clients were not listed, and the model is told to say the list is partial. Filter questions ("dormant and high risk") list every match.

**"What stops the same thing happening again?"**
The prompt is estimated before every call. One over the limit is never sent. The estimate came out above the real count in all 19 measured calls, and the token counts the server reports are written to the audit log for every chat.

**"Did accuracy really improve, or only speed?"**
Both, and accuracy is the larger gain. The old answers were produced without the rules and with most of the data missing. The same questions now return figures that match the database.

## 8. Changelog

- 6 Oct 2026: measured the truncation; added the budget, views, header, knowledge parts, compact merchant context, history trimming, guard and usage audit; pitch lists capped at 5 after one answer reached the reply cap; default list limit set to 8.
