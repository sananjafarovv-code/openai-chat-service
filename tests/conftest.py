from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_openai_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.openai_client import ChatMessage, OpenAIResult


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def generate(self, model: str, messages: list[ChatMessage]) -> OpenAIResult:
        self.calls.append((model, list(messages)))
        call_number = len(self.calls)
        return OpenAIResult(
            content=f"Test assistant response {call_number}",
            response_id=f"resp_test_{call_number}",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )


@pytest.fixture
def fake_openai() -> FakeOpenAIClient:
    return FakeOpenAIClient()


@pytest.fixture
def client(fake_openai: FakeOpenAIClient) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_openai_client] = lambda: fake_openai

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
