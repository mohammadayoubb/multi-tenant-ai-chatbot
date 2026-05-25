# Owner: Nasser
"""Chat orchestration service.

This service connects router, agent, RAG, memory, and guardrails.
"""

from app.agent.router import route_message
from app.domain.chat import ChatResponse


class ChatService:
    """Handle one visitor chat turn."""

    async def handle_message(self, tenant_id: int, message: str, session_id: str) -> ChatResponse:
        """Route a message through workflow or agent path."""
        route = await route_message(message)

        return ChatResponse(
            answer="Placeholder answer. Implement RAG/agent behavior here.",
            route=route,
            used_tools=[],
        )
