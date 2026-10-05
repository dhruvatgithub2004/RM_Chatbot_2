# Local LLM migration — switching from OpenAI to Qwen3-8B

**Status:** planning. The app currently runs on OpenAI (`gpt-4o-mini`). This document lists what would break or degrade if the model is switched to a local `qwen3:8b` (for example served by Ollama), and what to prepare first.

**Basis:** the app's code (`backend/app/llm.py`, `copilot.py`, `suggest_llm.py`), prompt sizes measured on the running prototype, and general knowledge of running Qwen3 through Ollama. **Nothing here has been tested with a local model yet.** Points marked "verify" depend on the Ollama version in use and must be checked.

---

## 1. Summary

Nothing breaks at the code level, because every call goes through one function (`llm.complete`). But several things would degrade *silently* if only the model name were changed. The most serious is a prompt that exceeds the model's context window and loses its rules without any error.

| Area | Verdict |
|---|---|
| Code structure | Good. One switch point, no provider-specific logic elsewhere |
| Facts and validation | Unaffected. Numbers come from code; product checks, scope guard, fallbacks, rate limit and audit log work with any model |
| Automated tests | Will still pass, because all 42 use a fake LLM. They cannot show how the new model behaves |
| Configuration | Needs additions: base URL, timeout, thinking mode |
| Prompt size | Real risk: silent truncation if the context window is too small |
| Answer quality | Expect a drop. Needs a before and after comparison |
| Data protection | Improves: client data stays inside the bank |

## 2. What could fail or degrade

| # | Risk | What happens | Fix | Effort |
|---|---|---|---|---|
| 1 | **No base URL setting** | `llm.py` always calls OpenAI's own endpoint. A local server needs its own address (for Ollama, usually `http://localhost:11434/v1`), and the code treats an empty API key as "LLM not configured" | Add `LLM_BASE_URL`, and allow a placeholder key for local use | Small |
| 2 | **Context window too small** | Our prompts are large (table below). Ollama's default context is only a few thousand tokens (verify for your version). When a prompt exceeds it, the model can silently drop the start of it, which is where the rules and the knowledge page sit | Set the model's context to 32k, Qwen3-8B's native size, in the model configuration. Add a guard that falls back to the data-only answer if the prompt is larger than the configured window | Small to medium |
| 3 | **Qwen3 "thinking" output** | Qwen3 reasons before answering, sometimes inside `<think>…</think>` tags. That text could appear in the chat, break the JSON parsing in the suggestion engine (it looks for the first `{` and last `}`), and use up the 500-token cap before the answer starts | Turn thinking off, or strip the tags. Raise the suggestion token limit | Small |
| 4 | **JSON output mode** | The suggestion engine requests strict JSON. A local server may handle that option differently (verify) | Test it. The existing retry and rule-based fallback remain as the safety net | Small |
| 5 | **Timeouts and speed** | A local 8B model is slower than the hosted one, and the first request has to load the model. The 45 s chat and 60 s suggestion timeouts may trip, which would show as "AI service unavailable" and data-only answers. Four parallel suggestion workers may compete for GPU memory | Make timeouts configurable. Run the 150-merchant suggestion batch for real and tune the worker count | Small |
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
- **The test suite:** 42 offline tests keep passing.

## 4. Effects on other plans and documents

- **NeMo Guardrails (now implemented):** the two LLM-based rails (`self check input` and `self check output`) call the app's own `llm.complete`, so they switch to the local model together with the chat. Their short Yes/No prompts are what a small model is most likely to get wrong. On `gpt-4o-mini` the first-draft prompts wrongly blocked correct answers until they were rewritten, so expect to re-test. Each judge adds one model call per question, which matters more on local hardware. The hard rails (decision boundary and grounding) are plain Python and do not depend on the model. If the local judge is unreliable, set `GUARDRAILS_LLM_CHECKS=0` and the deterministic rails still run.
- **`feasability.md`:** the largest non-technical risk, sending client data to an external provider (assumption A1), mostly goes away. Hardware sizing and hosting become new topics.
- **`business impact.md`:** per-token cost is replaced by hardware and operating cost.
- **`Role of AI.md` and `RESPONSIBLE_AI.md`:** references to OpenAI, provider processing and model names need updating after the switch.
- **Quality notes:** the observed weaknesses of `gpt-4o-mini` in `BLOCKERS_AND_PENDING_INPUTS.md` (item 14) will need re-measuring on the new model.

## 5. Preparation checklist

Do these while OpenAI is still the active model. None changes current behaviour.

- [ ] Add `LLM_BASE_URL` and a placeholder key rule to `config.py` and `llm.py`
- [ ] Add `LLM_TIMEOUT` (and a separate suggestion timeout) to the configuration
- [ ] Add a thinking-mode switch, and strip `<think>…</think>` blocks from any reply
- [ ] Make the suggestion JSON extraction tolerant of extra text, and raise its token limit for local use
- [ ] Add a context-overflow guard: estimate the prompt size, and if it exceeds `LLM_CONTEXT_TOKENS`, return the data-only answer and log the reason
- [ ] Add a few unit tests for the above (fake LLM, no network)
- [ ] Write a small evaluation script of about 20 questions with expected facts, covering lists of clients, dormant and risk filters, product questions, comparisons, and refusals, and run it on `gpt-4o-mini` first as the baseline
- [x] A regression set for the two NeMo judge prompts already exists: `cd backend && REPEAT=5 python -m evals.rails_judge_eval`. Run it on `gpt-4o-mini` (baseline: all judgements correct over five repeats) and again on `qwen3:8b`. Check the thinking-mode and timeout settings first, because a judge that returns `<think>` text or times out will degrade to the deterministic rules
- [ ] Decide from that result whether the LLM-based rails stay on for the local model (`GUARDRAILS_LLM_CHECKS`)

## 6. Test plan for the switch

1. **Install and configure:** pull `qwen3:8b`, set the context to 32k in the model configuration, and set `LLM_BASE_URL`, `LLM_MODEL=qwen3:8b` and a placeholder key.
2. **Smoke test:** one chat in each co-pilot, and a 5-merchant suggestion run. Check that no `<think>` text appears, JSON parses, and nothing times out.
3. **Truncation test:** ask a portfolio question and confirm the answer still obeys the rules. Check the server log and the guard for context overflow.
4. **Full suggestion batch:** run all 150 merchants. Record the time, the share decided by the model versus the rule fallback, the decision mix and the priority spread, and compare with the current run (145 model decisions and 5 rule fallbacks; 32 retention, 60 cross-sell, 55 lending, 3 none; 12% of priority scores at exactly 55 or 65). `python -m evals.ai_vs_rules` prints all of these from the database.
5. **Evaluation script:** run the question set on both models and compare accuracy. Record the failures.
6. **Update the documents** from section 4 with the measured results, not assumptions.

## 7. Open questions

- Which server will run the model (Ollama, vLLM, or another)? Syntax and limits differ.
- What hardware is available? This decides the context size, parallel workers and speed.
- Should suggestions and chat use different models? The code already supports `SUGGESTION_MODEL`, so a stronger model could be kept for the batch.
- What accuracy on the evaluation set is the minimum for switching?
