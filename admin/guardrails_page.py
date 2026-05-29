# Owner: Amer
"""Tenant Guardrails admin page (Spec 009 US2, T072).

Renders the read-only platform rules table (each row stamped "Locked by
platform" — tenants cannot weaken platform guardrails, FR-021) plus the
tenant-editable rails (blocked-topics list editor, refusal tone). Read via
`GET /tenants/{tid}/platform-guardrails` (T039j). Tenant edits persist
through `PUT /tenants/{tid}/agent-config` (T039a), so the agent and the
admin view stay aligned on the same row.

Any non-2xx response or transport error on the read falls back to the
canonical platform-rule list with a "(placeholder)" caption — even the
fallback renders the locked badge so platform rules NEVER appear unlocked.
"""

from __future__ import annotations

import copy
from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, signed_in_tenant_id
from admin.brand import COLORS, RADIUS

_REFUSAL_TONE_OPTIONS = ["polite", "firm", "neutral", "apologetic"]

_FALLBACK_SNAPSHOT: dict[str, Any] = {
    "platform_rules": [
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
    ],
    "tenant_blocked_topics": [],
    "tenant_refusal_tone": "polite",
}

_GENERIC_FORBIDDEN = "You do not have permission for that action."
_GENERIC_FAILED = "Save failed; please retry."


def _platform_url() -> str:
    return f"/tenants/{signed_in_tenant_id()}/platform-guardrails"


def _agent_config_url() -> str:
    return f"/tenants/{signed_in_tenant_id()}/agent-config"


def _fetch_snapshot() -> tuple[dict[str, Any], bool]:
    try:
        with _http_client() as client:
            resp = client.get(_platform_url())
    except httpx.HTTPError:
        return copy.deepcopy(_FALLBACK_SNAPSHOT), True
    if resp.status_code < 200 or resp.status_code >= 300:
        return copy.deepcopy(_FALLBACK_SNAPSHOT), True
    try:
        body = resp.json()
    except ValueError:
        return copy.deepcopy(_FALLBACK_SNAPSHOT), True
    if not isinstance(body, dict):
        return copy.deepcopy(_FALLBACK_SNAPSHOT), True
    return body, False


def _fetch_agent_config() -> dict[str, Any] | None:
    try:
        with _http_client() as client:
            resp = client.get(_agent_config_url())
    except httpx.HTTPError:
        return None
    if resp.status_code < 200 or resp.status_code >= 300:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _put_agent_config(payload: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.put(_agent_config_url(), json=payload)
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _locked_badge() -> str:
    bg = COLORS["neutral_bg"]
    fg = COLORS["text_muted"]
    return (
        f'<span style="display:inline-block;padding:2px 10px;'
        f'border-radius:{RADIUS["pill"]};background:{bg};color:{fg};'
        f'font-size:0.75rem;font-weight:600;letter-spacing:0.02em;">'
        "Locked by platform</span>"
    )


def _render_platform_rules(rules: list[dict[str, Any]]) -> None:
    st.markdown("### Platform rules")
    st.markdown(
        "These rules are enforced by the platform and cannot be disabled or "
        "weakened by tenant configuration."
    )
    if not rules:
        st.markdown("_No platform rules registered._")
        return
    badge_html = _locked_badge()
    for rule in rules:
        name = rule.get("name", "—")
        description = rule.get("description", "")
        st.markdown(f"**{name}** {badge_html}", unsafe_allow_html=True)
        if description:
            st.markdown(description)
        st.markdown("---")


def _render_tenant_section(snapshot: dict[str, Any]) -> None:
    st.markdown("### Tenant rules")
    st.caption(
        "Blocked topics extend the platform refusal set. The refusal tone "
        "shapes how the agent declines off-limits topics."
    )

    blocked_default = "\n".join(snapshot.get("tenant_blocked_topics") or [])
    blocked_raw = st.text_area(
        "Tenant blocked topics (one per line)",
        value=blocked_default,
        key="tenant_blocked_topics_input",
        height=160,
    )
    topics = [line.strip() for line in blocked_raw.splitlines() if line.strip()]

    tone_options = list(_REFUSAL_TONE_OPTIONS)
    current_tone = snapshot.get("tenant_refusal_tone") or _REFUSAL_TONE_OPTIONS[0]
    if current_tone not in tone_options:
        tone_options = [current_tone, *tone_options]
    tone = st.selectbox(
        "Tenant refusal tone",
        tone_options,
        index=tone_options.index(current_tone),
        key="tenant_refusal_tone_input",
    )

    save_clicked = st.button(
        "Save tenant rules", type="primary", key="save_guardrails"
    )
    if not save_clicked:
        return

    base = _fetch_agent_config()
    if base is None:
        st.error(_GENERIC_FAILED)
        return

    payload = dict(base)
    payload["tenant_blocked_topics"] = topics
    payload["tenant_refusal_tone"] = tone

    status_code, body = _put_agent_config(payload)
    if status_code in (200, 204):
        st.success("Saved.")
        st.rerun()
    elif status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
    elif status_code == 422:
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, str):
            st.error(f"Save rejected: {detail}")
        else:
            st.error("Save rejected: validation failed.")
    else:
        st.error(_GENERIC_FAILED)


def render() -> None:
    snapshot, placeholder = _fetch_snapshot()
    if placeholder:
        st.caption("(placeholder)")

    rules = snapshot.get("platform_rules") or []
    if not isinstance(rules, list):
        rules = []
    _render_platform_rules(rules)
    _render_tenant_section(snapshot)
