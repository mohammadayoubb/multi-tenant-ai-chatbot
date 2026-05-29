# Owner: Nasser
"""Groq Cloud client for the Track-2 agent loop.

DECISION 19b (revised) selects Groq (`llama-3.3-70b-versatile`) as the live
LLM provider for the bounded tool-calling agent. The API key is resolved
through Vault (`secret/data/llm/groq_api_key`) with an env-var fallback for
local development so unit tests don't require Vault.

The client is intentionally a thin wrapper. The agent loop owns the policy
(iteration / token caps, tool-arg validation, audit emission); this module
only knows how to *call* Groq.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

try:
    from groq import AsyncGroq
except ImportError:  # pragma: no cover - optional at import time
    AsyncGroq = None  # type: ignore[assignment]


_log = logging.getLogger(__name__)

GROQ_AGENT_MODEL = "llama-3.3-70b-versatile"


class GroqUnavailable(RuntimeError):
    """No Groq client could be constructed (missing key or SDK)."""


@dataclass(frozen=True)
class GroqCompletion:
    """Minimal projection of one Groq chat-completion response.

    The agent loop never needs the full SDK object — only the assistant
    message and usage. Keeping the projection narrow makes tests easier
    (no need to construct an entire SDK type).
    """

    message: Any
    total_tokens: int


class GroqAgentClient:
    """Async tool-calling client for the agent loop."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = GROQ_AGENT_MODEL,
        max_response_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> None:
        if AsyncGroq is None:
            raise GroqUnavailable("groq SDK is not installed")
        resolved_key = api_key or _resolve_groq_api_key()
        if not resolved_key:
            raise GroqUnavailable("no Groq API key available (Vault or GROQ_API_KEY)")
        self._client = AsyncGroq(api_key=resolved_key)
        self._model = model
        self._max_response_tokens = max_response_tokens
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> GroqCompletion:
        """Call Groq chat-completions with tool_choice='auto' and return the
        assistant message + total tokens used."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=self._max_response_tokens,
            temperature=self._temperature,
        )
        usage = getattr(response, "usage", None)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return GroqCompletion(
            message=response.choices[0].message,
            total_tokens=total_tokens,
        )


def _resolve_groq_api_key() -> str | None:
    """Pull the Groq API key from Vault first, falling back to env var."""
    try:
        from app.config import get_settings
        from app.infra.vault import VaultClient, VaultSecretError

        settings = get_settings()
        token_obj = getattr(settings, "vault_token", None)
        token = (
            token_obj.get_secret_value()
            if token_obj is not None and hasattr(token_obj, "get_secret_value")
            else str(token_obj or "")
        )
        client = VaultClient(addr=settings.vault_addr, token=token)
        try:
            return client.resolve_groq_api_key()
        except VaultSecretError:
            pass
    except Exception:  # pragma: no cover - dev-only path
        _log.debug("groq: vault resolution failed, falling back to env", exc_info=True)

    env_value = os.getenv("GROQ_API_KEY")
    return env_value or None


def try_build_default_groq_client() -> GroqAgentClient | None:
    """Best-effort default construction — returns None when no key is available.

    The agent loop calls this once and falls back to the deterministic plan
    when None is returned, so local tests / dev environments without Groq
    credentials still get a coherent (if non-LLM) response.
    """
    try:
        return GroqAgentClient()
    except GroqUnavailable as exc:
        _log.info("groq client unavailable: %s — falling back to deterministic plan", exc)
        return None
