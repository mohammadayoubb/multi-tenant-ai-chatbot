# Owner: Amer
"""Per-scope token-bucket rate limiter for the widget token endpoint.

Implements FR-015 (per-IP) and FR-016 (per-widget) baselines from spec.md.
In-process counters per worker; cross-worker accuracy is a documented limitation
(research.md §Research 2). A Redis-backed implementation satisfying the same
Protocol can be added later without touching this feature.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.services.widget_settings import widget_settings


class RateLimiter(Protocol):
    async def check(self, scope_key: str) -> bool:
        """Return True if the request is allowed; False if rate-limited."""
        ...


@dataclass
class _TokenBucket:
    capacity: int
    refill_per_second: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def try_consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            float(self.capacity),
            self.tokens + elapsed * self.refill_per_second,
        )
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class InMemoryTokenBucketRateLimiter:
    """Token-bucket per scope_key, thread-safe via asyncio.Lock."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def check(self, scope_key: str) -> bool:
        async with self._lock:
            bucket = self._buckets.get(scope_key)
            if bucket is None:
                bucket = _TokenBucket(self._capacity, self._refill)
                self._buckets[scope_key] = bucket
            return bucket.try_consume()


def per_ip_rate_limiter() -> RateLimiter:
    per_minute = widget_settings().widget_rate_per_ip
    return InMemoryTokenBucketRateLimiter(
        capacity=per_minute,
        refill_per_second=per_minute / 60.0,
    )


def per_widget_rate_limiter() -> RateLimiter:
    per_minute = widget_settings().widget_rate_per_widget
    return InMemoryTokenBucketRateLimiter(
        capacity=per_minute,
        refill_per_second=per_minute / 60.0,
    )
