from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpenAI Chat Sessions API"
    database_url: str = "sqlite:///./chat.db"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5.6-luna"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_reasoning_context: Literal["current_turn"] = "current_turn"
    openai_max_output_tokens: int = Field(default=1_024, ge=1, le=128_000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
