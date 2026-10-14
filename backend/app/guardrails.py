"""NVIDIA NeMo Guardrails for the RM co-pilots.

Two rail stages wrap the app's own LLM call (copilot.py is unchanged in how it generates an answer):

    question ──► INPUT rails ──► main LLM (llm.complete, our prompt and data) ──► OUTPUT rails ──► RM

NeMo's `check_async` runs the rails on their own (guardrails-only mode), so NeMo never sees the large data prompt. The rails are
configured in app/rails/ (config.yml, rails.co, prompts.yml). Two are deterministic Python actions (app/guard_rules.py) and two are
NeMo's LLM-based self-checks, which run on the app's own model through `_Adapter`, so switching the app to a local model switches
the rails with it.

If NeMo cannot be loaded or a check errors, the deterministic rules run directly (engine = "rules"), so the hard guarantees never
depend on NeMo or on an LLM.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import audit, config, guard_rules, llm
from .guard_rules import GroundingContext, Violation

log = logging.getLogger("rm_copilot.guardrails")
RAILS_DIR = Path(__file__).resolve().parent / "rails"
DECISION_MESSAGE = ("I can recommend and explain, but I can't approve, send, change or book anything. Those decisions and actions stay "
                    "with you as the RM. I can show the supporting data or the suggested next step if that helps.")
CHECK_SYSTEM = "You are a strict policy checker. Reply with exactly one word: Yes or No."

# Per-request state read by the rail actions. It is set inside the coroutine that runs the rails, so it follows the NeMo call.
_question: ContextVar[str] = ContextVar("rails_question", default="")
_answer: ContextVar[str] = ContextVar("rails_answer", default="")
_ctx: ContextVar[Optional[GroundingContext]] = ContextVar("rails_ctx", default=None)


@dataclass
class Verdict:
    allowed: bool = True
    stage: str = "input"                 # input | output
    rail: str | None = None              # name of the rail that blocked
    message: str | None = None           # refusal text (input rails)
    violations: list[Violation] = field(default_factory=list)
    engine: str = "nemo"                 # nemo | rules (NeMo unavailable, deterministic rules ran directly) | off

    def info(self) -> dict:
        return {"stage": self.stage, "rail": self.rail, "blocked": not self.allowed, "engine": self.engine,
                "violations": [str(v) for v in self.violations]}


# ── adapter: NeMo's LLM interface over the app's own llm.complete ───────────
class _Adapter:
    """Implements NeMo's LLMModel protocol on top of llm.complete, so rails use the app's configured model."""

    @property
    def model_name(self) -> str:
        return config.LLM_MODEL

    @property
    def provider_name(self) -> Optional[str]:
        return config.LLM_PROVIDER

    @property
    def provider_url(self) -> Optional[str]:
        return None

    async def generate_async(self, prompt, *, stop=None, **kwargs):
        from nemoguardrails.types import LLMResponse

        system, messages = CHECK_SYSTEM, []
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            for m in prompt:
                role = getattr(m.role, "value", m.role)
                content = m.content if isinstance(m.content, str) else str(m.content or "")
                if role == "system":
                    system = content
                else:
                    messages.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        max_tokens = min(int(kwargs.get("max_tokens") or 50), 200)
        text = await asyncio.to_thread(llm.complete, system, messages, max_tokens=max_tokens, timeout=config.LLM_TIMEOUT)
        return LLMResponse(content=text, model=config.LLM_MODEL)

    async def stream_async(self, prompt, *, stop=None, **kwargs):
        raise NotImplementedError("streaming is not used by the rails")
        yield  # pragma: no cover - makes this an async generator, as the protocol requires


# ── the deterministic rails, registered as NeMo actions ─────────────────────
def _actions():
    from nemoguardrails.actions.actions import action
    from nemoguardrails.actions.rail_outcome import RailOutcome

    @action(is_system_action=True)
    async def check_decision_boundary(context: Optional[dict] = None, **kwargs):
        text = (context or {}).get("user_message") or _question.get()
        if text and guard_rules.is_action_request(text):
            return RailOutcome.block(reason="the user asked the co-pilot to take an action")
        return RailOutcome.allow()

    @action(is_system_action=True)
    async def check_grounding(context: Optional[dict] = None, **kwargs):
        ctx = _ctx.get()
        answer = (context or {}).get("bot_message") or _answer.get()
        if ctx is None or not answer:
            return RailOutcome.allow()
        violations = guard_rules.check_answer(_question.get(), answer, ctx)
        ctx.violations.extend(violations)
        hard = [v for v in violations if v.hard]
        if hard:
            return RailOutcome.block(reason="; ".join(str(v) for v in hard[:3]))
        return RailOutcome.allow()

    return {"check_decision_boundary": check_decision_boundary, "check_grounding": check_grounding}


# ── engine: one background event loop, NeMo built lazily ────────────────────
class _Loop:
    """NeMo is async and its objects bind to an event loop, so every call runs on one dedicated loop thread."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, name="guardrails-loop", daemon=True).start()

    def run(self, coro, timeout: float):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)


_lock = threading.Lock()
_loop: _Loop | None = None
_engines: dict[bool, Any] = {}
_unavailable: str | None = None


def _engine(llm_checks: bool):
    global _loop, _unavailable
    with _lock:
        if _unavailable:
            raise RuntimeError(_unavailable)
        if llm_checks not in _engines:
            try:
                from nemoguardrails import LLMRails, RailsConfig

                cfg = RailsConfig.from_path(str(RAILS_DIR))
                if not llm_checks:  # keep only the deterministic rails
                    cfg.rails.input.flows = [f for f in cfg.rails.input.flows if not f.startswith("self check")]
                    cfg.rails.output.flows = [f for f in cfg.rails.output.flows if not f.startswith("self check")]
                rails = LLMRails(cfg, llm=_Adapter())
                for name, fn in _actions().items():
                    rails.register_action(fn, name)
                _engines[llm_checks] = rails
            except Exception as e:  # noqa: BLE001 - NeMo missing or misconfigured: fall back to the deterministic rules
                _unavailable = f"{type(e).__name__}: {e}"
                log.warning("NeMo Guardrails unavailable, using the deterministic rules directly: %s", _unavailable)
                audit.record("guardrail_error", stage="startup", error=type(e).__name__)
                raise
        if _loop is None:
            _loop = _Loop()
        return _engines[llm_checks]


def warm_up() -> None:
    """Build the engines in the background at startup so the first chat is not slow."""
    try:
        _engine(False)
        if config.LLM_API_KEY and config.GUARDRAILS_LLM_CHECKS:
            _engine(True)
    except Exception:  # noqa: BLE001 - already logged
        pass


async def _run_input(rails, question: str):
    from nemoguardrails.rails.llm.options import RailType

    token = _question.set(question)
    try:
        return await rails.check_async([{"role": "user", "content": question}], rail_types=[RailType.INPUT])
    finally:
        _question.reset(token)


async def _run_output(rails, question: str, answer: str, ctx: GroundingContext):
    from nemoguardrails.rails.llm.options import RailType

    tq, ta, tc = _question.set(question), _answer.set(answer), _ctx.set(ctx)
    try:
        return await rails.check_async([{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
                                       rail_types=[RailType.OUTPUT])
    finally:
        _question.reset(tq), _answer.reset(ta), _ctx.reset(tc)


# ── public API (synchronous: the FastAPI endpoints run in worker threads) ───
def check_input(question: str, *, use_llm: bool) -> Verdict:
    """Run the input rails on the RM's question. `use_llm` adds NeMo's LLM-based self-check (needs a configured LLM)."""
    if not config.GUARDRAILS_ENABLED:
        return Verdict(stage="input", engine="off")
    try:
        rails = _engine(use_llm and config.GUARDRAILS_LLM_CHECKS)
        result = _loop.run(_run_input(rails, question), config.GUARDRAILS_TIMEOUT)
        if result.status.value == "blocked":
            return Verdict(False, "input", result.rail, result.content)
        return Verdict(stage="input")
    except Exception as e:  # noqa: BLE001
        log.warning("input rails errored (%s): %s", type(e).__name__, e)
        audit.record("guardrail_error", stage="input", error=type(e).__name__)
        if guard_rules.is_action_request(question):
            return Verdict(False, "input", "check decision boundary", DECISION_MESSAGE, engine="rules")
        return Verdict(stage="input", engine="rules")


def check_output(question: str, answer: str, ctx: GroundingContext, *, use_llm: bool) -> Verdict:
    """Run the output rails on the model's answer. Soft findings are returned in `violations` but do not block."""
    if not config.GUARDRAILS_ENABLED:
        return Verdict(stage="output", engine="off")
    ctx.violations.clear()
    try:
        rails = _engine(use_llm and config.GUARDRAILS_LLM_CHECKS)
        result = _loop.run(_run_output(rails, question, answer, ctx), config.GUARDRAILS_TIMEOUT)
        blocked = result.status.value == "blocked"
        return Verdict(not blocked, "output", result.rail if blocked else None, None, list(ctx.violations))
    except Exception as e:  # noqa: BLE001
        log.warning("output rails errored (%s): %s", type(e).__name__, e)
        audit.record("guardrail_error", stage="output", error=type(e).__name__)
        found = guard_rules.check_answer(question, answer, ctx)
        hard = [v for v in found if v.hard]
        return Verdict(not hard, "output", "check grounding" if hard else None, None, found, engine="rules")
