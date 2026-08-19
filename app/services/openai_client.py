from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from openai import OpenAI, OpenAIError

from app.core.exceptions import OpenAIConfigurationError, OpenAIServiceError


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class OpenAIResult:
    content: str
    response_id: Optional[str]
    input_tokens: int
    output_tokens: int
    total_tokens: int


class OpenAIChatClient(Protocol):
    def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
        ...


class OpenAIResponsesClient:
    def __init__(self, api_key: Optional[str], timeout_seconds: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if not self._api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY is not configured.")
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=1,
            )
        return self._client

    def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
        request_input = [
            {"role": message.role, "content": message.content}
            for message in messages
        ]

        try:
            response = self._get_client().responses.create(
                model=model,
                input=request_input,
                store=False,
            )
        except OpenAIConfigurationError:
            raise
        except OpenAIError as exc:
            raise OpenAIServiceError("OpenAI API request failed.") from exc

        content = response.output_text.strip()
        usage = response.usage
        if not content:
            raise OpenAIServiceError("OpenAI returned an empty text response.")
        if usage is None:
            raise OpenAIServiceError("OpenAI response does not contain token usage.")

        return OpenAIResult(
            content=content,
            response_id=response.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
