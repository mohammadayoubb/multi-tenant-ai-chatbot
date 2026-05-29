# Owner: Ayoub
"""Platform guardrails snapshot service.

Read-only composition of:
- the locked platform rules (owned by the platform; never tenant-editable)
- the tenant-editable rails (blocked-topics list + refusal tone) sourced from
  the same TenantAgentConfig row that backs PUT /tenants/{tid}/agent-config

This service NEVER mutates state. The route is `GET /tenants/{tid}/platform-
guardrails`; the tenant section is updated through the agent-config PUT, not
through this endpoint.

The locked platform-rule registry mirrors the rule ids enforced by the
guardrails sidecar (`guardrails/main.py`). The list is kept here so the
admin UI can render them as read-only badges without making a sidecar call
on every page render.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.repositories.agent_config_repo import TenantAgentConfigRepository


_PLATFORM_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "block_cross_tenant_probe",
        "name": "Block cross-tenant probes",
        "description": "Refuses any question targeting another tenant's data.",
        "locked": True,
    },
    {
        "id": "block_pii_extraction",
        "name": "Block PII extraction prompts",
        "description": "Refuses requests to list users / dump PII / harvest contacts.",
        "locked": True,
    },
    {
        "id": "block_prompt_injection",
        "name": "Block prompt-injection attempts",
        "description": "Refuses jailbreaks, instruction overrides, role rewrites.",
        "locked": True,
    },
    {
        "id": "block_unsafe_topics",
        "name": "Block unsafe / abusive content",
        "description": "Refuses violence, self-harm, hate speech, explicit content.",
        "locked": True,
    },
)


_DEFAULT_REFUSAL_TONE = "polite"


class PlatformGuardrailsService:
    def __init__(self, agent_repo: TenantAgentConfigRepository) -> None:
        self._agent_repo = agent_repo

    async def snapshot(self, tenant_id: UUID) -> dict[str, Any]:
        """Return the platform-rules + tenant-rails view for one tenant."""
        agent_row = await self._agent_repo.get_by_tenant(tenant_id)
        rails = (agent_row.tenant_rails_json if agent_row else {}) or {}
        return {
            "platform_rules": [dict(rule) for rule in _PLATFORM_RULES],
            "tenant_blocked_topics": list(rails.get("tenant_blocked_topics", [])),
            "tenant_refusal_tone": rails.get(
                "tenant_refusal_tone", _DEFAULT_REFUSAL_TONE
            ),
        }
