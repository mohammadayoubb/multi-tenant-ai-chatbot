# Owner: Hiba
"""Tests for FastAPI dependency safety behavior."""

import pytest
from fastapi import HTTPException

from app.api.deps import get_platform_actor, get_tenant_id_from_widget_token
from app.domain.tenant import PlatformRole


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
async def test_widget_token_dependency_refuses_placeholder_tenant() -> None:
    """Widget auth must not return a fake tenant before Amer's verifier exists."""
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_id_from_widget_token("Bearer token")

    assert exc_info.value.status_code == 501
