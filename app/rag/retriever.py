# Owner: Nasser
"""Tenant-filtered RAG retrieval.

Every retrieval query must filter by tenant_id.
"""


async def retrieve_chunks(tenant_id: int, query: str, top_k: int = 5) -> list[dict]:
    """Retrieve tenant-scoped chunks."""
    return [
        {
            "tenant_id": tenant_id,
            "text": "Placeholder retrieved chunk.",
            "score": 1.0,
            "query": query,
            "top_k": top_k,
        }
    ]
