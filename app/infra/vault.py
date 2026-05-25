# Owner: Hiba
"""Vault adapter.

Secrets must be resolved from Vault, not hardcoded in source files.
"""


class VaultClient:
    """Placeholder Vault client wrapper."""

    def __init__(self, addr: str, token: str) -> None:
        self.addr = addr
        self.token = token

    def is_reachable(self) -> bool:
        """Return whether Vault is reachable."""
        return True
