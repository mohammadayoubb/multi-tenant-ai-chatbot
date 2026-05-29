# Owner: Nasser
"""Tenant agent-config service.

Read returns the UI-shape contract from missing-endpoints.md §1/§2:

    { persona_name, greeting, tone, language, business_rules, chips,
      tenant_blocked_topics, tenant_refusal_tone }

The persona column stores `persona_name`; everything else lives inside the
`tenant_rails_json` JSONB column. enabled_tools_json is left untouched (the
platform owns the tool surface, not the tenant).

Validation:
- chips: 0..6 entries, each 1..40 chars (raises AgentConfigInvalid → 422)
- tone, language, greeting, persona_name: trimmed length ≤ 255
- business_rules: length ≤ 4000

Audit emission `agent_config_updated` carries redacted metadata only (chip
count, not chip text).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.repositories.agent_config_repo import TenantAgentConfigRepository
from app.repositories.tenant_repo import TenantRepository


class AgentConfigInvalid(Exception):
    """The submitted agent-config body failed validation."""


_DEFAULT_CHIPS: tuple[str, ...] = (
    "Pricing",
    "Hours",
    "Talk to a human",
    "Get a quote",
)
_DEFAULT_GREETING = "Hi! How can I help?"
_DEFAULT_TONE = "professional"
_DEFAULT_LANGUAGE = "en"
_DEFAULT_REFUSAL_TONE = "polite"


class AgentConfigBody(BaseModel):
    """Wire shape consumed by PUT /tenants/{tid}/agent-config."""

    model_config = ConfigDict(extra="forbid")

    persona_name: str = Field(default="", max_length=255)
    greeting: str = Field(default=_DEFAULT_GREETING, max_length=2000)
    tone: str = Field(default=_DEFAULT_TONE, max_length=50)
    language: str = Field(default=_DEFAULT_LANGUAGE, max_length=20)
    business_rules: str = Field(default="", max_length=4000)
    chips: list[str] = Field(default_factory=list)
    tenant_blocked_topics: list[str] = Field(default_factory=list)
    tenant_refusal_tone: str = Field(default=_DEFAULT_REFUSAL_TONE, max_length=50)

    @field_validator("chips")
    @classmethod
    def _validate_chips(cls, value: list[str]) -> list[str]:
        if len(value) > 6:
            raise ValueError("chips must contain 0..6 entries")
        for chip in value:
            stripped = chip.strip() if isinstance(chip, str) else ""
            if not (1 <= len(stripped) <= 40):
                raise ValueError("each chip must be 1..40 characters")
        return [c.strip() for c in value]

    @field_validator("tenant_blocked_topics")
    @classmethod
    def _validate_topics(cls, value: list[str]) -> list[str]:
        if len(value) > 50:
            raise ValueError("tenant_blocked_topics capped at 50")
        return [t.strip() for t in value if isinstance(t, str) and t.strip()]


@dataclass(frozen=True)
class AgentConfigActor:
    """Trusted actor context for audited mutations."""

    tenant_id: UUID
    actor_id: str
    role: str


class AgentConfigService:
    def __init__(
        self,
        repo: TenantAgentConfigRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self._repo = repo
        self._tenant_repo = tenant_repo

    async def get_for_tenant(self, tenant_id: UUID) -> dict[str, Any]:
        row = await self._repo.get_by_tenant(tenant_id)
        if row is None:
            return _default_payload()
        rails = row.tenant_rails_json or {}
        return {
            "persona_name": row.persona or "",
            "greeting": rails.get("greeting", _DEFAULT_GREETING),
            "tone": rails.get("tone", _DEFAULT_TONE),
            "language": rails.get("language", _DEFAULT_LANGUAGE),
            "business_rules": rails.get("business_rules", ""),
            "chips": list(rails.get("chips", _DEFAULT_CHIPS)),
            "tenant_blocked_topics": list(rails.get("tenant_blocked_topics", [])),
            "tenant_refusal_tone": rails.get(
                "tenant_refusal_tone", _DEFAULT_REFUSAL_TONE
            ),
        }

    async def update_for_tenant(
        self,
        tenant_id: UUID,
        body: dict[str, Any],
        actor: AgentConfigActor,
    ) -> dict[str, Any]:
        try:
            validated = AgentConfigBody.model_validate(body)
        except ValidationError as exc:
            raise AgentConfigInvalid(str(exc)) from exc
        rails = {
            "greeting": validated.greeting,
            "tone": validated.tone,
            "language": validated.language,
            "business_rules": validated.business_rules,
            "chips": validated.chips,
            "tenant_blocked_topics": validated.tenant_blocked_topics,
            "tenant_refusal_tone": validated.tenant_refusal_tone,
        }
        await self._repo.upsert(
            tenant_id, persona=validated.persona_name, tenant_rails=rails
        )
        await self._tenant_repo.add_audit_log(
            tenant_id=tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            action="agent_config_updated",
            metadata={
                "chip_count": len(validated.chips),
                "tone": validated.tone,
                "language": validated.language,
            },
        )
        return await self.get_for_tenant(tenant_id)


def _default_payload() -> dict[str, Any]:
    return {
        "persona_name": "",
        "greeting": _DEFAULT_GREETING,
        "tone": _DEFAULT_TONE,
        "language": _DEFAULT_LANGUAGE,
        "business_rules": "",
        "chips": list(_DEFAULT_CHIPS),
        "tenant_blocked_topics": [],
        "tenant_refusal_tone": _DEFAULT_REFUSAL_TONE,
    }
