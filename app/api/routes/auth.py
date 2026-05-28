# Owner: Amer
"""Tenant-admin signup and login routes for the Streamlit admin app."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_tenant_service
from app.repositories.widget_repo import get_widget_repository
from app.services.admin_auth import (
    AdminAuthError,
    AdminAuthService,
    AdminCredentialsError,
    AdminEmailTakenError,
    AdminSessionContext,
    AdminTokenError,
    get_admin_account_repository,
)
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class AdminSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    tenant_name: str
    actor_id: str
    widget_id: str


def _auth_service() -> AdminAuthService:
    return AdminAuthService(
        accounts=get_admin_account_repository(),
        widget_repo=get_widget_repository(),
    )


def _response_from_session(
    service: AdminAuthService,
    session: AdminSessionContext,
) -> AdminSessionResponse:
    return AdminSessionResponse(
        access_token=service.issue_token(session),
        tenant_id=str(session.tenant_id),
        tenant_name=session.tenant_name,
        actor_id=session.actor_id,
        widget_id=str(session.widget_id),
    )


@router.post("/signup", response_model=AdminSessionResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignupRequest,
    tenant_service: Annotated[TenantService, Depends(get_tenant_service)],
) -> AdminSessionResponse:
    """Create a tenant-admin account and provision its tenant."""
    service = _auth_service()
    try:
        session = await service.signup(
            business_name=request.business_name,
            email=request.email,
            password=request.password,
            tenant_service=tenant_service,
        )
    except AdminEmailTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdminCredentialsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _response_from_session(service, session)


@router.post("/login", response_model=AdminSessionResponse)
async def login(request: LoginRequest) -> AdminSessionResponse:
    """Authenticate an existing tenant-admin account."""
    service = _auth_service()
    try:
        session = await service.login(email=request.email, password=request.password)
    except AdminCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _response_from_session(service, session)


@router.get("/me", response_model=AdminSessionResponse)
async def me(
    authorization: Annotated[str | None, Header()] = None,
) -> AdminSessionResponse:
    """Return the current tenant-admin session if the bearer token is valid."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing admin session.")

    scheme, _, raw_token = authorization.partition(" ")
    token = raw_token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid admin session.")

    service = _auth_service()
    try:
        session = service.verify_token(token)
    except AdminTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _response_from_session(service, session)
