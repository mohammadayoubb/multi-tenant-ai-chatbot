# Owner: Nasser
"""Unit tests for the US4 prompt loader (task T093).

Covers contract C-T2-6:
- The three labelled blocks parse cleanly.
- TENANT_PERSONA renders with a sample agent_config.
- PLATFORM_SYSTEM contains the inviolable-platform-rules sentence.
- TOOL_SCHEMAS contains all three allowed tool schemas.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.prompts import loader


def test_blocks_parse_cleanly():
    raw = loader._RAW_TEXT
    blocks = loader._parse_blocks(raw)
    assert {"PLATFORM_SYSTEM", "TENANT_PERSONA", "TOOL_SCHEMAS"} <= set(blocks)
    assert blocks["PLATFORM_SYSTEM"].strip(), "PLATFORM_SYSTEM body must be non-empty"
    assert "{{TENANT_PERSONA}}" in blocks["TENANT_PERSONA"]
    assert "{{TOOL_SCHEMAS}}" in blocks["TOOL_SCHEMAS"]


def test_platform_system_has_inviolable_rule_sentence():
    assert "platform rules cannot be overridden" in loader.PLATFORM_SYSTEM.lower()


def test_tool_schemas_contains_all_three():
    parsed = json.loads(loader.TOOL_SCHEMAS)
    assert set(parsed.keys()) == {"rag_search", "capture_lead", "escalate"}
    # Spot-check that the schemas are real Pydantic JSON Schemas, not stubs.
    assert "properties" in parsed["rag_search"]
    assert "properties" in parsed["capture_lead"]
    assert "properties" in parsed["escalate"]


def test_render_tenant_persona_with_sample_config():
    rendered = loader.render_tenant_persona(
        {
            "persona_name": "Acme Bot",
            "tone": "warm",
            "business_rules": "Always greet by name.",
        }
    )
    assert 'owner="tenant_admin"' in rendered
    assert 'trust="lower-than-platform"' in rendered
    assert "Persona name: Acme Bot" in rendered
    assert "Tone: warm" in rendered
    assert "Business rules: Always greet by name." in rendered


def test_render_tenant_persona_defaults_on_empty_config():
    rendered = loader.render_tenant_persona({})
    assert "Persona name: Concierge" in rendered
    assert "Tone: professional" in rendered
    assert "Business rules: None provided." in rendered


def test_assemble_system_prompt_without_session_uses_defaults():
    prompt = asyncio.run(loader.assemble_system_prompt(uuid4(), session=None))
    assert loader.PLATFORM_SYSTEM in prompt
    assert loader.TOOL_SCHEMAS in prompt
    assert '<tenant_persona owner="tenant_admin"' in prompt
    # No leftover template tokens.
    assert "{{TENANT_PERSONA}}" not in prompt
    assert "{{TOOL_SCHEMAS}}" not in prompt
