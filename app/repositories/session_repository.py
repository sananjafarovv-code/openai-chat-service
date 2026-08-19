from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

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

    def get(self, session_id: str, with_details: bool = False) -> Optional[ChatSession]:
        statement = select(ChatSession).where(ChatSession.id == session_id)
        if with_details:
            statement = statement.options(
                selectinload(ChatSession.messages),
                selectinload(ChatSession.usage_records),
            )
        return self._db.scalar(statement)

    def list_messages(self, session_id: str) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.sequence_number)
        )
        return list(self._db.scalars(statement))

    def save_interaction(
        self,
        session: ChatSession,
        user_content: str,
        openai_result: OpenAIResult,
        pricing: PricingBreakdown,
    ) -> tuple[Message, Message, UsageRecord]:
        last_sequence = self._db.scalar(
            select(func.max(Message.sequence_number)).where(Message.session_id == session.id)
        )
        next_sequence = int(last_sequence or 0) + 1

        user_message = Message(
            session_id=session.id,
            sequence_number=next_sequence,
            role="user",
            content=user_content,
        )
        assistant_message = Message(
            session_id=session.id,
            sequence_number=next_sequence + 1,
            role="assistant",
            content=openai_result.content,
        )
        usage_record = UsageRecord(
            session_id=session.id,
            model=session.model,
            input_tokens=openai_result.input_tokens,
            output_tokens=openai_result.output_tokens,
            total_tokens=openai_result.total_tokens,
            input_price_per_1m=pricing.input_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            input_cost=pricing.input_cost,
            output_cost=pricing.output_cost,
            total_cost=pricing.total_cost,
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
