from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.session_repository import SessionRepository
from app.services.chat import ChatService
from app.services.openai_client import OpenAIChatClient, OpenAIResponsesClient
from app.services.pricing import PricingService
from app.services.session_locks import SessionLockManager


@lru_cache
def get_openai_client() -> OpenAIChatClient:
    settings = get_settings()
    return OpenAIResponsesClient(
        api_key=settings.openai_api_key,
        reasoning_effort=settings.openai_reasoning_effort,
        reasoning_context=settings.openai_reasoning_context,
        max_output_tokens=settings.openai_max_output_tokens,
    )


@lru_cache
def get_pricing_service() -> PricingService:
    return PricingService()


@lru_cache
def get_session_lock_manager() -> SessionLockManager:
    return SessionLockManager()


def get_chat_service(
    db: Session = Depends(get_db),
    openai_client: OpenAIChatClient = Depends(get_openai_client),
    pricing_service: PricingService = Depends(get_pricing_service),
    lock_manager: SessionLockManager = Depends(get_session_lock_manager),
) -> ChatService:
    settings = get_settings()
    return ChatService(
        repository=SessionRepository(db),
        openai_client=openai_client,
        pricing_service=pricing_service,
        default_model=settings.openai_model,
        lock_manager=lock_manager,
    )
