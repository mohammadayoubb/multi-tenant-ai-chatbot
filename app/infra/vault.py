# Owner: Hiba
"""Vault adapter.

Secrets must be resolved from Vault, not hardcoded in source files.
Ayoub must review security-sensitive changes in this module.
"""

from typing import Any

import hvac  # type: ignore[import-untyped]

LLM_ANTHROPIC_KEY_PATH = "secret/data/llm/anthropic_api_key"
LLM_GROQ_KEY_PATH = "secret/data/llm/groq_api_key"


class VaultSecretError(RuntimeError):
    """Raised when Vault cannot return a required secret."""


class VaultClient:
    """Small Vault client wrapper used by app configuration."""

    def __init__(self, addr: str, token: str, timeout_seconds: float = 5.0) -> None:
        self.addr = addr
        self._client: Any = hvac.Client(url=addr, token=token, timeout=timeout_seconds)

    def is_reachable(self) -> bool:
        """Return whether Vault is reachable."""
        try:
            return bool(self._client.sys.is_initialized())
        except Exception:
            return False

    def read_secret(self, path: str) -> dict[str, Any]:
        """Read and unwrap a Vault secret payload."""
        response = self._client.read(path)
        if not response or not isinstance(response, dict):
            raise VaultSecretError(f"Vault secret was not found at path: {path}")

        payload = response.get("data")
        if not isinstance(payload, dict):
            raise VaultSecretError(f"Vault secret at path {path} did not contain data")

        nested_payload = payload.get("data")
        if isinstance(nested_payload, dict):
            return nested_payload
        return payload

    def resolve_anthropic_api_key(self) -> str:
        """Return the Anthropic API key seeded at ``LLM_ANTHROPIC_KEY_PATH``.

        Kept for rollback only — DECISION 19b (revised) selects Groq as the
        live LLM provider. The path stays seeded so a redeploy can revert
        without touching Vault again. Raises :class:`VaultSecretError` if the
        path is missing or the ``anthropic_api_key`` field is empty.
        """
        payload = self.read_secret(LLM_ANTHROPIC_KEY_PATH)
        key = payload.get("anthropic_api_key")
        if not isinstance(key, str) or not key:
            raise VaultSecretError(
                f"anthropic_api_key missing or empty at {LLM_ANTHROPIC_KEY_PATH}"
            )
        return key

    def resolve_groq_api_key(self) -> str:
        """Return the Groq API key seeded at ``LLM_GROQ_KEY_PATH``.

        Live LLM credential for the Track-2 agent loop (DECISION 19b revised).
        Raises :class:`VaultSecretError` if the path is missing or the
        ``groq_api_key`` field is empty.
        """
        payload = self.read_secret(LLM_GROQ_KEY_PATH)
        key = payload.get("groq_api_key")
        if not isinstance(key, str) or not key:
            raise VaultSecretError(
                f"groq_api_key missing or empty at {LLM_GROQ_KEY_PATH}"
            )
        return key
