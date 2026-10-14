"""Thin provider switch used by the co-pilots, guardrails, and suggestion generator."""
from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

from . import config


_usage = threading.local()


def last_usage() -> dict | None:
    """Token counts and timings (seconds) the model server reported for the most recent call on this thread, if it reported any."""
    return getattr(_usage, "value", None)


def configured() -> bool:
    return bool(config.LLM_API_KEY)


def complete(system: str, messages: list[dict], *, json_mode: bool = False, max_tokens: int | None = None,
             timeout: float | None = None, model: str | None = None) -> str:
    """messages: [{role: user|assistant, content: str}]. Returns the model's text. Raises on any failure."""
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    timeout = config.LLM_TIMEOUT if timeout is None else timeout
    model = model or config.LLM_MODEL
    if config.LLM_PROVIDER == "ollama":
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
            "think": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {"num_predict": max_tokens, "num_ctx": config.OLLAMA_NUM_CTX, "temperature": 0.2},
        }
        if json_mode:
            payload["format"] = "json"
        request = Request(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chunks = []
        _usage.value = None
        with urlopen(request, timeout=timeout) as response:
            for line in response:
                if not line.strip():
                    continue
                result = json.loads(line.decode("utf-8"))
                if result.get("error"):
                    raise RuntimeError(result["error"])
                if result.get("done"):
                    _usage.value = dict(prompt_tokens=result.get("prompt_eval_count"), reply_tokens=result.get("eval_count"),
                                        prompt_s=round(result.get("prompt_eval_duration", 0) / 1e9, 2),
                                        reply_s=round(result.get("eval_duration", 0) / 1e9, 2))
                content = result.get("message", {}).get("content")
                if content:
                    chunks.append(content)
        text = "".join(chunks).strip()
        if not text:
            raise RuntimeError("empty model response")
        return text

    if config.LLM_PROVIDER == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=timeout)
        resp = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                      messages=messages, output_config={"effort": "low"})
        if resp.stop_reason == "refusal":
            raise RuntimeError("model declined to answer")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("empty model response")
        return text

    # OpenAI implementation retained for rollback. To restore it, uncomment this block,
    # remove the Ollama default in config.py, and set LLM_PROVIDER=openai.
    # if config.LLM_PROVIDER == "openai":
    #     from openai import OpenAI
    #
    #     client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=timeout)
    #     kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    #     resp = client.chat.completions.create(
    #         model=model, max_tokens=max_tokens, temperature=0.2,
    #         messages=[{"role": "system", "content": system}, *messages], **kwargs)
    #     choice = resp.choices[0]
    #     text = (choice.message.content or "").strip()
    #     if not text:
    #         raise RuntimeError(f"empty model response (finish_reason={choice.finish_reason})")
    #     return text
    raise RuntimeError(f"unsupported LLM provider: {config.LLM_PROVIDER}")
