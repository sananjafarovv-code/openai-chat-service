from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional, Protocol

from openai import (
    APIConnectionError as SDKConnectionError,
    APIStatusError,
    APITimeoutError as SDKTimeoutError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.exceptions import (
    OpenAIConfigurationError,
    OpenAIConnectionError,
    OpenAIQuotaError,
    OpenAIRateLimitError,
    OpenAIServiceError,
    OpenAITimeoutError,
)

logger = logging.getLogger(__name__)


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
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


class OpenAIChatClient(Protocol):
    def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
        ...


class OpenAIResponsesClient:
    def __init__(
        self,
        api_key: Optional[str],
        timeout_seconds: float = 30.0,
        reasoning_effort: str = "none",
        reasoning_context: str = "current_turn",
        max_output_tokens: int = 1_024,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._reasoning_context = reasoning_context
        self._max_output_tokens = max_output_tokens
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

    @staticmethod
    def _error_code(exc: OpenAIError) -> Optional[str]:
        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            return None
        code = body.get("code")
        if isinstance(code, str):
            return code
        nested_error = body.get("error")
        if isinstance(nested_error, dict) and isinstance(nested_error.get("code"), str):
            return nested_error["code"]
        return None

    @staticmethod
    def _log_error(model: str, exc: OpenAIError) -> None:
        logger.warning(
            "OpenAI request failed: model=%s type=%s status=%s code=%s",
            model,
            type(exc).__name__,
            getattr(exc, "status_code", None),
            OpenAIResponsesClient._error_code(exc),
        )

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
                reasoning={
                    "effort": self._reasoning_effort,
                    "context": self._reasoning_context,
                },
                max_output_tokens=self._max_output_tokens,
            )
        except OpenAIConfigurationError:
            raise
        except SDKTimeoutError as exc:
            self._log_error(model, exc)
            raise OpenAITimeoutError("OpenAI API request timed out.") from exc
        except (AuthenticationError, PermissionDeniedError, NotFoundError) as exc:
            self._log_error(model, exc)
            raise OpenAIConfigurationError(
                "OpenAI credentials or model access were rejected."
            ) from exc
        except RateLimitError as exc:
            self._log_error(model, exc)
            if self._error_code(exc) in {"credit_balance_exhausted", "insufficient_quota"}:
                raise OpenAIQuotaError("OpenAI API credits are unavailable.") from exc
            raise OpenAIRateLimitError("OpenAI API rate limit exceeded.") from exc
        except SDKConnectionError as exc:
            self._log_error(model, exc)
            raise OpenAIConnectionError("OpenAI API is temporarily unreachable.") from exc
        except APIStatusError as exc:
            self._log_error(model, exc)
            raise OpenAIServiceError("OpenAI API returned an unsuccessful response.") from exc
        except OpenAIError as exc:
            self._log_error(model, exc)
            raise OpenAIServiceError("OpenAI API request failed.") from exc

        if response.status != "completed":
            logger.warning(
                "OpenAI response was not completed: model=%s response_id=%s status=%s",
                model,
                response.id,
                response.status,
            )
            raise OpenAIServiceError("OpenAI response was not completed.")

        content = (response.output_text or "").strip()
        usage = response.usage
        if not content:
            raise OpenAIServiceError("OpenAI returned an empty text response.")
        if usage is None:
            raise OpenAIServiceError("OpenAI response does not contain token usage.")

        input_details = usage.input_tokens_details
        output_details = usage.output_tokens_details
        cached_input_tokens = getattr(input_details, "cached_tokens", 0) or 0
        cache_write_tokens = getattr(input_details, "cache_write_tokens", 0) or 0
        reasoning_tokens = getattr(output_details, "reasoning_tokens", 0) or 0

        if cached_input_tokens + cache_write_tokens > usage.input_tokens:
            raise OpenAIServiceError("OpenAI response contains inconsistent token usage.")

        return OpenAIResult(
            content=content,
            response_id=response.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
        )
