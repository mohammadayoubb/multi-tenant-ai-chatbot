"""Modelserver HTTP client adapter.

Owner: Ayoub / Owner C

This module lets the main API call the classifier modelserver safely.

Important:
- Do not log raw visitor messages here.
- Service-to-service calls must include a Bearer token.
- Token should come from config/Vault later, not hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


RouterLabel = Literal[
    "spam",
    "faq",
    "sales_or_contact",
    "human_request",
    "ambiguous",
]


@dataclass(frozen=True)
class ModelserverPrediction:
    """Prediction returned by the modelserver."""

    label: RouterLabel
    confidence: float
    model_version: str
    latency_ms: float


class ModelserverClientError(RuntimeError):
    """Raised when the modelserver call fails."""


class ModelserverClient:
    """Async HTTP client for the classifier modelserver."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds

    async def predict(self, message: str) -> ModelserverPrediction:
        """Send a message to the modelserver and return its router prediction."""

        if not self.service_token:
            raise ModelserverClientError("Modelserver service token is missing.")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/predict",
                    headers={
                        "Authorization": f"Bearer {self.service_token}",
                    },
                    json={
                        "message": message,
                    },
                )
        except httpx.RequestError as error:
            raise ModelserverClientError("Modelserver request failed.") from error

        if response.status_code != 200:
            raise ModelserverClientError(
                f"Modelserver returned status {response.status_code}."
            )

        data = response.json()

        return ModelserverPrediction(
            label=data["label"],
            confidence=float(data["confidence"]),
            model_version=data["model_version"],
            latency_ms=float(data["latency_ms"]),
        )