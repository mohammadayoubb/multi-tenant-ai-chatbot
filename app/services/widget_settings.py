# Owner: Amer
"""Feature-scoped settings for the widget token exchange feature.

The platform-wide `app/config.py` is owned by Hiba and is intentionally NOT
modified by this feature. Widget-specific environment variables live here.

Required env vars (to be added to `.env.example` in a follow-up by Hiba):

    WIDGET_JWT_SECRET        HS256 signing key (32+ bytes). REQUIRED in prod.
                             Vault-backed value will replace the env var
                             in a separate feature owned by Ayoub.
    WIDGET_LOG_SALT          HMAC salt for hashed log identifiers
                             (FR-020, FR-021). REQUIRED in prod.
    WIDGET_TOKEN_TTL_SECONDS Token lifetime in seconds (default 900 = 15 min,
                             FR-009; runtime-configurable per FR-018).
    WIDGET_RATE_PER_IP       Per-IP token requests per minute (default 10,
                             FR-015).
    WIDGET_RATE_PER_WIDGET   Per-widget token requests per minute (default 60,
                             FR-016).
    WIDGET_REPO_BACKEND      "memory" (default) or "sql". The in-memory backend
                             is a temporary affordance per plan.md Complexity
                             Tracking row 2; flip to "sql" once Hiba's
                             widget_configs migration is merged.

Dev defaults exist so local pytest runs succeed without env wiring.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class WidgetSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    widget_jwt_secret: str = (
        "dev-only-do-not-ship-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    widget_log_salt: str = (
        "dev-only-salt-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    widget_token_ttl_seconds: int = 900
    widget_rate_per_ip: int = 10
    widget_rate_per_widget: int = 60
    widget_repo_backend: Literal["memory", "sql"] = "memory"


@lru_cache(maxsize=1)
def widget_settings() -> WidgetSettings:
    return WidgetSettings()
