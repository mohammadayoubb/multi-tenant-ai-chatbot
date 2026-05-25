# Owner: Nasser
"""Redis cache and short-term memory helpers."""


class SessionMemory:
    """Placeholder short-term session memory adapter."""

    async def append_message(self, tenant_id: int, session_id: str, role: str, content: str) -> None:
        """Append a message to Redis session memory."""
        return None
