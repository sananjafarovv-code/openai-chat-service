from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings


def test_migrations_build_current_schema_from_scratch(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "0001_initial_schema")

    engine = create_engine(database_url)
    session_id = str(uuid4())
    user_message_id = str(uuid4())
    assistant_message_id = str(uuid4())
    usage_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO chat_sessions "
                "(id, model, title, total_input_tokens, total_output_tokens, total_cost, "
                "created_at, updated_at) VALUES "
                "(:id, 'gpt-5.6-luna', 'legacy', 10, 5, 0.000008, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": session_id},
        )
        connection.execute(
            text(
                "INSERT INTO messages "
                "(id, session_id, sequence_number, role, content, created_at) VALUES "
                "(:user_id, :session_id, 1, 'user', 'hello', CURRENT_TIMESTAMP), "
                "(:assistant_id, :session_id, 2, 'assistant', 'hi', CURRENT_TIMESTAMP)"
            ),
            {
                "user_id": user_message_id,
                "assistant_id": assistant_message_id,
                "session_id": session_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO usage_records "
                "(id, session_id, model, input_tokens, output_tokens, total_tokens, "
                "input_price_per_1m, output_price_per_1m, input_cost, output_cost, "
                "total_cost, openai_response_id, created_at) VALUES "
                "(:id, :session_id, 'gpt-5.6-luna', 10, 5, 15, 0.20, 1.20, "
                "0.000002, 0.000006, 0.000008, 'legacy_response', CURRENT_TIMESTAMP)"
            ),
            {"id": usage_id, "session_id": session_id},
        )

    command.upgrade(config, "head")

    inspector = inspect(engine)
    message_columns = {column["name"] for column in inspector.get_columns("messages")}
    usage_columns = {column["name"] for column in inspector.get_columns("usage_records")}

    assert "interaction_id" in message_columns
    assert {
        "interaction_id",
        "cached_input_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "long_context_applied",
    }.issubset(usage_columns)

    with engine.connect() as connection:
        message_interactions = list(
            connection.execute(
                text(
                    "SELECT interaction_id FROM messages WHERE session_id = :session_id "
                    "ORDER BY sequence_number"
                ),
                {"session_id": session_id},
            ).scalars()
        )
        usage_interaction = connection.execute(
            text("SELECT interaction_id FROM usage_records WHERE id = :usage_id"),
            {"usage_id": usage_id},
        ).scalar_one()

    assert message_interactions == [usage_interaction, usage_interaction]

    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
    get_settings.cache_clear()
