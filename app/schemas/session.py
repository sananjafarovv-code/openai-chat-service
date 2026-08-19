from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import MessageRead


class SessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    model: Optional[str] = Field(default=None, max_length=100)


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    title: Optional[str]
    total_input_tokens: int
    total_output_tokens: int
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime


class UsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal
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
