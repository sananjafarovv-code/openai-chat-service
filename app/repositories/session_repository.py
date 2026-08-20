from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ChatSession, Message, UsageRecord, utc_now
from app.services.openai_client import OpenAIResult
from app.services.pricing import PricingBreakdown


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, model: str, title: Optional[str]) -> ChatSession:
        session = ChatSession(model=model, title=title)
        self._db.add(session)
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._db.refresh(session)
        return session

    def get(self, session_id: str) -> Optional[ChatSession]:
        statement = select(ChatSession).where(ChatSession.id == session_id)
        return self._db.scalar(statement)

    def list_messages(self, session_id: str, generation: int) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.generation == generation,
            )
            .order_by(Message.sequence_number)
        )
        return list(self._db.scalars(statement))

    def list_usage_records(self, session_id: str, generation: int) -> list[UsageRecord]:
        statement = (
            select(UsageRecord)
            .where(
                UsageRecord.session_id == session_id,
                UsageRecord.generation == generation,
            )
            .order_by(UsageRecord.created_at, UsageRecord.id)
        )
        return list(self._db.scalars(statement))

    def end_read_transaction(self) -> None:
        """Release the database connection before a slow external API call."""
        self._db.rollback()

    def reset(self, session: ChatSession) -> ChatSession:
        session.current_generation += 1
        session.total_input_tokens = 0
        session.total_output_tokens = 0
        session.total_cost = Decimal("0")
        session.updated_at = utc_now()
        self._db.add(session)

        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

        self._db.refresh(session)
        return session

    def save_interaction(
        self,
        session: ChatSession,
        generation: int,
        model: str,
        user_content: str,
        openai_result: OpenAIResult,
        pricing: PricingBreakdown,
    ) -> tuple[Message, Message, UsageRecord]:
        last_sequence = self._db.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.session_id == session.id,
                Message.generation == generation,
            )
        )
        next_sequence = int(last_sequence or 0) + 1
        interaction_id = str(uuid4())

        user_message = Message(
            session_id=session.id,
            interaction_id=interaction_id,
            generation=generation,
            sequence_number=next_sequence,
            role="user",
            content=user_content,
        )
        assistant_message = Message(
            session_id=session.id,
            interaction_id=interaction_id,
            generation=generation,
            sequence_number=next_sequence + 1,
            role="assistant",
            content=openai_result.content,
        )
        usage_record = UsageRecord(
            session_id=session.id,
            interaction_id=interaction_id,
            generation=generation,
            model=model,
            input_tokens=openai_result.input_tokens,
            cached_input_tokens=openai_result.cached_input_tokens,
            cache_write_tokens=openai_result.cache_write_tokens,
            output_tokens=openai_result.output_tokens,
            reasoning_tokens=openai_result.reasoning_tokens,
            total_tokens=openai_result.total_tokens,
            input_price_per_1m=pricing.input_price_per_1m,
            cached_input_price_per_1m=pricing.cached_input_price_per_1m,
            cache_write_price_per_1m=pricing.cache_write_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            uncached_input_cost=pricing.uncached_input_cost,
            cached_input_cost=pricing.cached_input_cost,
            cache_write_cost=pricing.cache_write_cost,
            input_cost=pricing.input_cost,
            output_cost=pricing.output_cost,
            total_cost=pricing.total_cost,
            long_context_applied=pricing.long_context_applied,
            openai_response_id=openai_result.response_id,
        )

        session.total_input_tokens += openai_result.input_tokens
        session.total_output_tokens += openai_result.output_tokens
        session.total_cost = Decimal(session.total_cost) + pricing.total_cost
        session.updated_at = utc_now()

        self._db.add_all([user_message, assistant_message, usage_record, session])
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

        self._db.refresh(user_message)
        self._db.refresh(assistant_message)
        self._db.refresh(usage_record)
        self._db.refresh(session)
        return user_message, assistant_message, usage_record
