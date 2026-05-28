# Owner: Amer
"""Minimal tenant-admin signup/login service for the Streamlit admin app.

This is a local-development session layer for the existing admin product flow.
It issues short-lived signed bearer tokens that the backend can verify for
tenant-admin routes, replacing the raw header mock on the happy path.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.repositories.widget_repo import InMemoryWidgetRepository, WidgetRepository
from app.services.tenant_service import TenantService


class AdminAuthSettings(BaseSettings):
    """Environment-backed settings for admin session auth."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_auth_secret: str = (
        "dev-admin-auth-secret-cccccccccccccccccccccccccccccccccccc"
    )
    admin_auth_ttl_seconds: int = 43_200


@lru_cache(maxsize=1)
def admin_auth_settings() -> AdminAuthSettings:
    return AdminAuthSettings()


@dataclass(frozen=True)
class AdminSessionContext:
    """Trusted tenant-admin identity resolved from a signed session token."""

    tenant_id: UUID
    actor_id: str
    email: str
    tenant_name: str
    widget_id: UUID


@dataclass(frozen=True)
class AdminAccount:
    """Stored tenant-admin account for the local development auth flow."""

    email: str
    actor_id: str
    tenant_id: UUID
    tenant_name: str
    widget_id: UUID
    password_salt: str
    password_hash: str


class AdminAuthError(Exception):
    """Base error raised by the admin auth service."""


class AdminCredentialsError(AdminAuthError):
    """Raised when login credentials are invalid."""


class AdminEmailTakenError(AdminAuthError):
    """Raised when signup attempts to reuse an existing admin email."""


class AdminTokenError(AdminAuthError):
    """Raised when a bearer token is missing, invalid, or expired."""


class InMemoryAdminAccountRepository:
    """Simple process-scoped account store used by the dev admin auth flow."""

    def __init__(self) -> None:
        self._accounts_by_email: dict[str, AdminAccount] = {}

    def get_by_email(self, email: str) -> AdminAccount | None:
        return self._accounts_by_email.get(email)

    def create(self, account: AdminAccount) -> AdminAccount:
        self._accounts_by_email[account.email] = account
        return account

    def clear(self) -> None:
        self._accounts_by_email.clear()


@lru_cache(maxsize=1)
def get_admin_account_repository() -> InMemoryAdminAccountRepository:
    return InMemoryAdminAccountRepository()


@dataclass
class AdminAuthService:
    """Create and verify tenant-admin accounts plus signed session tokens."""

    accounts: InMemoryAdminAccountRepository
    widget_repo: WidgetRepository

    async def signup(
        self,
        *,
        business_name: str,
        email: str,
        password: str,
        tenant_service: TenantService,
    ) -> AdminSessionContext:
        normalized_email = _normalize_email(email)
        if self.accounts.get_by_email(normalized_email) is not None:
            raise AdminEmailTakenError("An account already exists for that email.")

        cleaned_business_name = business_name.strip()
        if not cleaned_business_name:
            raise AdminCredentialsError("Business name is required.")

        tenant = await tenant_service.create_tenant(cleaned_business_name)
        widget_row = await self._ensure_widget_row(tenant.id)

        salt = secrets.token_hex(16)
        account = AdminAccount(
            email=normalized_email,
            actor_id=normalized_email,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            widget_id=widget_row.widget_id,
            password_salt=salt,
            password_hash=_hash_password(password, salt),
        )
        self.accounts.create(account)
        return self._session_from_account(account)

    async def login(self, *, email: str, password: str) -> AdminSessionContext:
        normalized_email = _normalize_email(email)
        account = self.accounts.get_by_email(normalized_email)
        if account is None:
            raise AdminCredentialsError("Invalid email or password.")

        expected_hash = _hash_password(password, account.password_salt)
        if not hmac.compare_digest(expected_hash, account.password_hash):
            raise AdminCredentialsError("Invalid email or password.")

        return self._session_from_account(account)

    def issue_token(self, session: AdminSessionContext) -> str:
        now = int(time.time())
        ttl = admin_auth_settings().admin_auth_ttl_seconds
        payload = {
            "kind": "admin_session",
            "tenant_id": str(session.tenant_id),
            "actor_id": session.actor_id,
            "actor_role": "tenant_admin",
            "email": session.email,
            "tenant_name": session.tenant_name,
            "widget_id": str(session.widget_id),
            "iat": now,
            "exp": now + ttl,
        }
        return jwt.encode(
            payload,
            admin_auth_settings().admin_auth_secret,
            algorithm="HS256",
        )

    def verify_token(self, token: str) -> AdminSessionContext:
        try:
            claims = jwt.decode(
                token,
                admin_auth_settings().admin_auth_secret,
                algorithms=["HS256"],
                options={
                    "require": [
                        "kind",
                        "tenant_id",
                        "actor_id",
                        "actor_role",
                        "email",
                        "tenant_name",
                        "widget_id",
                        "iat",
                        "exp",
                    ]
                },
            )
        except ExpiredSignatureError as exc:
            raise AdminTokenError("Admin session expired.") from exc
        except InvalidTokenError as exc:
            raise AdminTokenError("Invalid admin session.") from exc

        if claims.get("kind") != "admin_session" or claims.get("actor_role") != "tenant_admin":
            raise AdminTokenError("Invalid admin session.")

        try:
            return AdminSessionContext(
                tenant_id=UUID(str(claims["tenant_id"])),
                actor_id=str(claims["actor_id"]),
                email=_normalize_email(str(claims["email"])),
                tenant_name=str(claims["tenant_name"]).strip(),
                widget_id=UUID(str(claims["widget_id"])),
            )
        except (TypeError, ValueError) as exc:
            raise AdminTokenError("Invalid admin session.") from exc

    async def _ensure_widget_row(self, tenant_id: UUID):
        if isinstance(self.widget_repo, InMemoryWidgetRepository):
            return await self.widget_repo.ensure_for_tenant(tenant_id)

        row = await self.widget_repo.get_by_tenant_id(tenant_id)
        if row is None:
            raise AdminAuthError("Tenant widget configuration is unavailable.")
        return row

    @staticmethod
    def _session_from_account(account: AdminAccount) -> AdminSessionContext:
        return AdminSessionContext(
            tenant_id=account.tenant_id,
            actor_id=account.actor_id,
            email=account.email,
            tenant_name=account.tenant_name,
            widget_id=account.widget_id,
        )


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise AdminCredentialsError("A valid email address is required.")
    return normalized[:255]


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()
