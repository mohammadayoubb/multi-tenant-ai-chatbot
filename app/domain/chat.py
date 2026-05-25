# Owner: Nasser
"""Chat domain models."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Public widget chat request."""

    message: str
    session_id: str


class ChatResponse(BaseModel):
    """Public widget chat response."""

    answer: str
    route: str
    used_tools: list[str]
