# Owner: Hiba
"""Tests for FastAPI dependency safety behavior."""

import pytest
import jwt
from fastapi import HTTPException

import app.api.deps as deps
from app.domain.tenant import PlatformRole
from app.domain.widget import WidgetConfigDomain
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.admin_auth import AdminAuthService, AdminSessionContext, get_admin_account_repository
from app.services.widget_settings import widget_settings


@pytest.mark.asyncio
async def test_platform_actor_requires_trusted_headers() -> None:
    """Platform dependencies refuse missing actor context."""
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_platform_actor(actor_id=None, actor_role=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_platform_actor_validates_role() -> None:
    """Platform dependencies normalize known actor roles."""
    actor = await deps.get_platform_actor(actor_id="hiba", actor_role="tenant_manager")

    assert actor.actor_id == "hiba"
    assert actor.actor_role is PlatformRole.TENANT_MANAGER


def _mint_widget_token(
    *,
    tenant_id: str = "11111111-1111-1111-1111-111111111111",
    widget_id: str = "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d",
    origin: str = "http://localhost:5500",
    session_id: str = "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f",
    payload_overrides: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "tenant_id": tenant_id,
        "widget_id": widget_id,
        "origin": origin,
        "session_id": session_id,
        "iat": 1_700_000_000,
        "exp": 4_102_444_800,
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(
        payload,
        widget_settings().widget_jwt_secret,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_widget_token_dependency_returns_verified_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verified widget JWTs resolve to the owning tenant id."""
    repo = InMemoryWidgetRepository()
    monkeypatch.setattr(deps, "get_widget_repository", lambda: repo)

    tenant_id = await deps.get_tenant_id_from_widget_token(
        authorization=f"Bearer {_mint_widget_token()}",
        origin="http://localhost:5500",
    )

    assert str(tenant_id) == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_widget_token_dependency_requires_bearer_header() -> None:
    """Missing or malformed auth headers are rejected with 401."""
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_tenant_id_from_widget_token(authorization="token-only")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_widget_token_dependency_rejects_origin_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The request Origin must match the signed token origin."""
    repo = InMemoryWidgetRepository()
    monkeypatch.setattr(deps, "get_widget_repository", lambda: repo)

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_tenant_id_from_widget_token(
            authorization=f"Bearer {_mint_widget_token(origin='http://localhost:5500')}",
            origin="https://attacker.example",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_widget_token_dependency_rejects_unknown_widget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tokens for widget ids that no longer resolve are rejected."""
    repo = InMemoryWidgetRepository()
    repo.clear()
    monkeypatch.setattr(deps, "get_widget_repository", lambda: repo)

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_tenant_id_from_widget_token(
            authorization=f"Bearer {_mint_widget_token()}",
            origin="http://localhost:5500",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_widget_token_dependency_rejects_tenant_widget_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forged tenant/widget combinations are rejected even with a valid signature."""
    repo = InMemoryWidgetRepository()
    repo.upsert(
        WidgetConfigDomain(
            id=repo._FIXTURE_ROW_ID,
            tenant_id=repo._FIXTURE_TENANT_ID,
            widget_id=repo._FIXTURE_WIDGET_ID,
            allowed_origins=["http://localhost:5500"],
            enabled=True,
            tenant_status="active",
        )
    )
    monkeypatch.setattr(deps, "get_widget_repository", lambda: repo)

    forged_tenant = "22222222-2222-2222-2222-222222222222"
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_tenant_id_from_widget_token(
            authorization=f"Bearer {_mint_widget_token(tenant_id=forged_tenant)}",
            origin="http://localhost:5500",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_tenant_admin_accepts_signed_admin_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant-admin routes accept the new signed admin session token."""
    widget_repo = InMemoryWidgetRepository()
    monkeypatch.setattr(deps, "get_widget_repository", lambda: widget_repo)

    auth_service = AdminAuthService(
        accounts=get_admin_account_repository(),
        widget_repo=widget_repo,
    )
    session = AdminSessionContext(
        tenant_id=widget_repo._FIXTURE_TENANT_ID,
        actor_id="owner@example.com",
        email="owner@example.com",
        tenant_name="Acme",
        widget_id=widget_repo._FIXTURE_WIDGET_ID,
    )
    token = auth_service.issue_token(session)

    context = await deps.require_tenant_admin(authorization=f"Bearer {token}")

    assert context is not None
    assert context.actor_id == "owner@example.com"
    assert context.tenant_id == widget_repo._FIXTURE_TENANT_ID
