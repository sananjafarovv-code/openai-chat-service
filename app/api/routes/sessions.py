from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_chat_service
from app.schemas.message import MessageCreate, MessageRead
from app.schemas.session import (
    InteractionResponse,
    SessionCreate,
    SessionDetail,
    SessionSummary,
    UsageRead,
)
from app.services.chat import ChatService

router = APIRouter()


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    service: ChatService = Depends(get_chat_service),
) -> SessionSummary:
    session = service.create_session(model=payload.model, title=payload.title)
    return SessionSummary.model_validate(session)


@router.post("/{session_id}/messages", response_model=InteractionResponse)
def send_message(
    session_id: str,
    payload: MessageCreate,
    service: ChatService = Depends(get_chat_service),
) -> InteractionResponse:
    interaction = service.send_message(
        session_id=session_id,
        content=payload.content,
        model=payload.model,
    )
    return InteractionResponse(
        session=SessionSummary.model_validate(interaction.session),
        user_message=interaction.user_message,
        assistant_message=interaction.assistant_message,
        usage=interaction.usage,
    )


@router.post("/{session_id}/reset", response_model=SessionSummary)
def reset_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> SessionSummary:
    session = service.reset_session(session_id)
    return SessionSummary.model_validate(session)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> SessionDetail:
    details = service.get_session(session_id)
    summary = SessionSummary.model_validate(details.session)
    return SessionDetail(
        **summary.model_dump(),
        messages=[MessageRead.model_validate(message) for message in details.messages],
        usage_records=[UsageRead.model_validate(usage) for usage in details.usage_records],
    )
