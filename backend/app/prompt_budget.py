"""Token budget for the model's context window.

Why this exists: when a prompt is longer than the window, Ollama silently keeps only the END of it (measured: the last 4,098 tokens of
an 8,192-token window) and drops the START, which is where the rules and the knowledge page sit. The model then answers without its
rules and invents the missing facts. So the prompt is sized to fit before it is sent, and a prompt that cannot fit is never sent.

The characters-per-token ratios were measured on qwen3:8b through Ollama (see md_files/improvements/01_context_fit_and_latency.md):
rules text 4.5, knowledge page 3.7, client rows 2.7, merchant JSON 2.4. The values below are rounded down so estimates run high.
"""
from __future__ import annotations

import math

from . import config

PROSE_CHARS_PER_TOKEN = 3.5     # rules, knowledge page, chat turns
DATA_CHARS_PER_TOKEN = 2.4      # client rows and merchant JSON (digits and separators tokenise badly)
TEMPLATE_TOKENS = 30            # chat-template overhead measured at 29
SAFETY = 0.05                   # share of the window kept free
DATA_MARKER = "=== DATA"        # everything from here on in a system prompt is data; everything before it is prose


def prose_tokens(text: str) -> int:
    return math.ceil(len(text) / PROSE_CHARS_PER_TOKEN)


def data_tokens(text: str) -> int:
    return math.ceil(len(text) / DATA_CHARS_PER_TOKEN)


def prompt_limit() -> int:
    """Most tokens a prompt may use: the window, less a safety margin, the room kept for the reply and the template."""
    return math.floor(config.PROMPT_TOKENS * (1 - SAFETY)) - config.LLM_MAX_TOKENS - TEMPLATE_TOKENS


def estimate(system: str, history: list[dict]) -> int:
    """Estimated prompt size in tokens: the system prompt (prose before the data marker, data after it) plus the chat turns."""
    cut = system.find(DATA_MARKER)
    head, body = (system, "") if cut < 0 else (system[:cut], system[cut:])
    return prose_tokens(head) + data_tokens(body) + sum(prose_tokens(m["content"]) for m in history)


def data_chars_left(prose_used_tokens: int) -> int:
    """Characters of data that still fit once `prose_used_tokens` of rules, knowledge and chat turns are in the prompt."""
    return max(0, int((prompt_limit() - prose_used_tokens) * DATA_CHARS_PER_TOKEN))
