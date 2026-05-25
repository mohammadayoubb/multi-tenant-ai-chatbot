# Owner: Nasser
"""Agent tools.

The only allowed tools are rag_search, capture_lead, and escalate.
"""

from app.rag.retriever import retrieve_chunks


async def rag_search(tenant_id: int, query: str) -> dict:
    """Search tenant CMS content and return an answer payload."""
    chunks = await retrieve_chunks(tenant_id=tenant_id, query=query)
    return {"answer": "Placeholder RAG answer.", "chunks": chunks}


async def capture_lead(tenant_id: int, name: str | None, contact: str | None, intent: str) -> dict:
    """Capture a tenant-scoped lead."""
    return {"tenant_id": tenant_id, "lead_id": "placeholder", "status": "captured"}


async def escalate(tenant_id: int, conversation_id: str, reason: str) -> dict:
    """Escalate a conversation to a human."""
    return {"tenant_id": tenant_id, "ticket_id": "placeholder", "reason": reason}
