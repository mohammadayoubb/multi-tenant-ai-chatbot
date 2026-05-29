# Owner: Ayoub
"""Schemas for the platform-guardrails snapshot endpoint (T022).

Shape returned by ``GET /tenants/{tid}/platform-guardrails``. The route
currently emits a plain ``dict``; this schema is the authoritative response
contract referenced by the admin UI (`admin/guardrails_page.py`) and the
integration tests in ``tests/integration/test_platform_guardrails_endpoint.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlatformRuleItem(BaseModel):
    """One platform-locked rule. ``locked`` is always ``True``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    locked: bool = True


class PlatformGuardrailsResponse(BaseModel):
    """Response body for ``GET /tenants/{tid}/platform-guardrails``."""

    model_config = ConfigDict(extra="forbid")

    platform_rules: list[PlatformRuleItem]
    tenant_blocked_topics: list[str] = Field(default_factory=list)
    tenant_refusal_tone: str = "polite"
