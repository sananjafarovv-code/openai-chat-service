from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies import get_openai_client
from app.core.exceptions import OpenAIServiceError
from app.main import app
from app.services.openai_client import ChatMessage
from tests.conftest import FakeOpenAIClient


def create_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"title": "Test chat"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["model"] == "gpt-5.6-luna"
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


def test_unknown_model_returns_422(client: TestClient) -> None:
    response = client.post("/sessions", json={"model": "unknown-model"})

    assert response.status_code == 422
    assert "Pricing is not configured" in response.json()["detail"]


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
