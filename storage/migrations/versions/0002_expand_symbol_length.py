"""expand symbol length for option tickers

Revision ID: 0002_expand_symbol_length
Revises: 0001_initial
Create Date: 2025-12-30 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_expand_symbol_length"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as batch_op:
        batch_op.alter_column(
            "symbol",
            existing_type=sa.String(length=16),
            type_=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("positions") as batch_op:
        batch_op.alter_column(
            "symbol",
            existing_type=sa.String(length=64),
            type_=sa.String(length=16),
            nullable=False,
        )
