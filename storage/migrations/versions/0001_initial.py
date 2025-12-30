"""initial positions table

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(20, 8), nullable=False),
        sa.Column("unrealized_pl", sa.Numeric(20, 8), nullable=True),
        sa.Column("unrealized_plpc", sa.Numeric(20, 8), nullable=True),
        sa.Column("current_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("lastday_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("change_today", sa.Numeric(20, 8), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_positions_profile_id", "positions", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_positions_profile_id", table_name="positions")
    op.drop_table("positions")
