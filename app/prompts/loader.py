# Owner: Nasser
"""Prompt loader (US4 / contract C-T2-6 / task T089).

Parses ``app/prompts/system_prompt.md`` into three labelled blocks
(``PLATFORM_SYSTEM``, ``TENANT_PERSONA``, ``TOOL_SCHEMAS``) and assembles the
final system message per request.

PLATFORM_SYSTEM + TOOL_SCHEMAS are immutable after process start and cached on
module import. TENANT_PERSONA is read fresh per request from
``TenantAgentConfigRepository.get_by_tenant`` so a ``PUT
/tenants/{tid}/agent-config`` change reaches the next visitor message inside
60 s (research §R10 / SC-009).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import CaptureLeadArgs, EscalateArgs, RagSearchArgs
from app.repositories.agent_config_repo import TenantAgentConfigRepository

_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.md"

_BLOCK_RE = re.compile(
    r"<!--\s*(?P<name>[A-Z_]+):(?:start|placeholder)\s*-->"
    r"(?P<body>.*?)"
    r"<!--\s*(?P=name):end\s*-->",
    re.DOTALL,
)


def _parse_blocks(text: str) -> dict[str, str]:
    return {m.group("name"): m.group("body").strip() for m in _BLOCK_RE.finditer(text)}


def _render_tool_schemas() -> str:
    schemas = {
        "rag_search": RagSearchArgs.model_json_schema(),
        "capture_lead": CaptureLeadArgs.model_json_schema(),
        "escalate": EscalateArgs.model_json_schema(),
    }
    return json.dumps(schemas, indent=2, sort_keys=True)


_RAW_TEXT = _PROMPT_PATH.read_text(encoding="utf-8")
_BLOCKS = _parse_blocks(_RAW_TEXT)
PLATFORM_SYSTEM: str = _BLOCKS["PLATFORM_SYSTEM"]
TOOL_SCHEMAS: str = _render_tool_schemas()


def render_tenant_persona(config: dict[str, Any]) -> str:
    """Render the labelled persona block per contract C-T2-6."""
    persona_name = (config.get("persona_name") or "").strip() or "Concierge"
    tone = (config.get("tone") or "").strip() or "professional"
    business_rules = (config.get("business_rules") or "").strip() or "None provided."
    return (
        '<tenant_persona owner="tenant_admin" trust="lower-than-platform">\n'
        f"Persona name: {persona_name}\n"
        f"Tone: {tone}\n"
        f"Business rules: {business_rules}\n"
        "</tenant_persona>"
    )


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def assemble_system_prompt(
    tenant_id: Any, session: AsyncSession | None = None
) -> str:
    """Compose system_prompt = PLATFORM_SYSTEM + rendered_persona + TOOL_SCHEMAS.

    The tenant persona is fetched fresh per request — no cross-request cache
    (research §R10). When no DB session is available, the rendered persona
    falls back to safe defaults so the prompt remains well-formed.
    """
    payload: dict[str, Any] = {}
    if session is not None:
        try:
            tid = _coerce_uuid(tenant_id)
        except (TypeError, ValueError):
            tid = None
        if tid is not None:
            repo = TenantAgentConfigRepository(session)
            row = await repo.get_by_tenant(tid)
            if row is not None:
                rails = row.tenant_rails_json or {}
                payload = {
                    "persona_name": row.persona or "",
                    "tone": rails.get("tone", ""),
                    "business_rules": rails.get("business_rules", ""),
                }
    rendered_persona = render_tenant_persona(payload)
    return f"{PLATFORM_SYSTEM}\n\n{rendered_persona}\n\n{TOOL_SCHEMAS}"
