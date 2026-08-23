from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.message import MessageRead


class SessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Model must not be blank.")
        return value


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    title: Optional[str]
    current_generation: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime


class UsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interaction_id: str
    generation: int
    idempotency_key: Optional[str]
    model: str
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    input_price_per_1m: Decimal
    cached_input_price_per_1m: Decimal
    cache_write_price_per_1m: Decimal
    output_price_per_1m: Decimal
    uncached_input_cost: Decimal
    cached_input_cost: Decimal
    cache_write_cost: Decimal
    input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal
    long_context_applied: bool
    openai_response_id: Optional[str]
    created_at: datetime


class SessionDetail(SessionSummary):
    messages: list[MessageRead]
    usage_records: list[UsageRead]


class InteractionResponse(BaseModel):
    session: SessionSummary
    user_message: MessageRead
    assistant_message: MessageRead
    usage: UsageRead
    idempotency_replayed: bool
