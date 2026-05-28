# Owner: Amer
"""Admin authentication service.

Two responsibilities:

- `authenticate`: verify email+password against the `admin_users` table and
  mint an HS256 JWT bound to (actor_id, tenant_id, role).
- `verify_admin_token`: decode an inbound Bearer JWT and return the trusted
  admin context — consumed by `require_tenant_admin` in app/api/deps.py.

The login path NEVER discloses whether the failure was "no such email" or
"wrong password" — both surface as `InvalidCredentials` so the route returns
a single 401 byte body.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import jwt

from app.domain.admin_auth import AdminLoginResponse
from app.infra.password import hash_password, verify_password
from app.repositories.admin_user_repo import AdminUserRepository
from app.services.admin_settings import admin_settings


class InvalidCredentials(Exception):
    """Login refused. The route maps every cause to the same 401 body."""


@dataclass(frozen=True)
class AdminSession:
    """Trusted admin context recovered from a verified JWT."""

    actor_id: str
    tenant_id: UUID
    role: str


_ALLOWED_LOGIN_ROLES = {"tenant_admin", "tenant_manager"}


async def authenticate(
    *,
    email: str,
    password: str,
    repo: AdminUserRepository,
) -> AdminLoginResponse:
    """Verify credentials and mint an admin JWT.

    Raises `InvalidCredentials` on any of: missing user, wrong password,
    suspended user, unknown role. The route maps every cause to the same 401
    response so an attacker can neither enumerate registered emails nor
    distinguish "wrong password" from "your account was suspended".
    """
    user = await repo.get_by_email(email.lower())
    if user is None:
        # Run a dummy verify against a fixed hash anyway so we don't leak a
        # timing signal that distinguishes "user exists" from "user missing".
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentials()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentials()

    if getattr(user, "status", "active") != "active":
        raise InvalidCredentials()
    if user.role not in _ALLOWED_LOGIN_ROLES:
        raise InvalidCredentials()

    settings = admin_settings()
    now = int(time.time())
    payload = {
        "actor_id": user.email,
        "tenant_id": str(user.tenant_id),
        "role": user.role,
        "iat": now,
        "exp": now + settings.admin_token_ttl_seconds,
    }
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")
    full_name = getattr(user, "full_name", None)
    return AdminLoginResponse(
        token=token,
        expires_in=settings.admin_token_ttl_seconds,
        actor_id=user.email,
        tenant_id=user.tenant_id,
        role=user.role,
        full_name=full_name,
    )


def verify_admin_token(token: str) -> AdminSession | None:
    """Decode + verify an admin JWT. Return None on any failure."""
    try:
        payload = jwt.decode(
            token,
            admin_settings().admin_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None
    raw_tenant = payload.get("tenant_id")
    actor_id = payload.get("actor_id")
    role = payload.get("role")
    if not isinstance(raw_tenant, str) or not isinstance(actor_id, str):
        return None
    if not isinstance(role, str) or role not in ("tenant_admin", "tenant_manager"):
        return None
    try:
        tenant_id = UUID(raw_tenant)
    except ValueError:
        return None
    return AdminSession(actor_id=actor_id, tenant_id=tenant_id, role=role)


# Generated once per process from a placeholder secret no caller ever supplies.
# Used solely to keep login timing constant when the email lookup misses, so an
# attacker can't probe for registered admin emails via response-time deltas.
_DUMMY_HASH = hash_password("__no-such-user-placeholder__")
