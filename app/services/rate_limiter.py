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


# ---------------------------------------------------------------------------
# Per-session `capture_lead` bucket (feature 010 §R6, task T019).
#
# Keyed `lead:{tenant_id}:{session_id}` so the threat model — "an injected
# prompt within one visitor's session spams capture_lead" — gets the right
# unit of granularity. Same in-process backing store as the widget IP /
# widget-id buckets; not Redis-shared because the api process is the only
# writer to a given session key.
#
# Window is a fixed 1-hour rolling count instead of a token bucket so the
# semantics match the per-tenant tenant_settings.rate_limit_lead_per_session
# value exactly: "N writes per hour, hard ceiling".
# ---------------------------------------------------------------------------


@dataclass
class _LeadWindowBucket:
    """Fixed-window counter; resets ``window_seconds`` after the first hit."""

    cap: int
    window_seconds: int
    count: int = 0
    window_started_at: float = field(default_factory=time.monotonic)


class LeadCaptureRateLimiter:
    """Per-session ``capture_lead`` write-rate guard.

    Public method ``check_and_increment`` returns ``True`` when the call is
    permitted (and increments the count) or ``False`` when the cap was already
    reached in the current window. The window is restarted lazily on the next
    permitted call after expiry.
    """

    def __init__(self, default_cap: int = 5, window_seconds: int = 3600) -> None:
        self._default_cap = default_cap
        self._window_seconds = window_seconds
        self._buckets: dict[str, _LeadWindowBucket] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def key(tenant_id: object, session_id: str) -> str:
        return f"lead:{tenant_id}:{session_id}"

    async def check_and_increment(
        self,
        tenant_id: object,
        session_id: str,
        *,
        cap: int | None = None,
    ) -> bool:
        """Record one ``capture_lead`` attempt; return whether it was accepted."""
        effective_cap = cap if cap is not None else self._default_cap
        scope_key = self.key(tenant_id, session_id)
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(scope_key)
            if bucket is None or now - bucket.window_started_at >= self._window_seconds:
                bucket = _LeadWindowBucket(
                    cap=effective_cap,
                    window_seconds=self._window_seconds,
                    window_started_at=now,
                )
                self._buckets[scope_key] = bucket
            else:
                # Allow the cap to be raised/lowered on the fly without rolling
                # the window — the next decision uses the current per-tenant
                # `tenant_settings.rate_limit_lead_per_session` value.
                bucket.cap = effective_cap
            if bucket.count >= bucket.cap:
                return False
            bucket.count += 1
            return True

    async def reset(self, tenant_id: object, session_id: str) -> None:
        """Drop the bucket for one session. Used by tests."""
        scope_key = self.key(tenant_id, session_id)
        async with self._lock:
            self._buckets.pop(scope_key, None)


_LEAD_LIMITER: LeadCaptureRateLimiter | None = None


def lead_capture_rate_limiter() -> LeadCaptureRateLimiter:
    """Return the process-wide ``capture_lead`` rate limiter (singleton)."""
    global _LEAD_LIMITER
    if _LEAD_LIMITER is None:
        _LEAD_LIMITER = LeadCaptureRateLimiter()
    return _LEAD_LIMITER
