"""Service-to-service authentication helpers.

Owner: Ayoub / Owner C

This module centralizes validation for internal service credentials.

Examples:
- API -> modelserver
- API -> guardrails sidecar

The token value should come from environment/Vault-backed config.
No real secrets should be hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceAuthResult:
    """Result of validating a service Authorization header."""

    is_valid: bool
    reason: str


def validate_bearer_token(
    authorization: str | None,
    expected_token: str | None,
) -> ServiceAuthResult:
    """Validate a Bearer token used for service-to-service calls.

    Returns a structured result instead of raising so FastAPI routes can
    decide which HTTP response to return.
    """

    if not expected_token:
        return ServiceAuthResult(
            is_valid=False,
            reason="Service token is not configured.",
        )

    if not authorization:
        return ServiceAuthResult(
            is_valid=False,
            reason="Missing Authorization header.",
        )

    expected_header = f"Bearer {expected_token}"

    if authorization != expected_header:
        return ServiceAuthResult(
            is_valid=False,
            reason="Invalid service credentials.",
        )

    return ServiceAuthResult(
        is_valid=True,
        reason="Service credentials are valid.",
    )