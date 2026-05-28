"""Guardrails HTTP client adapter.

Owner: Ayoub / Owner C

This module lets the main API call the guardrails sidecar safely.

Important:
- This is only the client adapter.
- The actual guardrails sidecar lives in guardrails/main.py.
- Do not log raw visitor messages here.
- Service-to-service calls must include a Bearer token.
- The token should come from config/Vault later, not be hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


GuardrailDecision = Literal["allow", "block"]


@dataclass(frozen=True)
class GuardrailCheckResult:
    """Result returned by the guardrails sidecar."""

    decision: GuardrailDecision
    reason: str
    matched_rule: str | None = None


class GuardrailsClientError(RuntimeError):
    """Raised when the guardrails sidecar call fails."""


class GuardrailsClient:
    """Async HTTP client for the guardrails sidecar."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds

    async def check(
        self,
        message: str,
        tenant_id: str | None = None,
    ) -> GuardrailCheckResult:
        """Send a message to the guardrails sidecar for safety checking."""

        if not self.service_token:
            raise GuardrailsClientError("Guardrails service token is missing.")

        payload: dict[str, str] = {
            "message": message,
        }

        if tenant_id is not None:
            payload["tenant_id"] = tenant_id

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/check",
                    headers={
                        "Authorization": f"Bearer {self.service_token}",
                    },
                    json=payload,
                )
        except httpx.RequestError as error:
            raise GuardrailsClientError("Guardrails request failed.") from error

        if response.status_code != 200:
            raise GuardrailsClientError(
                f"Guardrails returned status {response.status_code}."
            )

        data = response.json()

        return GuardrailCheckResult(
            decision=data["decision"],
            reason=data["reason"],
            matched_rule=data.get("matched_rule"),
        )