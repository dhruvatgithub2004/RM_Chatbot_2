# Local LLM migration — switching from OpenAI to Qwen3-8B

**Status:** the app uses `qwen3:8b-rm`, an 8K-context Ollama variant derived from the unchanged `qwen3:8b` weights, through a dedicated Ollama daemon on port 11435. OpenAI client code remains commented in `backend/app/llm.py` for rollback. All 92 backend tests pass. Live API checks confirmed a portfolio list answered by Qwen in 8 seconds and a merchant summary answered by Qwen in 93 seconds.

**Basis:** the app's code (`backend/app/config.py`, `backend/app/llm.py`, `backend/tests/test_backend.py`), prior prompt-size measurements, and live portfolio/merchant smoke checks. Suggestion-batch quality has not been evaluated with Qwen.

---

## 1. Summary

Chat, guardrails, and suggestions share one provider boundary (`llm.complete`). Ollama is the active default; the request disables Qwen3 thinking, supports JSON output, and sets a configurable context window. A prompt that exceeds that configured window could still lose rules without an error, so full-prompt testing remains important.

| Area | Verdict |
|---|---|
| Code structure | Good. Chat, guardrails, and suggestions share `llm.complete` |
| Facts and validation | Unaffected. Numbers come from code; product checks, scope guard, fallbacks, rate limit and audit log work with any model |
| Automated tests | 92 backend tests pass, including a mocked Ollama request test; they do not establish model quality |
| Configuration | `OLLAMA_BASE_URL`, `LLM_MODEL=qwen3:8b-rm`, and an 8K model context are configured; no local API key is needed |
| Prompt size | Real risk: silent truncation if the context window is too small |
| Answer quality | Unknown until the local model is evaluated on the app's prompts |
| Data protection | Improves: client data stays inside the bank |

## 2. What could fail or degrade

| # | Risk | What happens | Fix | Effort |
|---|---|---|---|---|
| 1 | **Ollama availability** | The app calls `http://127.0.0.1:11435/api/chat`; its dedicated daemon must be running and `qwen3:8b-rm` must exist | Pull the base tag, create the variant, and run `backend\\run_ollama.ps1` | Small |
| 2 | **Context window and memory** | The base Ollama tag was loading 32K and offloading Qwen layers to CPU. The app now uses a derived tag with an explicit 8K context, and question filters reduce portfolio row context | Monitor full-prompt behavior; reduce data further or use more VRAM if prompts exceed the 8K context | Small to medium |
| 3 | **Qwen3 "thinking" output** | The Ollama request sets `think: false`; simple live responses returned without reasoning text | Smoke-test full chat and suggestion workflows for leaked reasoning | Small |
| 4 | **JSON output mode** | Ollama receives `format: "json"`; a live simple JSON completion succeeded, but the full suggestion flow remains untested | Run a suggestion batch. Existing retries and rule-based fallback remain as safety nets | Small |
| 5 | **Timeouts and speed** | The original desktop daemon used a 32K context and left stale runners. The dedicated 8K daemon returned a 29-client Qwen answer. Chat defaults to 350 output tokens and a 120 s Python timeout; LLM guardrail judges passed 54/54 live regression checks | Verify longer portfolio answers and tune suggestion workers on this hardware | Small |
| 6 | **Answer quality** | An 8B model follows long rule lists and checks comparisons less reliably than `gpt-4o-mini`, which already slipped in testing. Expect more wrong answers on questions such as "who is dormant and High risk?", more suggestions rejected by validation (falling back to rules), and a stronger retention bias | Compare on a fixed question set before and after (section 5) | Medium |

### Prompt sizes (measured on the prototype)

| Call | Approx. tokens | Note |
|---|---|---|
| Portfolio chat | about 17.6k per question | The whole book is in every prompt |
| Merchant chat | about 5.1k per question | |
| Suggestion (per merchant) | about 4.3k | About 650k across 150 merchants |

These are characters divided by four. Qwen's tokenizer may produce more tokens for numbers and JSON, so treat them as lower bounds. The portfolio chat is the closest to the limit; scoping the chat to one RM's book (see `feasability.md`, section 3.3) would shrink it a great deal.

## 3. What stays the same

- **Every number the model quotes** is computed in code.
- **Product, amount and eligibility checks** on suggestions.
- **The cross-client guard**, rate limit, audit log and the AI-generated labels.
- **Fallbacks:** data-only chat answers and rule-based pitches when the model fails.
- **The test suite:** 92 backend tests pass. Portfolio and merchant API calls have both returned `mode=llm`; the merchant summary took 93 seconds.

## 4. Effects on other plans and documents

- **NeMo Guardrails (now implemented):** deterministic decision-boundary and grounding checks remain enabled, and both LLM-based input/output judges now default on after passing 54/54 live Qwen regression judgments. Disable only with `GUARDRAILS_LLM_CHECKS=0` if local inference is unavailable.
- **`feasability.md`:** the largest non-technical risk, sending client data to an external provider (assumption A1), mostly goes away. Hardware sizing and hosting become new topics.
- **`business impact.md`:** per-token cost is replaced by hardware and operating cost.
- **`Role of AI.md` and `RESPONSIBLE_AI.md`:** now identify Ollama as the default and the OpenAI evaluation as historical.
- **Quality notes:** the observed weaknesses of `gpt-4o-mini` in `BLOCKERS_AND_PENDING_INPUTS.md` (item 14) will need re-measuring on the new model.

## 5. Preparation checklist

Remaining work after the code switch:

- [x] Add `OLLAMA_BASE_URL` and no-key local configuration
- [x] Build `qwen3:8b-rm` from the original weights with an explicit 8K context; leave `qwen3:8b` unchanged
- [x] Add a dedicated Ollama launcher on port 11435 to avoid the stale 32K desktop daemon
- [x] Add configurable `LLM_TIMEOUT` and `SUGGESTION_TIMEOUT` (120 s and 180 s defaults for Ollama)
- [x] Disable Qwen3 thinking in the Ollama request
- [ ] Make the suggestion JSON extraction tolerant of extra text, and raise its token limit for local use
- [ ] Add a context-overflow guard: estimate the prompt size, and if it exceeds `OLLAMA_NUM_CTX`, return the data-only answer and log the reason
- [x] Add a mocked Ollama request test (no network)
- [ ] Write a small evaluation script of about 20 questions with expected facts, covering lists of clients, dormant and risk filters, product questions, comparisons, and refusals, and run it on `gpt-4o-mini` first as the baseline
- [x] A regression set for the two NeMo judge prompts already exists: `cd backend && REPEAT=5 python -m evals.rails_judge_eval`. Run it on `gpt-4o-mini` (baseline: all judgements correct over five repeats) and again on `qwen3:8b`. Check the thinking-mode and timeout settings first, because a judge that returns `<think>` text or times out will degrade to the deterministic rules
- [x] Enable LLM-based guardrail judges by default after they passed the live Qwen regression set; deterministic checks stay on

## 6. Test plan for the switch

1. **Install and configure:** done on this machine; `qwen3:8b-rm` is built from `qwen3:8b` with `num_ctx=8192`, and the dedicated daemon runs on port 11435.
2. **Smoke test:** portfolio and merchant chat both returned Qwen-generated answers; the merchant summary took 93 seconds. A 5-merchant suggestion run still needs testing.
3. **Truncation test:** ask a portfolio question and confirm the answer still obeys the rules. Check the server log and the guard for context overflow.
4. **Full suggestion batch:** run all 150 merchants. Record the time, the share decided by the model versus the rule fallback, the decision mix and the priority spread, and compare with the current run (145 model decisions and 5 rule fallbacks; 32 retention, 60 cross-sell, 55 lending, 3 none; 12% of priority scores at exactly 55 or 65). `python -m evals.ai_vs_rules` prints all of these from the database.
5. **Evaluation script:** run the question set on both models and compare accuracy. Record the failures.
6. **Update the documents** from section 4 with the measured results, not assumptions.

## 7. Open questions

- What local hardware and context size are available? This decides suggestion workers and response speed.
- Should suggestions and chat use different models? The code already supports `SUGGESTION_MODEL`, so a stronger model could be kept for the batch.
- What accuracy on the evaluation set is the minimum for switching?
