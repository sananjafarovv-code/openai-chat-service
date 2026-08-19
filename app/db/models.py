from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 10),
        nullable=False,
        default=Decimal("0"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.sequence_number",
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by=lambda: (UsageRecord.created_at, UsageRecord.id),
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_messages_session_sequence"),
        Index("ix_messages_session_interaction", "session_id", "interaction_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    interaction_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    interaction_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    cached_input_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    cache_write_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    output_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    uncached_input_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    cached_input_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    cache_write_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    input_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    output_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    long_context_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    openai_response_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[ChatSession] = relationship(back_populates="usage_records")
