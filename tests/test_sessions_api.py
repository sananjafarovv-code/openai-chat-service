from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import time

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.api.dependencies import get_openai_client
from app.core.exceptions import (
    OpenAIConnectionError,
    OpenAIQuotaError,
    OpenAIRateLimitError,
    OpenAIServiceError,
    OpenAITimeoutError,
)
from app.main import app
from app.services.openai_client import ChatMessage, OpenAIResult
from tests.conftest import FakeOpenAIClient


def create_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"title": "Test chat"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["current_generation"] == 1
    assert payload["total_input_tokens"] == 0
    assert payload["total_output_tokens"] == 0
    assert payload["total_cost"] == "0E-10"
    return payload["id"]


def test_session_keeps_context_and_accumulates_usage(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
) -> None:
    session_id = create_session(client)

    first = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Hello"},
    )
    second = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "What did I say?"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["usage"]["total_cost"] == "0.0000080000"
    first_payload = first.json()
    interaction_id = first_payload["usage"]["interaction_id"]
    assert first_payload["user_message"]["interaction_id"] == interaction_id
    assert first_payload["assistant_message"]["interaction_id"] == interaction_id

    assert len(fake_openai.calls) == 2
    _, second_context = fake_openai.calls[1]
    assert [(message.role, message.content) for message in second_context] == [
        ("user", "Hello"),
        ("assistant", "Test assistant response 1"),
        ("user", "What did I say?"),
    ]

    detail = client.get(f"/sessions/{session_id}")

    assert detail.status_code == 200
    payload = detail.json()
    assert [message["sequence_number"] for message in payload["messages"]] == [1, 2, 3, 4]
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert len(payload["usage_records"]) == 2
    assert payload["total_input_tokens"] == 20
    assert payload["total_output_tokens"] == 10
    assert payload["total_cost"] == "0.0000160000"


def test_unknown_session_returns_404(client: TestClient) -> None:
    response = client.get("/sessions/missing")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_blank_message_returns_422(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "   "},
    )

    assert response.status_code == 422


def test_message_whitespace_is_preserved(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
) -> None:
    session_id = create_session(client)
    content = "  code block\n    nested line  "

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": content},
    )

    assert response.status_code == 200
    assert response.json()["user_message"]["content"] == content
    assert fake_openai.calls[0][1][-1].content == content


def test_database_connection_is_released_during_openai_call(
    client: TestClient,
    db_engine: Engine,
) -> None:
    session_id = create_session(client)

    class ConnectionInspectingOpenAIClient:
        def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
            assert db_engine.pool.checkedout() == 0
            return OpenAIResult(
                content="connection released",
                response_id="connection_released",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            )

    app.dependency_overrides[get_openai_client] = lambda: ConnectionInspectingOpenAIClient()

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "check the connection"},
    )

    assert response.status_code == 200


def test_unknown_model_returns_422(client: TestClient) -> None:
    response = client.post("/sessions", json={"model": "unknown-model"})

    assert response.status_code == 422
    assert "Pricing is not configured" in response.json()["detail"]


def test_blank_model_returns_422(client: TestClient) -> None:
    response = client.post("/sessions", json={"model": "   "})

    assert response.status_code == 422


def test_message_model_override_uses_effective_model_and_pricing(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
) -> None:
    session_id = create_session(client)

    overridden = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Use Terra once", "model": "gpt-5.6-terra"},
    )
    defaulted = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Return to the session default"},
    )

    assert overridden.status_code == 200
    assert overridden.json()["usage"]["model"] == "gpt-5.6-terra"
    assert overridden.json()["usage"]["total_cost"] == "0.0000800000"
    assert overridden.json()["session"]["model"] == "gpt-5.6-luna"
    assert defaulted.status_code == 200
    assert defaulted.json()["usage"]["model"] == "gpt-5.6-luna"
    assert [call[0] for call in fake_openai.calls] == [
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    ]


def test_unsupported_message_model_returns_422_without_openai_call(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Do not send this", "model": "unsupported-model"},
    )

    assert response.status_code == 422
    assert "Pricing is not configured" in response.json()["detail"]
    assert fake_openai.calls == []
    assert client.get(f"/sessions/{session_id}").json()["messages"] == []


def test_blank_message_model_returns_422(client: TestClient) -> None:
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "hello", "model": "   "},
    )

    assert response.status_code == 422


def test_reset_starts_clean_generation_and_preserves_archived_data(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
    db_engine: Engine,
) -> None:
    session_id = create_session(client)
    first = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "message before reset"},
    )

    reset = client.post(f"/sessions/{session_id}/reset")
    after_reset = client.get(f"/sessions/{session_id}")
    second = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "message after reset"},
    )

    assert first.status_code == 200
    assert reset.status_code == 200
    reset_payload = reset.json()
    assert reset_payload["id"] == session_id
    assert reset_payload["current_generation"] == 2
    assert reset_payload["total_input_tokens"] == 0
    assert reset_payload["total_output_tokens"] == 0
    assert reset_payload["total_cost"] == "0E-10"

    assert after_reset.status_code == 200
    assert after_reset.json()["messages"] == []
    assert after_reset.json()["usage_records"] == []

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["user_message"]["generation"] == 2
    assert second_payload["user_message"]["sequence_number"] == 1
    assert second_payload["assistant_message"]["sequence_number"] == 2
    assert [(message.role, message.content) for message in fake_openai.calls[1][1]] == [
        ("user", "message after reset"),
    ]

    with db_engine.connect() as connection:
        message_generations = list(
            connection.execute(
                text(
                    "SELECT generation FROM messages WHERE session_id = :session_id "
                    "ORDER BY generation, sequence_number"
                ),
                {"session_id": session_id},
            ).scalars()
        )
        usage_generations = list(
            connection.execute(
                text(
                    "SELECT generation FROM usage_records WHERE session_id = :session_id "
                    "ORDER BY generation"
                ),
                {"session_id": session_id},
            ).scalars()
        )

    assert message_generations == [1, 1, 2, 2]
    assert usage_generations == [1, 2]


def test_reset_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post("/sessions/missing/reset")

    assert response.status_code == 404


def test_reset_waits_for_inflight_message_then_starts_clean_generation(
    client: TestClient,
) -> None:
    session_id = create_session(client)

    class BlockingOpenAIClient:
        def __init__(self) -> None:
            self.started = Event()
            self.release = Event()

        def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
            self.started.set()
            if not self.release.wait(timeout=3):
                raise RuntimeError("Reset concurrency test timed out.")
            return OpenAIResult(
                content="completed before reset",
                response_id="before_reset",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            )

    blocking_openai = BlockingOpenAIClient()
    app.dependency_overrides[get_openai_client] = lambda: blocking_openai

    with ThreadPoolExecutor(max_workers=2) as executor:
        message_future = executor.submit(
            client.post,
            f"/sessions/{session_id}/messages",
            json={"content": "finish before reset"},
        )
        assert blocking_openai.started.wait(timeout=2)
        reset_future = executor.submit(client.post, f"/sessions/{session_id}/reset")

        time.sleep(0.1)
        assert reset_future.done() is False
        blocking_openai.release.set()
        message_response = message_future.result(timeout=3)
        reset_response = reset_future.result(timeout=3)

    assert message_response.status_code == 200
    assert reset_response.status_code == 200
    assert reset_response.json()["current_generation"] == 2
    detail = client.get(f"/sessions/{session_id}").json()
    assert detail["messages"] == []
    assert detail["usage_records"] == []
    assert detail["total_cost"] == "0E-10"


def test_openai_failure_does_not_save_partial_interaction(client: TestClient) -> None:
    session_id = create_session(client)

    class FailingOpenAIClient:
        def generate(self, model: str, messages: list[ChatMessage]) -> None:
            raise OpenAIServiceError("Simulated upstream failure.")

    app.dependency_overrides[get_openai_client] = lambda: FailingOpenAIClient()

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "This must not be persisted"},
    )
    detail = client.get(f"/sessions/{session_id}")

    assert response.status_code == 502
    assert detail.status_code == 200
    assert detail.json()["messages"] == []
    assert detail.json()["usage_records"] == []
    assert detail.json()["total_cost"] == "0E-10"


def test_different_sessions_keep_isolated_histories(
    client: TestClient,
    fake_openai: FakeOpenAIClient,
) -> None:
    first_session = create_session(client)
    second_session = create_session(client)

    assert client.post(
        f"/sessions/{first_session}/messages",
        json={"content": "first session"},
    ).status_code == 200
    assert client.post(
        f"/sessions/{second_session}/messages",
        json={"content": "second session"},
    ).status_code == 200
    assert client.post(
        f"/sessions/{first_session}/messages",
        json={"content": "continue first"},
    ).status_code == 200

    _, first_session_second_context = fake_openai.calls[2]
    assert [(message.role, message.content) for message in first_session_second_context] == [
        ("user", "first session"),
        ("assistant", "Test assistant response 1"),
        ("user", "continue first"),
    ]


def test_detailed_usage_is_persisted_and_priced(client: TestClient) -> None:
    session_id = create_session(client)

    class DetailedUsageOpenAIClient:
        def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
            return OpenAIResult(
                content="detailed response",
                response_id="detailed_response",
                input_tokens=100,
                cached_input_tokens=40,
                cache_write_tokens=10,
                output_tokens=20,
                reasoning_tokens=5,
                total_tokens=120,
            )

    app.dependency_overrides[get_openai_client] = lambda: DetailedUsageOpenAIClient()

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "detailed usage"},
    )

    assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["cached_input_tokens"] == 40
    assert usage["cache_write_tokens"] == 10
    assert usage["reasoning_tokens"] == 5
    assert usage["uncached_input_cost"] == "0.0000100000"
    assert usage["cached_input_cost"] == "8.000E-7"
    assert usage["cache_write_cost"] == "0.0000025000"
    assert usage["input_cost"] == "0.0000133000"
    assert usage["total_cost"] == "0.0000373000"

    stored_usage = client.get(f"/sessions/{session_id}").json()["usage_records"][0]
    assert stored_usage == usage


def test_parallel_messages_in_one_session_are_serialized(client: TestClient) -> None:
    session_id = create_session(client)

    class OrderedOpenAIClient:
        def __init__(self) -> None:
            self.first_started = Event()
            self.release_first = Event()
            self.guard = Lock()
            self.contexts: list[list[tuple[str, str]]] = []

        def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
            with self.guard:
                call_number = len(self.contexts) + 1
                self.contexts.append([(message.role, message.content) for message in messages])
            if call_number == 1:
                self.first_started.set()
                if not self.release_first.wait(timeout=3):
                    raise RuntimeError("Concurrency test timed out.")
            return OpenAIResult(
                content=f"ordered response {call_number}",
                response_id=f"ordered_{call_number}",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            )

    ordered_openai = OrderedOpenAIClient()
    app.dependency_overrides[get_openai_client] = lambda: ordered_openai

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            client.post,
            f"/sessions/{session_id}/messages",
            json={"content": "first concurrent message"},
        )
        assert ordered_openai.first_started.wait(timeout=2)
        second_future = executor.submit(
            client.post,
            f"/sessions/{session_id}/messages",
            json={"content": "second concurrent message"},
        )

        time.sleep(0.1)
        assert len(ordered_openai.contexts) == 1
        ordered_openai.release_first.set()
        first_response = first_future.result(timeout=3)
        second_response = second_future.result(timeout=3)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert ordered_openai.contexts[1] == [
        ("user", "first concurrent message"),
        ("assistant", "ordered response 1"),
        ("user", "second concurrent message"),
    ]

    detail = client.get(f"/sessions/{session_id}").json()
    assert [message["sequence_number"] for message in detail["messages"]] == [1, 2, 3, 4]
    assert len(detail["usage_records"]) == 2


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (OpenAIQuotaError("no credits"), 503),
        (OpenAIRateLimitError("rate limit"), 429),
        (OpenAITimeoutError("timeout"), 504),
        (OpenAIConnectionError("connection"), 503),
    ],
)
def test_specific_openai_errors_have_stable_http_statuses(
    client: TestClient,
    error: OpenAIServiceError,
    expected_status: int,
) -> None:
    session_id = create_session(client)

    class FailingOpenAIClient:
        def generate(self, model: str, messages: list[ChatMessage]) -> None:
            raise error

    app.dependency_overrides[get_openai_client] = lambda: FailingOpenAIClient()

    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "trigger expected error"},
    )

    assert response.status_code == expected_status
    assert client.get(f"/sessions/{session_id}").json()["messages"] == []
