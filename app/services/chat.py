from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.exceptions import SessionNotFoundError
from app.db.models import ChatSession, Message, UsageRecord
from app.repositories.session_repository import SessionRepository
from app.services.openai_client import ChatMessage, OpenAIChatClient
from app.services.pricing import PricingService
from app.services.session_locks import SessionLockManager


@dataclass(frozen=True)
class Interaction:
    session: ChatSession
    user_message: Message
    assistant_message: Message
    usage: UsageRecord


class ChatService:
    def __init__(
        self,
        repository: SessionRepository,
        openai_client: OpenAIChatClient,
        pricing_service: PricingService,
        default_model: str,
        lock_manager: SessionLockManager,
    ) -> None:
        self._repository = repository
        self._openai_client = openai_client
        self._pricing_service = pricing_service
        self._default_model = default_model
        self._lock_manager = lock_manager

    def create_session(self, model: Optional[str], title: Optional[str]) -> ChatSession:
        selected_model = model or self._default_model
        self._pricing_service.ensure_model_supported(selected_model)
        return self._repository.create(model=selected_model, title=title)

    def get_session(self, session_id: str) -> ChatSession:
        session = self._repository.get(session_id, with_details=True)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def send_message(self, session_id: str, content: str) -> Interaction:
        with self._lock_manager.acquire(session_id):
            return self._send_message_locked(session_id, content)

    def _send_message_locked(self, session_id: str, content: str) -> Interaction:
        session = self._repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        history = self._repository.list_messages(session_id)
        context = [ChatMessage(role=message.role, content=message.content) for message in history]
        context.append(ChatMessage(role="user", content=content))

        model = session.model
        self._repository.end_read_transaction()

        openai_result = self._openai_client.generate(model, context)
        pricing = self._pricing_service.calculate(
            model,
            input_tokens=openai_result.input_tokens,
            output_tokens=openai_result.output_tokens,
            cached_input_tokens=openai_result.cached_input_tokens,
            cache_write_tokens=openai_result.cache_write_tokens,
        )

        session = self._repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        user_message, assistant_message, usage = self._repository.save_interaction(
            session=session,
            user_content=content,
            openai_result=openai_result,
            pricing=pricing,
        )

        return Interaction(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            usage=usage,
        )
