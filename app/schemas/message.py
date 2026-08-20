from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Model must not be blank.")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interaction_id: str
    generation: int
    sequence_number: int
    role: str
    content: str
    created_at: datetime
