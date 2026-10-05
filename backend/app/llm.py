"""Thin provider switch (OpenAI or Anthropic) used by the co-pilots and the suggestion generator."""
from __future__ import annotations

from . import config


def configured() -> bool:
    return bool(config.LLM_API_KEY)


def complete(system: str, messages: list[dict], *, json_mode: bool = False, max_tokens: int | None = None,
             timeout: float = 45, model: str | None = None) -> str:
    """messages: [{role: user|assistant, content: str}]. Returns the model's text. Raises on any failure."""
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    model = model or config.LLM_MODEL
    if config.LLM_PROVIDER == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=timeout)
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=0.2,
            messages=[{"role": "system", "content": system}, *messages], **kwargs)
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            raise RuntimeError(f"empty model response (finish_reason={choice.finish_reason})")
        return text

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
