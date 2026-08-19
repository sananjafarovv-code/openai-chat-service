from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_openai_client
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys, get_db
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
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(
    fake_openai: FakeOpenAIClient,
    db_engine: Engine,
) -> Generator[TestClient, None, None]:
    testing_session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

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
