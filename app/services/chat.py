from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.exceptions import SessionGenerationConflictError, SessionNotFoundError
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


@dataclass(frozen=True)
class SessionDetails:
    session: ChatSession
    messages: list[Message]
    usage_records: list[UsageRecord]


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

    def get_session(self, session_id: str) -> SessionDetails:
        session = self._repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return SessionDetails(
            session=session,
            messages=self._repository.list_messages(session_id, session.current_generation),
            usage_records=self._repository.list_usage_records(
                session_id,
                session.current_generation,
            ),
        )

    def reset_session(self, session_id: str) -> ChatSession:
        with self._lock_manager.acquire(session_id):
            session = self._repository.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            return self._repository.reset(session)

    def send_message(
        self,
        session_id: str,
        content: str,
        model: Optional[str] = None,
    ) -> Interaction:
        with self._lock_manager.acquire(session_id):
            return self._send_message_locked(session_id, content, model)

    def _send_message_locked(
        self,
        session_id: str,
        content: str,
        requested_model: Optional[str],
    ) -> Interaction:
        session = self._repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        generation = session.current_generation
        model = requested_model or session.model
        self._pricing_service.ensure_model_supported(model)

        history = self._repository.list_messages(session_id, generation)
        context = [ChatMessage(role=message.role, content=message.content) for message in history]
        context.append(ChatMessage(role="user", content=content))

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
        if session.current_generation != generation:
            raise SessionGenerationConflictError(session_id)

        user_message, assistant_message, usage = self._repository.save_interaction(
            session=session,
            generation=generation,
            model=model,
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
