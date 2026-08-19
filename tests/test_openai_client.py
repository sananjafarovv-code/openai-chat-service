from types import SimpleNamespace

import httpx
from openai import APITimeoutError as SDKTimeoutError
from openai import RateLimitError
import pytest

from app.core.exceptions import (
    OpenAIConfigurationError,
    OpenAIQuotaError,
    OpenAIServiceError,
    OpenAITimeoutError,
)
from app.services.openai_client import ChatMessage, OpenAIResponsesClient


class FakeResponsesResource:
    def __init__(self, response: object = None, error: Exception = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


def build_client(resource: FakeResponsesResource) -> OpenAIResponsesClient:
    adapter = OpenAIResponsesClient(api_key="test-key")
    adapter._client = SimpleNamespace(responses=resource)  # type: ignore[assignment]
    return adapter


def test_adapter_sends_explicit_reasoning_and_extracts_detailed_usage() -> None:
    response = SimpleNamespace(
        id="resp_test",
        status="completed",
        output_text=" OK ",
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            input_tokens_details=SimpleNamespace(cached_tokens=40, cache_write_tokens=10),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )
    resource = FakeResponsesResource(response=response)

    result = build_client(resource).generate(
        "gpt-5.6-luna",
        [ChatMessage(role="user", content="hello")],
    )

    assert resource.kwargs == {
        "model": "gpt-5.6-luna",
        "input": [{"role": "user", "content": "hello"}],
        "store": False,
        "reasoning": {"effort": "none", "context": "current_turn"},
        "max_output_tokens": 1_024,
    }
    assert result.content == "OK"
    assert result.cached_input_tokens == 40
    assert result.cache_write_tokens == 10
    assert result.reasoning_tokens == 0


def test_adapter_rejects_incomplete_response() -> None:
    response = SimpleNamespace(
        id="resp_incomplete",
        status="incomplete",
        output_text="partial answer",
        usage=None,
    )

    with pytest.raises(OpenAIServiceError, match="was not completed"):
        build_client(FakeResponsesResource(response=response)).generate(
            "gpt-5.6-luna",
            [ChatMessage(role="user", content="hello")],
        )


def test_adapter_maps_exhausted_credits_without_exposing_upstream_message() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    sdk_error = RateLimitError(
        "sensitive upstream message",
        response=response,
        body={"code": "credit_balance_exhausted"},
    )

    with pytest.raises(OpenAIQuotaError, match="credits are unavailable"):
        build_client(FakeResponsesResource(error=sdk_error)).generate(
            "gpt-5.6-luna",
            [ChatMessage(role="user", content="hello")],
        )


def test_adapter_maps_timeout() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")

    with pytest.raises(OpenAITimeoutError):
        build_client(FakeResponsesResource(error=SDKTimeoutError(request))).generate(
            "gpt-5.6-luna",
            [ChatMessage(role="user", content="hello")],
        )


def test_adapter_requires_api_key_before_network_call() -> None:
    with pytest.raises(OpenAIConfigurationError):
        OpenAIResponsesClient(api_key=None).generate(
            "gpt-5.6-luna",
            [ChatMessage(role="user", content="hello")],
        )
