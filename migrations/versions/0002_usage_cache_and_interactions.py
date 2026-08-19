"""Add interaction linkage and detailed token accounting.

Revision ID: 0002_usage_cache_and_interactions
Revises: 0001_initial_schema
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0002_usage_cache_and_interactions"
down_revision: Optional[str] = "0001_initial_schema"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def _backfill_interaction_ids() -> None:
    connection = op.get_bind()
    session_ids = connection.execute(
        sa.text(
            "SELECT session_id FROM messages UNION SELECT session_id FROM usage_records"
        )
    ).scalars()

    for session_id in session_ids:
        messages = list(
            connection.execute(
                sa.text(
                    "SELECT id FROM messages WHERE session_id = :session_id "
                    "ORDER BY sequence_number"
                ),
                {"session_id": session_id},
            ).scalars()
        )
        usage_ids = list(
            connection.execute(
                sa.text(
                    "SELECT id FROM usage_records WHERE session_id = :session_id "
                    "ORDER BY created_at, id"
                ),
                {"session_id": session_id},
            ).scalars()
        )

        interaction_ids: list[str] = []
        pair_count = max(len(usage_ids), (len(messages) + 1) // 2)
        for _ in range(pair_count):
            interaction_ids.append(str(uuid4()))

        for index, usage_id in enumerate(usage_ids):
            connection.execute(
                sa.text(
                    "UPDATE usage_records SET interaction_id = :interaction_id, "
                    "uncached_input_cost = input_cost, "
                    "cached_input_price_per_1m = 0.02, "
                    "cache_write_price_per_1m = 0.25 "
                    "WHERE id = :usage_id"
                ),
                {"interaction_id": interaction_ids[index], "usage_id": usage_id},
            )

        for index, message_id in enumerate(messages):
            connection.execute(
                sa.text(
                    "UPDATE messages SET interaction_id = :interaction_id WHERE id = :message_id"
                ),
                {
                    "interaction_id": interaction_ids[index // 2],
                    "message_id": message_id,
                },
            )


def upgrade() -> None:
    op.add_column("messages", sa.Column("interaction_id", sa.String(length=36), nullable=True))

    op.add_column("usage_records", sa.Column("interaction_id", sa.String(length=36), nullable=True))
    op.add_column(
        "usage_records",
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_records",
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_records",
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_records",
        sa.Column(
            "cached_input_price_per_1m",
            sa.Numeric(precision=18, scale=10),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usage_records",
        sa.Column(
            "cache_write_price_per_1m",
            sa.Numeric(precision=18, scale=10),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usage_records",
        sa.Column(
            "uncached_input_cost",
            sa.Numeric(precision=18, scale=10),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usage_records",
        sa.Column(
            "cached_input_cost",
            sa.Numeric(precision=18, scale=10),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usage_records",
        sa.Column(
            "cache_write_cost",
            sa.Numeric(precision=18, scale=10),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usage_records",
        sa.Column("long_context_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    _backfill_interaction_ids()

    with op.batch_alter_table("messages") as batch_op:
        batch_op.alter_column("interaction_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index(
            "ix_messages_session_interaction",
            ["session_id", "interaction_id"],
            unique=False,
        )

    with op.batch_alter_table("usage_records") as batch_op:
        batch_op.alter_column("interaction_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index(
            "ix_usage_records_interaction_id",
            ["interaction_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_records") as batch_op:
        batch_op.drop_index("ix_usage_records_interaction_id")
        batch_op.drop_column("long_context_applied")
        batch_op.drop_column("cache_write_cost")
        batch_op.drop_column("cached_input_cost")
        batch_op.drop_column("uncached_input_cost")
        batch_op.drop_column("cache_write_price_per_1m")
        batch_op.drop_column("cached_input_price_per_1m")
        batch_op.drop_column("reasoning_tokens")
        batch_op.drop_column("cache_write_tokens")
        batch_op.drop_column("cached_input_tokens")
        batch_op.drop_column("interaction_id")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_session_interaction")
        batch_op.drop_column("interaction_id")
