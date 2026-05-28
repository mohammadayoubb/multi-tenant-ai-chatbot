# Owner: Hiba
"""Tests for FastAPI dependency safety behavior."""

import time
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.api.deps import get_platform_actor, get_tenant_id_from_widget_token
from app.domain.tenant import PlatformRole
from app.services.widget_settings import widget_settings


@pytest.mark.asyncio
async def test_platform_actor_requires_trusted_headers() -> None:
    """Platform dependencies refuse missing actor context."""
    with pytest.raises(HTTPException) as exc_info:
        await get_platform_actor(actor_id=None, actor_role=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_platform_actor_validates_role() -> None:
    """Platform dependencies normalize known actor roles."""
    actor = await get_platform_actor(actor_id="hiba", actor_role="tenant_manager")

    assert actor.actor_id == "hiba"
    assert actor.actor_role is PlatformRole.TENANT_MANAGER


@pytest.mark.asyncio
async def test_widget_token_dependency_refuses_missing_header() -> None:
    """Missing Authorization header is a 401."""
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_id_from_widget_token(None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_widget_token_dependency_refuses_garbage_token() -> None:
    """Unsigned / unparseable tokens collapse to the same 401 as a missing header."""
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_id_from_widget_token("Bearer not-a-jwt")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_widget_token_dependency_refuses_wrong_secret() -> None:
    """A JWT signed with a foreign secret must not authenticate."""
    now = int(time.time())
    payload = {
        "tenant_id": str(uuid4()),
        "iat": now,
        "exp": now + 60,
    }
    token = jwt.encode(payload, "some-other-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_id_from_widget_token(f"Bearer {token}")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_widget_token_dependency_returns_tenant_id_on_valid_token() -> None:
    """A properly signed, unexpired token resolves to its tenant_id claim."""
    tenant_id = uuid4()
    now = int(time.time())
    payload = {
        "tenant_id": str(tenant_id),
        "widget_id": str(uuid4()),
        "origin": "https://customer-site.example",
        "session_id": str(uuid4()),
        "iat": now,
        "exp": now + 60,
    }
    token = jwt.encode(
        payload, widget_settings().widget_jwt_secret, algorithm="HS256"
    )
    resolved = await get_tenant_id_from_widget_token(f"Bearer {token}")
    assert resolved == tenant_id


@pytest.mark.asyncio
async def test_widget_token_dependency_refuses_expired_token() -> None:
    """Expired tokens must not authenticate."""
    now = int(time.time())
    payload = {
        "tenant_id": str(uuid4()),
        "iat": now - 120,
        "exp": now - 60,
    }
    token = jwt.encode(
        payload, widget_settings().widget_jwt_secret, algorithm="HS256"
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_id_from_widget_token(f"Bearer {token}")

    assert exc_info.value.status_code == 401
