# Owner: Amer
"""Settings for admin authentication (mirrors widget_settings pattern).

Required env vars (defaulted for local pytest runs so the suite boots
without any wiring):

    ADMIN_JWT_SECRET           HS256 signing key (32+ bytes). REQUIRED in prod.
    ADMIN_TOKEN_TTL_SECONDS    Admin session lifetime in seconds (default 28800
                               = 8h). Re-login required after expiry; no refresh.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_jwt_secret: str = (
        "dev-only-do-not-ship-admin-cccccccccccccccccccccccccc"
    )
    admin_token_ttl_seconds: int = 28800  # 8 hours


@lru_cache(maxsize=1)
def admin_settings() -> AdminSettings:
    return AdminSettings()
