from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_chat_service
from app.schemas.message import MessageCreate
from app.schemas.session import InteractionResponse, SessionCreate, SessionDetail, SessionSummary
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
    interaction = service.send_message(session_id=session_id, content=payload.content)
    return InteractionResponse(
        session=SessionSummary.model_validate(interaction.session),
        user_message=interaction.user_message,
        assistant_message=interaction.assistant_message,
        usage=interaction.usage,
    )


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> SessionDetail:
    session = service.get_session(session_id)
    return SessionDetail.model_validate(session)
