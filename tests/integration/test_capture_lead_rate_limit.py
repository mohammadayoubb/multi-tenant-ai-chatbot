# Owner: Nasser
"""Integration test for ``capture_lead`` per-session rate limit (task T055).

Covers contract C-T2-4: 5 successive calls succeed, the 6th returns
``status="rate_limited"``, and a ``lead.rate_limited`` audit entry is
emitted. The cap is pulled from ``tenant_settings.rate_limit_lead_per_session``
when present, falling back to the default of 5.

The test stays in-process: it monkey-patches the LeadRepository, TenantRepository,
and `_resolve_lead_cap` seams so the DB is never touched. The rate-limit
behaviour under test lives in `app/agent/tools.py` + `app/services/rate_limiter.py`,
not in the DB layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

import app.agent.tools as tools_module
from app.agent.tools import capture_lead
from app.services.rate_limiter import LeadCaptureRateLimiter


@dataclass
class _FakeLead:
    id: UUID = field(default_factory=uuid4)


class _FakeLeadRepo:
    def __init__(self, session: Any) -> None:  # noqa: ARG002 — match real signature
        self.created: list[dict[str, Any]] = []

    async def create(self, *, tenant_id, name, contact, intent) -> _FakeLead:
        lead = _FakeLead()
        self.created.append(
            {"tenant_id": tenant_id, "name": name, "contact": contact, "intent": intent}
        )
        return lead


class _AuditCollector:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def make_repo(self, session: Any):  # noqa: ARG002 — match real signature
        collector = self

        class _FakeTenantRepo:
            async def add_audit_log(
                self_inner,
                *,
                tenant_id,
                actor_id,
                actor_role,
                action,
                metadata,
            ) -> None:
                collector.events.append(
                    {
                        "tenant_id": tenant_id,
                        "actor_id": actor_id,
                        "actor_role": actor_role,
                        "action": action,
                        "metadata": metadata,
                    }
                )

        return _FakeTenantRepo()


@pytest.fixture
def fake_session() -> object:
    """Opaque sentinel — the patched repos ignore it."""
    return object()


@pytest.fixture
def patched_tools(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeLeadRepo | None, _AuditCollector]:
    """Patch LeadRepository / TenantRepository / lead cap; return spy state."""
    created_repos: list[_FakeLeadRepo] = []
    collector = _AuditCollector()

    def _make_lead_repo(session):
        repo = _FakeLeadRepo(session)
        created_repos.append(repo)
        return repo

    monkeypatch.setattr(tools_module, "LeadRepository", _make_lead_repo)
    monkeypatch.setattr(tools_module, "TenantRepository", collector.make_repo)

    # Force a fresh per-process limiter so test ordering doesn't leak counts.
    fresh_limiter = LeadCaptureRateLimiter(default_cap=5)
    monkeypatch.setattr(
        tools_module, "lead_capture_rate_limiter", lambda: fresh_limiter
    )

    return created_repos, collector  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_default_cap_allows_five_then_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: object,
    patched_tools: tuple[list[_FakeLeadRepo], _AuditCollector],
) -> None:
    """5 successive calls succeed against default cap; the 6th rate-limits + audits."""
    created_repos, audits = patched_tools

    async def _no_db_cap(session, tenant_id):  # noqa: ARG001
        return 5

    monkeypatch.setattr(tools_module, "_resolve_lead_cap", _no_db_cap)

    tenant_id = uuid4()
    session_id = "session-rate-limit-A"

    for _ in range(5):
        result = await capture_lead(
            tenant_id=tenant_id,
            session_id=session_id,
            name=None,
            contact="visitor@example.com",
            intent="Wants pricing.",
            session=fake_session,
        )
        assert result["status"] == "captured", result

    sixth = await capture_lead(
        tenant_id=tenant_id,
        session_id=session_id,
        name=None,
        contact="visitor@example.com",
        intent="Wants pricing.",
        session=fake_session,
    )
    assert sixth["status"] == "rate_limited"
    assert sixth["session_id"] == session_id

    rate_limited_events = [e for e in audits.events if e["action"] == "lead.rate_limited"]
    assert len(rate_limited_events) == 1
    metadata = rate_limited_events[0]["metadata"]
    assert metadata["session_id"] == session_id
    assert metadata["count_in_window"] == 5

    # Verify only 5 real INSERTs happened — the rate-limited 6th did not hit the repo.
    insert_count = sum(len(repo.created) for repo in created_repos)
    assert insert_count == 5


@pytest.mark.asyncio
async def test_cap_pulled_from_tenant_settings(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: object,
    patched_tools: tuple[list[_FakeLeadRepo], _AuditCollector],
) -> None:
    """A tenant-specific cap of 2 overrides the default of 5."""
    _created_repos, audits = patched_tools

    async def _tenant_cap_of_two(session, tenant_id):  # noqa: ARG001
        return 2

    monkeypatch.setattr(tools_module, "_resolve_lead_cap", _tenant_cap_of_two)

    tenant_id = uuid4()
    session_id = "session-rate-limit-B"

    assert (
        await capture_lead(
            tenant_id=tenant_id,
            session_id=session_id,
            name=None,
            contact=None,
            intent="hi 1",
            session=fake_session,
        )
    )["status"] == "captured"
    assert (
        await capture_lead(
            tenant_id=tenant_id,
            session_id=session_id,
            name=None,
            contact=None,
            intent="hi 2",
            session=fake_session,
        )
    )["status"] == "captured"
    third = await capture_lead(
        tenant_id=tenant_id,
        session_id=session_id,
        name=None,
        contact=None,
        intent="hi 3",
        session=fake_session,
    )
    assert third["status"] == "rate_limited"
    assert third["session_id"] == session_id

    rate_limited_events = [e for e in audits.events if e["action"] == "lead.rate_limited"]
    assert len(rate_limited_events) == 1
    assert rate_limited_events[0]["metadata"]["count_in_window"] == 2


@pytest.mark.asyncio
async def test_distinct_sessions_have_independent_buckets(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: object,
    patched_tools: tuple[list[_FakeLeadRepo], _AuditCollector],
) -> None:
    """One session reaching the cap must not affect another session on the same tenant."""
    _created_repos, _audits = patched_tools

    async def _cap_of_one(session, tenant_id):  # noqa: ARG001
        return 1

    monkeypatch.setattr(tools_module, "_resolve_lead_cap", _cap_of_one)

    tenant_id = uuid4()

    first = await capture_lead(
        tenant_id=tenant_id,
        session_id="sess-X",
        name=None,
        contact=None,
        intent="hello",
        session=fake_session,
    )
    assert first["status"] == "captured"

    blocked = await capture_lead(
        tenant_id=tenant_id,
        session_id="sess-X",
        name=None,
        contact=None,
        intent="hello again",
        session=fake_session,
    )
    assert blocked["status"] == "rate_limited"

    fresh = await capture_lead(
        tenant_id=tenant_id,
        session_id="sess-Y",
        name=None,
        contact=None,
        intent="hello from another session",
        session=fake_session,
    )
    assert fresh["status"] == "captured"
