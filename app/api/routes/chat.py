# Owner: Nasser
"""Public chat routes used by the embedded widget."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_id_from_widget_token
from app.db.session import get_session
from app.domain.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_id: UUID = Depends(get_tenant_id_from_widget_token),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Handle one widget chat message."""
    service = ChatService(session=session)
    return await service.handle_message(
        tenant_id=tenant_id,
        message=request.message,
        session_id=request.session_id,
    )
