"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2026-06-18 21:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Deals ─────────────────────────────────────────────────────────────
    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("iron_ingots", sa.Float(), server_default="0"),
        sa.Column("gold_ingots", sa.Float(), server_default="0"),
        sa.Column("diamond_items", sa.Float(), server_default="0"),
        sa.Column("iron_price", sa.Float(), server_default="0"),
        sa.Column("gold_price", sa.Float(), server_default="0"),
        sa.Column("diamond_price", sa.Float(), server_default="0"),
        sa.Column("market_value", sa.Float(), server_default="0"),
        sa.Column("offered_price", sa.Float(), server_default="0"),
        sa.Column("status", sa.Text(), server_default=""),
        sa.Column("profit", sa.Float(), server_default="0"),
        sa.Column("iron_amount", sa.Float(), server_default="0"),
        sa.Column("iron_unit", sa.Text(), server_default="ingot"),
        sa.Column("gold_amount", sa.Float(), server_default="0"),
        sa.Column("gold_unit", sa.Text(), server_default="ingot"),
        sa.Column("diamond_amount", sa.Float(), server_default="0"),
        sa.Column("diamond_unit", sa.Text(), server_default="ingot"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deals_timestamp", "deals", ["timestamp"])

    # ── Price cache ───────────────────────────────────────────────────────
    op.create_table(
        "price_cache",
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("item_name"),
    )

    # ── Stash ─────────────────────────────────────────────────────────────
    op.create_table(
        "stash",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), server_default="Default"),
        sa.Column("iron_blocks", sa.Integer(), server_default="0"),
        sa.Column("iron_ingots", sa.Integer(), server_default="0"),
        sa.Column("gold_blocks", sa.Integer(), server_default="0"),
        sa.Column("gold_ingots", sa.Integer(), server_default="0"),
        sa.Column("diamond_blocks", sa.Integer(), server_default="0"),
        sa.Column("diamond_items", sa.Integer(), server_default="0"),
        sa.Column("raw_iron_blocks", sa.Integer(), server_default="0"),
        sa.Column("raw_gold_blocks", sa.Integer(), server_default="0"),
        sa.Column("auto_subtract", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="stash_single_row"),
    )

    # ── Templates ─────────────────────────────────────────────────────────
    op.create_table(
        "templates",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("iron_ingots", sa.Float(), server_default="0"),
        sa.Column("gold_ingots", sa.Float(), server_default="0"),
        sa.Column("diamond_items", sa.Float(), server_default="0"),
        sa.Column("offered_price", sa.Float(), server_default="0"),
        sa.PrimaryKeyConstraint("name"),
    )

    # ── Price history ─────────────────────────────────────────────────────
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("iron_price", sa.Float(), server_default="0"),
        sa.Column("gold_price", sa.Float(), server_default="0"),
        sa.Column("diamond_price", sa.Float(), server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_history_timestamp", "price_history", ["timestamp"])


def downgrade() -> None:
    op.drop_table("price_history")
    op.drop_table("templates")
    op.drop_table("stash")
    op.drop_table("price_cache")
    op.drop_table("deals")