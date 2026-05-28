# Owner: Amer
"""Admin authentication route: POST /admin/login.

The login endpoint is intentionally minimal:
  - Validates the request body shape.
  - Calls AdminAuthService.authenticate; every failure (no such email, wrong
    password, malformed input) returns the same 401 body so an attacker cannot
    enumerate registered admin emails.
  - On success returns a JWT the Streamlit admin UI stores in st.session_state.

There is no signup, no password-reset, and no refresh. Admin users are seeded
via scripts/seed_admin.py; expired tokens require a fresh login.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.admin_auth import AdminLoginRequest
from app.repositories.admin_user_repo import AdminUserRepository
from app.services.admin_auth import InvalidCredentials, authenticate

router = APIRouter(prefix="/admin", tags=["admin-auth"])

_UNAUTHORIZED_BODY = b'{"error":"invalid_credentials"}'
_BAD_REQUEST_BODY = b'{"error":"bad_request"}'
_HEADERS = {"Cache-Control": "no-store", "Content-Type": "application/json"}


def _bytes_response(status: int, body: bytes) -> Response:
    return Response(status_code=status, content=body, headers=_HEADERS)


@router.post("/login")
async def login(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Verify email+password; on success return an HS256 admin JWT."""
    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _bytes_response(400, _BAD_REQUEST_BODY)

    try:
        body = AdminLoginRequest.model_validate(raw)
    except ValidationError:
        return _bytes_response(400, _BAD_REQUEST_BODY)

    repo = AdminUserRepository(session)
    try:
        response = await authenticate(
            email=body.email, password=body.password, repo=repo
        )
    except InvalidCredentials:
        return _bytes_response(401, _UNAUTHORIZED_BODY)

    payload = response.model_dump(mode="json")
    return Response(
        status_code=200,
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=_HEADERS,
    )
