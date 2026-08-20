"""Add session generations for reset support.

Revision ID: 0003_session_generations
Revises: 0002_usage_cache_and_interactions
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_session_generations"
down_revision: Optional[str] = "0002_usage_cache_and_interactions"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "current_generation",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "usage_records",
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
    )

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint("uq_messages_session_sequence", type_="unique")
        batch_op.create_unique_constraint(
            "uq_messages_session_generation_sequence",
            ["session_id", "generation", "sequence_number"],
        )

    op.create_index(
        "ix_usage_records_session_generation",
        "usage_records",
        ["session_id", "generation"],
        unique=False,
    )


def _renumber_messages_for_legacy_constraint() -> None:
    connection = op.get_bind()
    session_ids = list(
        connection.execute(
            sa.text("SELECT DISTINCT session_id FROM messages")
        ).scalars()
    )

    for session_id in session_ids:
        message_ids = list(
            connection.execute(
                sa.text(
                    "SELECT id FROM messages WHERE session_id = :session_id "
                    "ORDER BY generation, sequence_number, created_at, id"
                ),
                {"session_id": session_id},
            ).scalars()
        )
        numbered_messages = list(enumerate(message_ids, start=1))
        for sequence_number, message_id in numbered_messages:
            connection.execute(
                sa.text(
                    "UPDATE messages SET sequence_number = :sequence_number "
                    "WHERE id = :message_id"
                ),
                {
                    "sequence_number": -sequence_number,
                    "message_id": message_id,
                },
            )
        for sequence_number, message_id in numbered_messages:
            connection.execute(
                sa.text(
                    "UPDATE messages SET sequence_number = :sequence_number "
                    "WHERE id = :message_id"
                ),
                {
                    "sequence_number": sequence_number,
                    "message_id": message_id,
                },
            )


def _restore_lifetime_session_totals() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE chat_sessions SET "
            "total_input_tokens = COALESCE(("
            "SELECT SUM(input_tokens) FROM usage_records "
            "WHERE usage_records.session_id = chat_sessions.id"
            "), 0), "
            "total_output_tokens = COALESCE(("
            "SELECT SUM(output_tokens) FROM usage_records "
            "WHERE usage_records.session_id = chat_sessions.id"
            "), 0), "
            "total_cost = COALESCE(("
            "SELECT SUM(total_cost) FROM usage_records "
            "WHERE usage_records.session_id = chat_sessions.id"
            "), 0)"
        )
    )


def downgrade() -> None:
    _renumber_messages_for_legacy_constraint()
    _restore_lifetime_session_totals()

    op.drop_index("ix_usage_records_session_generation", table_name="usage_records")
    with op.batch_alter_table("usage_records") as batch_op:
        batch_op.drop_column("generation")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint(
            "uq_messages_session_generation_sequence",
            type_="unique",
        )
        batch_op.drop_column("generation")
        batch_op.create_unique_constraint(
            "uq_messages_session_sequence",
            ["session_id", "sequence_number"],
        )

    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("current_generation")
