# Owner: Amer
"""Unit tests for app.services.admin_invite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.domain.admin_invite import (
    InviteAcceptRequest,
    InviteCreateRequest,
)
from app.services.admin_invite import (
    InviteUnavailable,
    WeakPassword,
    accept_invite,
    create_invite,
    get_invite_details,
)


# --- in-memory fakes --------------------------------------------------------


@dataclass
class _FakeInvite:
    id: UUID
    token: UUID
    tenant_id: UUID
    email: str
    role: str
    invited_by: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class _FakeAdminUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None


@dataclass
class _FakeTenant:
    id: UUID
    name: str


class _FakeInviteRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeInvite] = {}

    async def create(self, **kwargs) -> _FakeInvite:
        invite = _FakeInvite(id=uuid4(), **kwargs)
        self.rows[invite.token] = invite
        return invite

    async def get_by_token(self, token: UUID) -> _FakeInvite | None:
        return self.rows.get(token)

    async def mark_used(self, invite: _FakeInvite, *, used_at: datetime) -> None:
        invite.used_at = used_at


class _FakeUserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeAdminUser] = {}

    async def get_by_email(self, email: str) -> _FakeAdminUser | None:
        return self.by_email.get(email)

    async def create(
        self, *, tenant_id: UUID, email: str, password_hash: str, role: str = "tenant_admin"
    ) -> _FakeAdminUser:
        user = _FakeAdminUser(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self.by_email[email] = user
        return user


class _FakeTenantRepo:
    def __init__(self, tenants: list[_FakeTenant]) -> None:
        self._by_id = {t.id: t for t in tenants}

    async def get_by_id(self, tenant_id: UUID) -> _FakeTenant | None:
        return self._by_id.get(tenant_id)


# --- create_invite ----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_invite_pulls_tenant_from_inviter_not_body() -> None:
    """tenant_id comes from the inviter's JWT context, not the request body."""
    repo = _FakeInviteRepo()
    inviter_tenant = uuid4()
    request = InviteCreateRequest(email="newbie@acme.example", role="tenant_admin")

    response = await create_invite(
        request=request,
        inviter_tenant_id=inviter_tenant,
        inviter_actor_id="boss@acme.example",
        repo=repo,
    )

    assert response.tenant_id == inviter_tenant
    assert response.email == "newbie@acme.example"
    assert response.role == "tenant_admin"
    stored = repo.rows[response.token]
    assert stored.tenant_id == inviter_tenant
    assert stored.invited_by == "boss@acme.example"


# --- get_invite_details -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_invite_details_returns_safe_metadata_for_pending() -> None:
    tenant = _FakeTenant(id=uuid4(), name="Acme Inc.")
    invite_repo = _FakeInviteRepo()
    token = uuid4()
    invite_repo.rows[token] = _FakeInvite(
        id=uuid4(),
        token=token,
        tenant_id=tenant.id,
        email="newbie@acme.example",
        role="tenant_admin",
        invited_by="boss@acme.example",
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
    )

    details = await get_invite_details(
        token=token,
        invite_repo=invite_repo,
        tenant_repo=_FakeTenantRepo([tenant]),
    )

    assert details.email == "newbie@acme.example"
    assert details.tenant_name == "Acme Inc."
    assert details.role == "tenant_admin"
    assert details.status == "pending"


@pytest.mark.asyncio
async def test_get_invite_details_marks_expired_when_past_ttl() -> None:
    tenant = _FakeTenant(id=uuid4(), name="Acme Inc.")
    invite_repo = _FakeInviteRepo()
    token = uuid4()
    invite_repo.rows[token] = _FakeInvite(
        id=uuid4(),
        token=token,
        tenant_id=tenant.id,
        email="newbie@acme.example",
        role="tenant_admin",
        invited_by="boss@acme.example",
        expires_at=datetime.now(tz=UTC) - timedelta(seconds=1),
    )

    details = await get_invite_details(
        token=token,
        invite_repo=invite_repo,
        tenant_repo=_FakeTenantRepo([tenant]),
    )
    assert details.status == "expired"


@pytest.mark.asyncio
async def test_get_invite_details_marks_used_when_already_redeemed() -> None:
    tenant = _FakeTenant(id=uuid4(), name="Acme Inc.")
    invite_repo = _FakeInviteRepo()
    token = uuid4()
    invite_repo.rows[token] = _FakeInvite(
        id=uuid4(),
        token=token,
        tenant_id=tenant.id,
        email="newbie@acme.example",
        role="tenant_admin",
        invited_by="boss@acme.example",
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
        used_at=datetime.now(tz=UTC),
    )

    details = await get_invite_details(
        token=token,
        invite_repo=invite_repo,
        tenant_repo=_FakeTenantRepo([tenant]),
    )
    assert details.status == "used"


@pytest.mark.asyncio
async def test_get_invite_details_unknown_token_raises_unavailable() -> None:
    with pytest.raises(InviteUnavailable):
        await get_invite_details(
            token=uuid4(),
            invite_repo=_FakeInviteRepo(),
            tenant_repo=_FakeTenantRepo([]),
        )


# --- accept_invite ----------------------------------------------------------


def _seeded_pending_invite() -> tuple[_FakeInviteRepo, UUID, UUID]:
    tenant_id = uuid4()
    invite_repo = _FakeInviteRepo()
    token = uuid4()
    invite_repo.rows[token] = _FakeInvite(
        id=uuid4(),
        token=token,
        tenant_id=tenant_id,
        email="newbie@acme.example",
        role="tenant_admin",
        invited_by="boss@acme.example",
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
    )
    return invite_repo, token, tenant_id


@pytest.mark.asyncio
async def test_accept_invite_creates_user_from_invite_fields() -> None:
    """tenant_id, role, email come from the invite row — never from the body."""
    invite_repo, token, tenant_id = _seeded_pending_invite()
    user_repo = _FakeUserRepo()

    user = await accept_invite(
        token=token,
        request=InviteAcceptRequest(
            full_name="New B.",
            password="hunter2letter",
            confirm_password="hunter2letter",
        ),
        invite_repo=invite_repo,
        user_repo=user_repo,
    )

    assert user.tenant_id == tenant_id
    assert user.email == "newbie@acme.example"
    assert user.role == "tenant_admin"
    assert user.full_name == "New B."
    # Invite is consumed (single-use).
    assert invite_repo.rows[token].used_at is not None


@pytest.mark.asyncio
async def test_accept_invite_rejects_password_mismatch() -> None:
    invite_repo, token, _ = _seeded_pending_invite()
    with pytest.raises(InviteUnavailable):
        await accept_invite(
            token=token,
            request=InviteAcceptRequest(
                full_name="x",
                password="hunter2letter",
                confirm_password="something-else1",
            ),
            invite_repo=invite_repo,
            user_repo=_FakeUserRepo(),
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_weak_password() -> None:
    invite_repo, token, _ = _seeded_pending_invite()
    with pytest.raises(WeakPassword):
        await accept_invite(
            token=token,
            request=InviteAcceptRequest(
                full_name="x",
                password="alllettersnodigit",
                confirm_password="alllettersnodigit",
            ),
            invite_repo=invite_repo,
            user_repo=_FakeUserRepo(),
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_used_invite() -> None:
    invite_repo, token, _ = _seeded_pending_invite()
    invite_repo.rows[token].used_at = datetime.now(tz=UTC)
    with pytest.raises(InviteUnavailable):
        await accept_invite(
            token=token,
            request=InviteAcceptRequest(
                full_name="x",
                password="hunter2letter",
                confirm_password="hunter2letter",
            ),
            invite_repo=invite_repo,
            user_repo=_FakeUserRepo(),
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_expired_invite() -> None:
    invite_repo, token, _ = _seeded_pending_invite()
    invite_repo.rows[token].expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    with pytest.raises(InviteUnavailable):
        await accept_invite(
            token=token,
            request=InviteAcceptRequest(
                full_name="x",
                password="hunter2letter",
                confirm_password="hunter2letter",
            ),
            invite_repo=invite_repo,
            user_repo=_FakeUserRepo(),
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_already_registered_email() -> None:
    invite_repo, token, tenant_id = _seeded_pending_invite()
    user_repo = _FakeUserRepo()
    user_repo.by_email["newbie@acme.example"] = _FakeAdminUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="newbie@acme.example",
        password_hash="anything",
    )
    with pytest.raises(InviteUnavailable):
        await accept_invite(
            token=token,
            request=InviteAcceptRequest(
                full_name="x",
                password="hunter2letter",
                confirm_password="hunter2letter",
            ),
            invite_repo=invite_repo,
            user_repo=user_repo,
        )
