# Owner: Nasser
"""Agent tools.

The only allowed tools are rag_search, capture_lead, and escalate.

Important security rule:
tenant_id is passed from trusted backend context. The visitor and the LLM never
choose tenant_id, session_id, conversation_id, or actor_id. The Pydantic
schemas below enforce that physically — they have `extra="forbid"` and no
fields for any trusted identifier, so any LLM tool_use call attempting to
supply one fails validation at the boundary (contract C-T2-2, task T051).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, EscalationTicket, TenantSettings
from app.infra.redaction import redact_text
from app.rag.retriever import retrieve_chunks
from app.repositories.escalation_repo import EscalationRepository
from app.repositories.lead_repo import LeadRepository
from app.repositories.tenant_repo import TenantRepository
from app.services.rate_limiter import lead_capture_rate_limiter

_MAX_RAG_TOP_K = 10
_MAX_INTENT_CHARS = 1000
_MAX_NAME_CHARS = 200
_MAX_CONTACT_CHARS = 255
_MAX_ESCALATION_REASON_CHARS = 280
_AUDIT_EXCERPT_CHARS = 80
_DEFAULT_LEAD_CAP = 5

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic argument schemas (contract C-T2-2, task T050).
#
# These describe ONLY the fields an LLM is allowed to choose. tenant_id,
# session_id, conversation_id, and actor_id are absent on purpose — they are
# trusted-context kwargs that the tool functions accept from the caller
# (ChatService / agent loop) and they must never appear in an LLM tool_use
# payload. `extra="forbid"` makes that physical: any LLM-supplied
# tenant_id / session_id / actor_id raises ValidationError.
# ---------------------------------------------------------------------------


_CONTACT_PATTERN = r"^([\w.\-+]+@[\w\-]+\.[\w.\-]+|[\+\d][\d\s\-\(\)]{6,})$"


class RagSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=_MAX_RAG_TOP_K)


class CaptureLeadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=_MAX_NAME_CHARS)
    contact: str | None = Field(default=None, pattern=_CONTACT_PATTERN)
    intent: str = Field(min_length=1, max_length=_MAX_INTENT_CHARS)


class EscalateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=_MAX_ESCALATION_REASON_CHARS)


# ---------------------------------------------------------------------------
# Tool implementations.
# ---------------------------------------------------------------------------


def build_rag_answer(query: str, chunks: list[dict[str, object]]) -> str:
    """Build a simple grounded answer from retrieved tenant CMS chunks."""

    cleaned_query = query.strip()
    if not chunks:
        return (
            "I could not find this in the tenant's published content. "
            "I can escalate this to a human if you want."
        )

    selected_chunks = chunks[:3]
    answer_parts: list[str] = []

    for index, chunk in enumerate(selected_chunks, start=1):
        source = str(chunk.get("source_title", "CMS content")).strip() or "CMS content"
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue

        snippet = text[:450].strip()
        answer_parts.append(f"{index}. From {source}: {snippet}")

    if not answer_parts:
        return (
            "I found tenant content, but it did not contain enough readable text "
            "to answer safely. I can escalate this to a human if needed."
        )

    intro = "Based on the tenant's published content"
    if cleaned_query:
        intro = f"Based on the tenant's published content for your question: “{cleaned_query[:120]}”"

    return f"{intro}\n\n" + "\n\n".join(answer_parts)


async def rag_search(
    *,
    tenant_id: Any,
    query: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Search tenant CMS content and return an answer payload.

    The LLM-controlled args (`query`, `top_k`) are validated against
    `RagSearchArgs` before retrieval. `tenant_id` is trusted-context and
    never appears in the schema.
    """

    try:
        args = RagSearchArgs(query=query, top_k=top_k)
    except ValidationError as exc:
        return {
            "status": "invalid_args",
            "tenant_id": _tid_str(tenant_id),
            "errors": exc.errors(),
        }

    chunks = await retrieve_chunks(
        tenant_id=tenant_id,
        query=args.query,
        top_k=args.top_k,
        session=session,
    )

    return {
        "status": "ok",
        "answer": build_rag_answer(args.query, chunks),
        "chunks": chunks,
        "tenant_id": _tid_str(tenant_id),
        "top_k": args.top_k,
    }


async def capture_lead(
    *,
    tenant_id: Any,
    session_id: str,
    name: str | None,
    contact: str | None,
    intent: str,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Capture a tenant-scoped lead.

    Enforces the per-session write-rate cap (task T052) BEFORE doing any work.
    `tenant_id` and `session_id` are trusted-context kwargs from the caller.
    LLM-supplied values for either would be dropped at the Pydantic boundary
    (they are not fields on `CaptureLeadArgs`).
    """

    clean_intent = (intent or "").strip()
    if not clean_intent:
        clean_intent = "Visitor requested follow-up"

    clean_name = _trim_optional(name, _MAX_NAME_CHARS)
    clean_contact = _trim_optional(contact, _MAX_CONTACT_CHARS)

    try:
        args = CaptureLeadArgs(
            name=clean_name,
            contact=clean_contact,
            intent=clean_intent[:_MAX_INTENT_CHARS],
        )
    except ValidationError as exc:
        return {
            "status": "invalid_args",
            "tenant_id": _tid_str(tenant_id),
            "session_id": session_id,
            "errors": exc.errors(),
        }

    cap = await _resolve_lead_cap(session, tenant_id)
    limiter = lead_capture_rate_limiter()
    allowed = await limiter.check_and_increment(tenant_id, session_id, cap=cap)
    if not allowed:
        await _emit_audit_safe(
            session,
            tenant_id=tenant_id,
            action="lead.rate_limited",
            metadata={"session_id": session_id, "count_in_window": cap},
        )
        return {
            "status": "rate_limited",
            "tenant_id": _tid_str(tenant_id),
            "session_id": session_id,
        }

    redacted_intent = redact_text(args.intent)

    if session is not None:
        repo = LeadRepository(session)
        lead = await repo.create(
            tenant_id=tenant_id,
            name=args.name,
            contact=args.contact,
            intent=redacted_intent,
        )
        return {
            "status": "captured",
            "lead_id": str(lead.id),
            "tenant_id": _tid_str(tenant_id),
            "session_id": session_id,
            "has_contact": args.contact is not None,
        }

    return {
        "status": "captured",
        "lead_id": str(uuid4()),
        "tenant_id": _tid_str(tenant_id),
        "session_id": session_id,
        "has_contact": args.contact is not None,
    }


async def escalate(
    *,
    tenant_id: Any,
    conversation_id: str,
    reason: str,
    last_message_excerpt: str = "",
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Escalate a conversation to a human (task T053).

    `conversation_id` is the session identifier supplied by the trusted
    caller (chat_service / agent loop). On the first call for a given
    session, INSERT a row via `EscalationRepository.create()` and emit
    `escalation.created`. Subsequent calls in the same session return the
    existing ticket_id without a second INSERT.
    """

    clean_reason = (reason or "").strip() or "Visitor needs human follow-up."

    try:
        args = EscalateArgs(reason=clean_reason[:_MAX_ESCALATION_REASON_CHARS])
    except ValidationError as exc:
        return {
            "status": "invalid_args",
            "tenant_id": _tid_str(tenant_id),
            "session_id": conversation_id,
            "errors": exc.errors(),
        }

    redacted_reason = redact_text(args.reason)

    if session is None:
        # No DB context — synthetic ticket for dev/tests that don't bind a
        # session. The in-DB dedup rule does not apply in this path.
        return {
            "status": "escalated",
            "ticket_id": str(uuid4()),
            "tenant_id": _tid_str(tenant_id),
            "conversation_id": conversation_id,
            "session_id": conversation_id,
            "reason": redacted_reason,
        }

    conversation = await _ensure_conversation(session, tenant_id, conversation_id)
    existing = await _find_existing_escalation(session, tenant_id, conversation.id)
    if existing is not None:
        return {
            "status": "escalated",
            "ticket_id": str(existing.id),
            "tenant_id": _tid_str(tenant_id),
            "conversation_id": conversation_id,
            "session_id": conversation_id,
            "reason": redacted_reason,
            "deduplicated": True,
        }

    repo = EscalationRepository(session)
    ticket = await repo.create(
        tenant_id=_coerce_uuid(tenant_id),
        conversation_id=conversation.id,
        reason=args.reason,
        last_message_excerpt=last_message_excerpt,
    )

    # Principle V — the audit metadata excerpt MUST pass through redact_text
    # before persist (contract C-T2-5 / task T053).
    reason_excerpt = redact_text(args.reason)[:_AUDIT_EXCERPT_CHARS]
    await _emit_audit_safe(
        session,
        tenant_id=tenant_id,
        action="escalation.created",
        metadata={
            "ticket_id": str(ticket.id),
            "session_id": conversation_id,
            "reason_excerpt": reason_excerpt,
        },
    )

    return {
        "status": "escalated",
        "ticket_id": str(ticket.id),
        "tenant_id": _tid_str(tenant_id),
        "conversation_id": conversation_id,
        "session_id": conversation_id,
        "reason": redacted_reason,
    }


def extract_lead_fields(message: str) -> tuple[str | None, str | None]:
    """Best-effort extraction for direct workflow lead capture.

    This is intentionally lightweight. It is not treated as trusted identity.
    """

    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        message,
    )
    phone_match = re.search(
        r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)",
        message,
    )
    name_match = re.search(
        r"(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z\s'-]{1,60})",
        message,
        re.IGNORECASE,
    )

    contact = None
    if email_match is not None:
        contact = email_match.group(0)
    elif phone_match is not None:
        contact = phone_match.group(0)

    name = name_match.group(1).strip() if name_match else None

    return name, contact


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _trim_optional(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_chars]


def _tid_str(tenant_id: Any) -> str:
    return str(tenant_id)


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def _resolve_lead_cap(session: AsyncSession | None, tenant_id: Any) -> int:
    """Return the per-session cap from tenant_settings, defaulting to 5."""
    if session is None:
        return _DEFAULT_LEAD_CAP
    try:
        tid = _coerce_uuid(tenant_id)
    except (TypeError, ValueError):
        return _DEFAULT_LEAD_CAP
    try:
        result = await session.execute(
            select(TenantSettings.rate_limit_lead_per_session).where(
                TenantSettings.tenant_id == tid
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return _DEFAULT_LEAD_CAP
        return int(row)
    except Exception:  # pragma: no cover - defensive; tenant_settings is optional
        _log.warning("capture_lead: failed to read tenant_settings cap", exc_info=True)
        return _DEFAULT_LEAD_CAP


async def _emit_audit_safe(
    session: AsyncSession | None,
    *,
    tenant_id: Any,
    action: str,
    metadata: dict[str, Any],
    actor_role: str = "agent",
) -> None:
    """Emit an audit entry; swallow errors so a failed audit never breaks a tool."""
    if session is None:
        return
    try:
        repo = TenantRepository(session)
        await repo.add_audit_log(
            tenant_id=_coerce_uuid(tenant_id),
            actor_id=None,
            actor_role=actor_role,
            action=action,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover - defensive
        _log.warning("tool audit emission failed: action=%s", action, exc_info=True)


async def _ensure_conversation(
    session: AsyncSession,
    tenant_id: Any,
    session_id: str,
) -> Conversation:
    """Return the Conversation for (tenant_id, session_id), creating one if absent."""
    tid = _coerce_uuid(tenant_id)
    result = await session.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tid)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.started_at.asc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is not None:
        return conversation
    conversation = Conversation(tenant_id=tid, session_id=session_id, status="open")
    session.add(conversation)
    await session.flush()
    return conversation


async def _find_existing_escalation(
    session: AsyncSession,
    tenant_id: Any,
    conversation_id: UUID,
) -> EscalationTicket | None:
    """Return the existing escalation for a conversation, if one was created."""
    tid = _coerce_uuid(tenant_id)
    result = await session.execute(
        select(EscalationTicket)
        .where(EscalationTicket.tenant_id == tid)
        .where(EscalationTicket.conversation_id == conversation_id)
        .order_by(EscalationTicket.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()
