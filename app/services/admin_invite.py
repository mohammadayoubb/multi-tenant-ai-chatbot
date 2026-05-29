# Owner: Amer
"""Admin invite service.

Three operations, all small enough to keep in one module:

- `create_invite`: called by an authenticated admin. The inviter's tenant_id
  and role come from THEIR JWT; the request body cannot override them. The
  invite carries the same tenant_id and a server-validated role.
- `get_invite_details`: returns safe public metadata for the acceptance page.
  Distinguishes "pending / used / expired" but never reveals invited_by,
  tenant_id, or any other field that could fingerprint the platform.
- `accept_invite`: validates the token + password rules, creates the
  admin_user row using tenant_id/role/email FROM THE INVITE, marks the invite
  used. Raises `InviteUnavailable` for every refusal cause so the route layer
  can collapse them to one canonical 400 body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.db.models import AdminInvite, AdminUser
from app.domain.admin_invite import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    InviteDetailsResponse,
)
from app.infra.password import hash_password
from app.repositories.admin_invite_repo import AdminInviteRepository
from app.repositories.admin_user_repo import AdminUserRepository
from app.repositories.tenant_repo import TenantRepository


class InviteUnavailable(Exception):
    """The invite cannot be acted on (expired / used / unknown / bad input)."""


class InviteForbidden(Exception):
    """Caller is not allowed to act on this invite (cross-tenant)."""


class InviteConflict(Exception):
    """Invite is already used or already revoked — refuse with 409."""


class WeakPassword(Exception):
    """Password failed strength check. Surfaced separately so the UI can hint."""


@dataclass(frozen=True)
class _PasswordRule:
    pattern: re.Pattern[str]
    hint: str


_PASSWORD_RULES: tuple[_PasswordRule, ...] = (
    _PasswordRule(re.compile(r"[A-Za-z]"), "include at least one letter"),
    _PasswordRule(re.compile(r"\d"), "include at least one digit"),
)


def _check_password_strength(password: str) -> None:
    """Minimum-bar password validation. Bcrypt truncates at 72 bytes so we cap
    here to keep behavior predictable; pydantic enforces the 8-char floor."""
    if len(password) > 72:
        raise WeakPassword("password must be 72 characters or fewer")
    for rule in _PASSWORD_RULES:
        if not rule.pattern.search(password):
            raise WeakPassword(f"password must {rule.hint}")


async def create_invite(
    *,
    request: InviteCreateRequest,
    inviter_tenant_id: UUID,
    inviter_actor_id: str,
    repo: AdminInviteRepository,
) -> InviteCreateResponse:
    """Mint a new single-use invite token scoped to the inviter's tenant."""
    token = uuid4()
    expires_at = datetime.now(tz=UTC) + timedelta(seconds=request.ttl_seconds)
    invite = await repo.create(
        token=token,
        tenant_id=inviter_tenant_id,
        email=str(request.email).lower(),
        role=request.role,
        invited_by=inviter_actor_id,
        expires_at=expires_at,
    )
    return InviteCreateResponse(
        token=invite.token,
        email=invite.email,
        role=invite.role,  # type: ignore[arg-type]
        tenant_id=invite.tenant_id,
        expires_at=invite.expires_at,
    )


async def get_invite_details(
    *,
    token: UUID,
    invite_repo: AdminInviteRepository,
    tenant_repo: TenantRepository,
) -> InviteDetailsResponse:
    """Return safe public metadata for the acceptance page."""
    invite = await invite_repo.get_by_token(token)
    if invite is None:
        raise InviteUnavailable("unknown")
    tenant = await tenant_repo.get_by_id(invite.tenant_id)
    if tenant is None:
        raise InviteUnavailable("unknown")

    status = _invite_status(invite)
    return InviteDetailsResponse(
        email=invite.email,
        role=invite.role,  # type: ignore[arg-type]
        tenant_name=tenant.name,
        expires_at=invite.expires_at,
        status=status,
    )


async def accept_invite(
    *,
    token: UUID,
    request: InviteAcceptRequest,
    invite_repo: AdminInviteRepository,
    user_repo: AdminUserRepository,
) -> AdminUser:
    """Validate + redeem the invite. Returns the freshly created admin user."""
    if request.password != request.confirm_password:
        raise InviteUnavailable("password_mismatch")
    _check_password_strength(request.password)

    invite = await invite_repo.get_by_token(token)
    if invite is None or _invite_status(invite) != "pending":
        raise InviteUnavailable("unavailable")

    # Email uniqueness is enforced at the DB layer; check first so we can
    # surface a clean error instead of a constraint violation.
    existing = await user_repo.get_by_email(invite.email)
    if existing is not None:
        raise InviteUnavailable("already_registered")

    user = await user_repo.create(
        tenant_id=invite.tenant_id,
        email=invite.email,
        password_hash=hash_password(request.password),
        role=invite.role,
    )
    user.full_name = request.full_name.strip()
    await invite_repo.mark_used(invite, used_at=datetime.now(tz=UTC))
    return user


def _invite_status(invite: AdminInvite) -> str:
    """Compute the live status (used / revoked / expired / pending) of an invite row."""
    if invite.used_at is not None:
        return "used"
    if getattr(invite, "revoked_at", None) is not None:
        return "revoked"
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(tz=UTC):
        return "expired"
    return "pending"


@dataclass(frozen=True)
class InviteActor:
    """Trusted actor context for invite mutations."""

    tenant_id: UUID
    actor_id: str
    role: str  # "tenant_admin" or "tenant_manager"


async def revoke_invite(
    *,
    token: UUID,
    actor: InviteActor,
    invite_repo: AdminInviteRepository,
    tenant_repo: TenantRepository,
) -> AdminInvite:
    """Mark an invite revoked. Raises InviteUnavailable / InviteForbidden / InviteConflict."""
    invite = await invite_repo.get_by_token(token)
    if invite is None:
        raise InviteUnavailable("unknown")
    _require_actor_scope(invite, actor)
    status = _invite_status(invite)
    if status == "used":
        raise InviteConflict("already_used")
    if status == "revoked":
        raise InviteConflict("already_revoked")
    revoked = await invite_repo.mark_revoked(token, revoked_at=datetime.now(tz=UTC))
    assert revoked is not None  # repo returned the row we just fetched
    await tenant_repo.add_audit_log(
        tenant_id=invite.tenant_id,
        actor_id=actor.actor_id,
        actor_role=actor.role,
        action="admin.invite_revoked",
        metadata={"invite_id": str(invite.id), "email": invite.email},
    )
    return revoked


async def resend_invite(
    *,
    token: UUID,
    actor: InviteActor,
    invite_repo: AdminInviteRepository,
    tenant_repo: TenantRepository,
    ttl_seconds: int = 86400 * 7,
) -> AdminInvite:
    """Re-mint the invite's token + extend expires_at. Refuses used/revoked rows."""
    invite = await invite_repo.get_by_token(token)
    if invite is None:
        raise InviteUnavailable("unknown")
    _require_actor_scope(invite, actor)
    status = _invite_status(invite)
    if status == "used":
        raise InviteConflict("already_used")
    if status == "revoked":
        raise InviteConflict("already_revoked")
    new_token = uuid4()
    new_expires_at = datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds)
    resent = await invite_repo.resend(
        token, new_token=new_token, new_expires_at=new_expires_at
    )
    assert resent is not None
    await tenant_repo.add_audit_log(
        tenant_id=invite.tenant_id,
        actor_id=actor.actor_id,
        actor_role=actor.role,
        action="admin.invite_resent",
        metadata={"invite_id": str(invite.id), "email": invite.email},
    )
    return resent


def _require_actor_scope(invite: AdminInvite, actor: InviteActor) -> None:
    """Tenant manager may act on any tenant; tenant admin only on own."""
    if actor.role == "tenant_manager":
        return
    if invite.tenant_id != actor.tenant_id:
        raise InviteForbidden("cross_tenant")
