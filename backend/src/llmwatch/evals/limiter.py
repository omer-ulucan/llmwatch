"""
Module: limiter.py (evals)
Purpose: Per-provider throttling for eval runs.
WHY: A suite with hundreds of cases (times several variants) would otherwise hammer a
provider and turn into a wall of 429s. Each provider gets a cap on concurrent
requests and a requests-per-minute token bucket, shared by every run in the process.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from llmwatch.config import settings


class ProviderLimiter:
    def __init__(self, concurrency: int, rpm: int, clock=time.monotonic):
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._rate = max(1, rpm) / 60.0  # tokens per second
        self._capacity = max(1.0, min(float(rpm), self._rate * 10))
        self._tokens = self._capacity
        self._clock = clock
        self._updated = clock()
        self._lock = asyncio.Lock()

    async def _take_token(self) -> None:
        while True:
            async with self._lock:
                now = self._clock()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) * self._rate
                )
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._rate
            await asyncio.sleep(wait)

    @asynccontextmanager
    async def slot(self):
        async with self._sem:
            await self._take_token()
            yield


_limiters: dict[str, ProviderLimiter] = {}


def for_provider(provider_id: str) -> ProviderLimiter:
    limiter = _limiters.get(provider_id)
    if limiter is None:
        limiter = ProviderLimiter(
            settings.eval_provider_concurrency, settings.eval_provider_rpm
        )
        _limiters[provider_id] = limiter
    return limiter


def reset() -> None:
    """Forget limiters (tests, or after changing settings)."""
    _limiters.clear()
