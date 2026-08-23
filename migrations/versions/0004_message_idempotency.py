"""Add idempotency keys to successful message interactions.

Revision ID: 0004_message_idempotency
Revises: 0003_session_generations
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_message_idempotency"
down_revision: Optional[str] = "0003_session_generations"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    with op.batch_alter_table("usage_records") as batch_op:
        batch_op.add_column(
            sa.Column("idempotency_key", sa.String(length=100), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_usage_records_session_generation_idempotency_key",
            ["session_id", "generation", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_records") as batch_op:
        batch_op.drop_constraint(
            "uq_usage_records_session_generation_idempotency_key",
            type_="unique",
        )
        batch_op.drop_column("idempotency_key")
