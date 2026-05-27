# Owner: Nasser
"""Agent tools.

The only allowed tools are rag_search, capture_lead, and escalate.

Important security rule:
tenant_id is passed from trusted backend context. The visitor and the LLM never
choose tenant_id.
"""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.redaction import redact_text
from app.rag.retriever import retrieve_chunks
from app.repositories.lead_repo import LeadRepository

_MAX_RAG_TOP_K = 8
_MAX_INTENT_CHARS = 255
_MAX_NAME_CHARS = 255
_MAX_CONTACT_CHARS = 255
_MAX_ESCALATION_REASON_CHARS = 500


def build_rag_answer(query: str, chunks: list[dict[str, object]]) -> str:
    """Build a simple grounded answer from retrieved tenant CMS chunks.

    This is intentionally conservative. It only answers from retrieved chunks.
    If no chunk is found, it does not hallucinate.
    """

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
    tenant_id: int,
    query: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Search tenant CMS content and return an answer payload.

    Retrieval must remain tenant-filtered inside retrieve_chunks().
    """

    cleaned_query = query.strip()
    if not cleaned_query:
        return {
            "status": "empty_query",
            "answer": "Please send a question so I can search the tenant content.",
            "chunks": [],
            "tenant_id": tenant_id,
        }

    safe_top_k = max(1, min(top_k, _MAX_RAG_TOP_K))
    chunks = await retrieve_chunks(
        tenant_id=tenant_id,
        query=cleaned_query,
        top_k=safe_top_k,
        session=session,
    )

    return {
        "status": "ok",
        "answer": build_rag_answer(cleaned_query, chunks),
        "chunks": chunks,
        "tenant_id": tenant_id,
        "top_k": safe_top_k,
    }


async def capture_lead(
    tenant_id: int,
    name: str | None,
    contact: str | None,
    intent: str,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Capture a tenant-scoped lead.

    The caller supplies tenant_id from trusted server context, never from the
    visitor or LLM. A DB session writes a real Lead; otherwise a synthetic id is
    returned for local tests/dev.
    """

    clean_intent = _clean_optional(intent, _MAX_INTENT_CHARS) or "Visitor requested follow-up"
    clean_name = _clean_optional(name, _MAX_NAME_CHARS)
    clean_contact = _clean_optional(contact, _MAX_CONTACT_CHARS)

    redacted_intent = redact_text(clean_intent)

    if session is not None:
        repo = LeadRepository(session)
        lead = await repo.create(
            tenant_id=tenant_id,
            name=clean_name,
            contact=clean_contact,
            intent=redacted_intent,
        )
        return {
            "status": "captured",
            "lead_id": lead.id,
            "tenant_id": tenant_id,
            "has_contact": clean_contact is not None,
        }

    return {
        "status": "captured",
        "lead_id": str(uuid4()),
        "tenant_id": tenant_id,
        "has_contact": clean_contact is not None,
    }


async def escalate(
    tenant_id: int,
    conversation_id: str,
    reason: str,
) -> dict[str, object]:
    """Escalate a conversation to a human.

    This currently returns a ticket-like payload. A later persistence layer can
    write it to a tenant-scoped tickets/escalations table.
    """

    clean_conversation_id = _clean_optional(conversation_id, 128) or "unknown-session"
    clean_reason = (
        _clean_optional(reason, _MAX_ESCALATION_REASON_CHARS)
        or "Visitor needs human follow-up."
    )

    return {
        "status": "escalated",
        "ticket_id": str(uuid4()),
        "tenant_id": tenant_id,
        "conversation_id": clean_conversation_id,
        "reason": redact_text(clean_reason),
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


def _clean_optional(value: str | None, max_chars: int) -> str | None:
    """Trim optional text and return None for empty values."""

    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    return cleaned[:max_chars]
