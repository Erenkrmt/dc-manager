"""Multi-company support — companies table, company_id FKs on all scoped tables.

Revision ID: 002
Revises: 001
Create Date: 2026-06-19 00:45:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── 1. Create companies table ──────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_id", sa.Text(), nullable=False),
        sa.Column("discord_username", sa.Text(), nullable=False),
        sa.Column("discord_avatar", sa.Text(), server_default=""),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), server_default=""),
        sa.Column("access_expires_at", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), server_default="1"),
        sa.Column("trial_used", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_id", name="uq_companies_discord_id"),
        sa.UniqueConstraint("api_key", name="uq_companies_api_key"),
    )

    # ── 2. Seed the legacy company (id=1) for existing data ────────────────
    op.execute(
        sa.text(
            """INSERT INTO companies (id, discord_id, discord_username, api_key, company_name,
                                     access_expires_at, is_active, trial_used, created_at, updated_at)
               VALUES (1, 'legacy', 'Legacy Admin', 'legacy_migration_key',
                       'Fishy Business (Legacy)', NULL, 1, 1, :now, :now)"""
        ).bindparams(now=now)
    )

    # ── 3. Add company_id to deals ─────────────────────────────────────────
    op.add_column(
        "deals",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_index("ix_deals_company_id", "deals", ["company_id"])

    # ── 4. Rework stash ────────────────────────────────────────────────────
    # Drop the old single-row CHECK constraint
    op.execute("ALTER TABLE stash DROP CONSTRAINT IF EXISTS stash_single_row")
    # Add company_id — seed 1 for any existing stash row
    op.add_column(
        "stash",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            server_default="1",
        ),
    )
    # Make id auto-increment (PostgreSQL handles this; SQLite needs recreate)
    # Add unique constraint per company
    op.create_unique_constraint("uq_stash_company", "stash", ["company_id"])

    # ── 5. Add company_id to templates ─────────────────────────────────────
    op.add_column(
        "templates",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            server_default="1",
        ),
    )
    # Drop old PK on name alone, create compound PK
    op.execute("ALTER TABLE templates DROP CONSTRAINT IF EXISTS templates_pkey")
    op.create_primary_key("pk_templates", "templates", ["name", "company_id"])

    # ── 6. Add company_id to price_history ─────────────────────────────────
    op.add_column(
        "price_history",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_index("ix_price_history_company_id", "price_history", ["company_id"])

    # ── 7. Add company_id to item_lookup_deals ─────────────────────────────
    op.add_column(
        "item_lookup_deals",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_index("ix_item_lookup_deals_company_id", "item_lookup_deals", ["company_id"])


def downgrade() -> None:
    # Reverse order
    op.drop_index("ix_item_lookup_deals_company_id", table_name="item_lookup_deals")
    op.drop_column("item_lookup_deals", "company_id")

    op.drop_index("ix_price_history_company_id", table_name="price_history")
    op.drop_column("price_history", "company_id")

    op.drop_constraint("pk_templates", "templates", type_="primary")
    op.drop_column("templates", "company_id")

    op.drop_constraint("uq_stash_company", "stash", type_="unique")
    op.drop_column("stash", "company_id")

    op.drop_index("ix_deals_company_id", table_name="deals")
    op.drop_column("deals", "company_id")

    op.drop_table("companies")
