"""add orders, fills, and protection links

Revision ID: 0003_add_orders_and_fills
Revises: 0002_expand_symbol_length
Create Date: 2025-12-31 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_orders_and_fills"
down_revision = "0002_expand_symbol_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("qty", sa.Numeric(20, 8), nullable=True),
        sa.Column("filled_qty", sa.Numeric(20, 8), nullable=True),
        sa.Column("filled_avg_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("trail_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("broker_order_id", name="uq_orders_broker_order_id"),
    )
    op.create_index("ix_orders_profile_id", "orders", ["profile_id"])
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"])

    op.create_table(
        "fills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fills_profile_id", "fills", ["profile_id"])
    op.create_index("ix_fills_broker_order_id", "fills", ["broker_order_id"])

    op.create_table(
        "protection_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("entry_order_id", sa.String(length=128), nullable=False),
        sa.Column("protection_order_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entry_order_id", name="uq_protection_links_entry_order_id"),
    )
    op.create_index("ix_protection_links_profile_id", "protection_links", ["profile_id"])
    op.create_index("ix_protection_links_entry_order_id", "protection_links", ["entry_order_id"])


def downgrade() -> None:
    op.drop_index("ix_protection_links_entry_order_id", table_name="protection_links")
    op.drop_index("ix_protection_links_profile_id", table_name="protection_links")
    op.drop_table("protection_links")

    op.drop_index("ix_fills_broker_order_id", table_name="fills")
    op.drop_index("ix_fills_profile_id", table_name="fills")
    op.drop_table("fills")

    op.drop_index("ix_orders_broker_order_id", table_name="orders")
    op.drop_index("ix_orders_profile_id", table_name="orders")
    op.drop_table("orders")
