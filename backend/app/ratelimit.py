"""Basic in-memory sliding-window rate limit for the chat endpoints (per client address).

Prototype-grade: state is per process and resets on restart. Behind the Next.js proxy every browser reaches the API from the
proxy's address, so the limit is effectively shared; raise RATE_LIMIT_PER_MIN for busy demos, or set it to 0 to disable.
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import audit, config


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0, now: float | None = None) -> float | None:
        """Record a hit. Returns None if allowed, else the seconds until the oldest hit leaves the window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return window - (now - q[0])
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def chat_rate_limit(request: Request) -> None:
    """FastAPI dependency for the co-pilot endpoints."""
    if config.RATE_LIMIT_PER_MIN <= 0:
        return
    key = request.client.host if request.client else "unknown"
    retry = limiter.check(key, config.RATE_LIMIT_PER_MIN)
    if retry is not None:
        audit.record("rate_limited", client=key, path=request.url.path, limit_per_min=config.RATE_LIMIT_PER_MIN)
        raise HTTPException(429, detail={"code": "rate_limited", "message": "Too many requests. Please wait a moment and try again."},
                            headers={"Retry-After": str(max(1, math.ceil(retry)))})
