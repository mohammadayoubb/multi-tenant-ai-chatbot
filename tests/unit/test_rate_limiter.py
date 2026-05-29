# Owner: Nasser
"""Unit tests for the new per-session ``capture_lead`` bucket (task T020).

Covers:
- 5 successive calls succeed against the default cap of 5.
- The 6th call returns False (rate-limited).
- The cap is configurable per call (so ``tenant_settings.rate_limit_lead_per_session``
  can vary between tenants without recreating the limiter).
- Window expiry resets the count.
- Buckets are keyed by ``(tenant_id, session_id)`` — two sessions on the same
  tenant do not share a count.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.rate_limiter import LeadCaptureRateLimiter, lead_capture_rate_limiter


@pytest.mark.asyncio
async def test_default_cap_allows_five_then_rate_limits() -> None:
    limiter = LeadCaptureRateLimiter(default_cap=5, window_seconds=3600)
    tenant_id = uuid4()
    session_id = "session-A"

    for _ in range(5):
        assert await limiter.check_and_increment(tenant_id, session_id) is True
    assert await limiter.check_and_increment(tenant_id, session_id) is False


@pytest.mark.asyncio
async def test_per_call_cap_override_is_honored() -> None:
    limiter = LeadCaptureRateLimiter(default_cap=5)
    tenant_id = uuid4()
    session_id = "session-B"

    assert await limiter.check_and_increment(tenant_id, session_id, cap=2) is True
    assert await limiter.check_and_increment(tenant_id, session_id, cap=2) is True
    assert await limiter.check_and_increment(tenant_id, session_id, cap=2) is False


@pytest.mark.asyncio
async def test_distinct_sessions_have_independent_buckets() -> None:
    limiter = LeadCaptureRateLimiter(default_cap=1)
    tenant_id = uuid4()

    assert await limiter.check_and_increment(tenant_id, "sess-1") is True
    assert await limiter.check_and_increment(tenant_id, "sess-1") is False
    # Different session_id under the same tenant must not inherit the prior
    # session's count.
    assert await limiter.check_and_increment(tenant_id, "sess-2") is True


@pytest.mark.asyncio
async def test_window_expiry_resets_count(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = LeadCaptureRateLimiter(default_cap=2, window_seconds=60)
    tenant_id = uuid4()
    session_id = "session-D"

    # Freeze time, fill the bucket.
    fake_now = {"value": 1_000.0}

    def _fake_monotonic() -> float:
        return fake_now["value"]

    monkeypatch.setattr("app.services.rate_limiter.time.monotonic", _fake_monotonic)
    await limiter.reset(tenant_id, session_id)

    assert await limiter.check_and_increment(tenant_id, session_id) is True
    assert await limiter.check_and_increment(tenant_id, session_id) is True
    assert await limiter.check_and_increment(tenant_id, session_id) is False

    # Advance past the window — next call must be accepted.
    fake_now["value"] += 61.0
    assert await limiter.check_and_increment(tenant_id, session_id) is True


@pytest.mark.asyncio
async def test_singleton_returns_same_instance() -> None:
    a = lead_capture_rate_limiter()
    b = lead_capture_rate_limiter()
    assert a is b
