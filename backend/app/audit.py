"""Append-only audit log (JSON Lines): one line per chat request, suggestion decision and rate-limit hit.

Auditing must never break the app, so write failures are logged and swallowed. API keys are never passed in here;
question/reply text is recorded so an RM's use of the co-pilot can be reviewed afterwards (synthetic data in this prototype).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()
_log = logging.getLogger("rm_copilot.audit")
MAX_TEXT = 4000


def _clip(v):
    return v[:MAX_TEXT] if isinstance(v, str) else v


def record(event: str, **fields) -> None:
    if not config.AUDIT_LOG_ENABLED:
        return
    try:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event,
                 **{k: _clip(v) for k, v in fields.items()}}
        line = json.dumps(entry, default=str, ensure_ascii=False)
        with _lock, open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 - never let auditing break a request
        _log.exception("audit write failed")
