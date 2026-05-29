# Owner: Nasser
"""Redis cache and short-term memory helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.infra.redaction import redact_text


class MemoryUnavailableError(RuntimeError):
    """Redis-backed session memory could not be reached on this operation."""


@dataclass(frozen=True)
class MemoryMessage:
    """One redacted chat memory entry."""

    role: str
    content: str
    created_at: str


class SessionMemory:
    """Redis-backed short-term session memory adapter.

    Keys are scoped by tenant and session to prevent cross-tenant/session mixups:
    session:{tenant_id}:{session_id}

    Memory is useful but non-critical. If Redis is unavailable, chat continues
    without memory instead of failing the visitor turn.
    """

    def __init__(
        self,
        redis_client: Redis[str] | None = None,
        ttl_seconds: int | None = None,
        max_messages: int = 12,
    ) -> None:
        try:
            from app import config as app_config

            if hasattr(app_config, "get_app_secrets"):
                secrets = app_config.get_app_secrets()
                redis_url = secrets.redis_url
                default_ttl_seconds = secrets.session_memory_ttl_seconds
            else:
                settings = get_settings()
                redis_url = settings.redis_url
                default_ttl_seconds = settings.session_memory_ttl_seconds
        except Exception:
            redis_url = "redis://localhost:6379"
            default_ttl_seconds = 1800

        self._redis = redis_client or Redis.from_url(
            redis_url,
            decode_responses=True,
        )
        self._ttl_seconds = ttl_seconds or default_ttl_seconds
        self._max_messages = max_messages

    async def append_message(
        self,
        tenant_id: int,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """Append a redacted message to Redis session memory."""

        key = self.key_for(tenant_id, session_id)
        message = MemoryMessage(
            role=role,
            content=redact_text(content),
            created_at=datetime.now(tz=UTC).isoformat(),
        )

        try:
            await self._redis.rpush(key, json.dumps(message.__dict__))
            await self._redis.ltrim(key, -self._max_messages, -1)
            await self._redis.expire(key, self._ttl_seconds)
        except RedisError as exc:
            raise MemoryUnavailableError(str(exc)) from exc

    async def get_messages(self, tenant_id: int, session_id: str) -> list[MemoryMessage]:
        """Return recent redacted messages for one tenant-scoped session."""

        key = self.key_for(tenant_id, session_id)

        try:
            raw_items = await self._redis.lrange(key, 0, -1)
        except RedisError as exc:
            raise MemoryUnavailableError(str(exc)) from exc

        messages: list[MemoryMessage] = []
        for item in raw_items:
            try:
                data: dict[str, Any] = json.loads(item)
                messages.append(
                    MemoryMessage(
                        role=str(data["role"]),
                        content=str(data["content"]),
                        created_at=str(data["created_at"]),
                    )
                )
            except (KeyError, TypeError, json.JSONDecodeError):
                continue

        return messages

    @staticmethod
    def key_for(tenant_id: int, session_id: str) -> str:
        """Build the contract-required Redis memory key."""

        safe_session_id = _safe_key_part(session_id)
        return f"session:{tenant_id}:{safe_session_id}"


def _safe_key_part(value: str) -> str:
    """Return a Redis-key-safe identifier fragment."""

    cleaned = value.strip()
    if not cleaned:
        return "anonymous"

    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", cleaned)