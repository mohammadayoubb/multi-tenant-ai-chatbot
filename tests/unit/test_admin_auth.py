# Owner: Amer
"""Unit tests for admin authentication infra + service.

Covers:
  - password hash round-trip + wrong-password rejection
  - JWT issue + verify happy path
  - JWT verify rejects: wrong secret, expired, missing tenant_id, bad role
  - authenticate() raises InvalidCredentials for missing email AND wrong password
    (must NOT distinguish — collapsing failure modes prevents enumeration).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

import jwt
import pytest

from app.infra.password import hash_password, verify_password
from app.services.admin_auth import (
    InvalidCredentials,
    authenticate,
    verify_admin_token,
)
from app.services.admin_settings import admin_settings


# --- password hashing ---


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_password_hash_rejects_wrong_password() -> None:
    h = hash_password("right one")
    assert verify_password("wrong one", h) is False


def test_password_verify_returns_false_on_malformed_hash() -> None:
    """Defensive: callers should never need a try/except around verify_password."""
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# --- JWT verify ---


def _mint(tenant_id: UUID, *, role: str = "tenant_admin", exp_offset: int = 60) -> str:
    now = int(time.time())
    payload = {
        "actor_id": "admin@example.com",
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, admin_settings().admin_jwt_secret, algorithm="HS256")


def test_verify_admin_token_returns_session_on_valid_token() -> None:
    tenant = uuid4()
    token = _mint(tenant)
    session = verify_admin_token(token)
    assert session is not None
    assert session.tenant_id == tenant
    assert session.actor_id == "admin@example.com"
    assert session.role == "tenant_admin"


def test_verify_admin_token_rejects_wrong_secret() -> None:
    now = int(time.time())
    token = jwt.encode(
        {
            "actor_id": "x",
            "tenant_id": str(uuid4()),
            "role": "tenant_admin",
            "iat": now,
            "exp": now + 60,
        },
        "totally-different-secret",
        algorithm="HS256",
    )
    assert verify_admin_token(token) is None


def test_verify_admin_token_rejects_expired() -> None:
    assert verify_admin_token(_mint(uuid4(), exp_offset=-1)) is None


def test_verify_admin_token_rejects_unknown_role() -> None:
    assert verify_admin_token(_mint(uuid4(), role="visitor")) is None


def test_verify_admin_token_rejects_malformed_tenant_id() -> None:
    now = int(time.time())
    token = jwt.encode(
        {
            "actor_id": "x",
            "tenant_id": "not-a-uuid",
            "role": "tenant_admin",
            "iat": now,
            "exp": now + 60,
        },
        admin_settings().admin_jwt_secret,
        algorithm="HS256",
    )
    assert verify_admin_token(token) is None


# --- authenticate() ---


@dataclass
class _FakeAdminUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"


class _FakeRepo:
    """In-memory AdminUserRepository stand-in keyed by email."""

    def __init__(self, users: list[_FakeAdminUser]) -> None:
        self._by_email = {u.email: u for u in users}

    async def get_by_email(self, email: str) -> _FakeAdminUser | None:
        return self._by_email.get(email)


@pytest.mark.asyncio
async def test_authenticate_issues_token_on_correct_credentials() -> None:
    tenant = uuid4()
    user = _FakeAdminUser(
        id=uuid4(),
        tenant_id=tenant,
        email="alice@acme.example",
        password_hash=hash_password("s3cret-pw"),
    )
    repo = _FakeRepo([user])
    resp = await authenticate(
        email="alice@acme.example", password="s3cret-pw", repo=repo
    )
    assert resp.tenant_id == tenant
    assert resp.actor_id == "alice@acme.example"
    assert resp.role == "tenant_admin"
    assert resp.expires_in > 0
    # Token must verify back to the same session.
    session = verify_admin_token(resp.token)
    assert session is not None
    assert session.tenant_id == tenant


@pytest.mark.asyncio
async def test_authenticate_raises_on_wrong_password() -> None:
    user = _FakeAdminUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="alice@acme.example",
        password_hash=hash_password("real-pw"),
    )
    repo = _FakeRepo([user])
    with pytest.raises(InvalidCredentials):
        await authenticate(
            email="alice@acme.example", password="WRONG", repo=repo
        )


@pytest.mark.asyncio
async def test_authenticate_raises_on_missing_email_same_exception() -> None:
    """Missing user must raise the SAME exception as wrong password.

    The route layer maps both to the same 401 body — verifying here that the
    service does not leak the distinction earlier in the stack.
    """
    repo = _FakeRepo([])
    with pytest.raises(InvalidCredentials):
        await authenticate(
            email="nobody@example.com", password="anything", repo=repo
        )
