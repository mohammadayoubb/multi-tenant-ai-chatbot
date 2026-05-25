# Owner: Nasser
"""Public chat routes used by the embedded widget."""

from fastapi import APIRouter, Depends

from app.api.deps import get_tenant_id_from_widget_token
from app.domain.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_id: int = Depends(get_tenant_id_from_widget_token),
) -> ChatResponse:
    """Handle one widget chat message."""
    service = ChatService()
    return await service.handle_message(
        tenant_id=tenant_id,
        message=request.message,
        session_id=request.session_id,
    )
