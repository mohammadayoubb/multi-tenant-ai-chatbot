# Owner: Hiba
"""Vault adapter.

Secrets must be resolved from Vault, not hardcoded in source files.
Ayoub must review security-sensitive changes in this module.
"""

from typing import Any

import hvac  # type: ignore[import-untyped]


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
