"""Add company_members table + invite_code for multi-user per company.

Key design: 1 Discord user can belong to many companies.
UNIQUE constraint is on (company_id, discord_id), not on discord_id alone.

Revision ID: 004
Revises: 003
Create Date: 2026-06-21 18:35:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    columns = [col["name"] for col in inspector.get_columns("companies")]

    # 1. Add invite_code to companies table
    if "invite_code" not in columns:
        op.add_column("companies", sa.Column("invite_code", sa.Text(), server_default=""))
        conn.exec_driver_sql("UPDATE companies SET invite_code = '' WHERE invite_code IS NULL")

    # 2. Create company_members table
    if "company_members" not in tables:
        op.create_table(
            "company_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("discord_id", sa.Text(), nullable=False),
            sa.Column("discord_username", sa.Text(), nullable=False),
            sa.Column("discord_avatar", sa.Text(), default=""),
            sa.Column("role", sa.Text(), default="member"),  # 'owner', 'admin', 'member'
            sa.Column("session_token", sa.Text(), default=""),
            sa.Column("session_created_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("company_id", "discord_id", name="uq_company_member"),
        )

    # 3. Migrate existing companies → company_members (one owner row per company)
    # First check if old discord_id column still exists (SQLite auto-migration might have added both)
    old_cols = [col["name"] for col in inspector.get_columns("companies")]
    if "discord_id" in old_cols:
        result = conn.exec_driver_sql(
            "SELECT id, discord_id, discord_username, discord_avatar, "
            "session_token, session_created_at, created_at, updated_at "
            "FROM companies WHERE discord_id IS NOT NULL AND discord_id != ''"
        ).fetchall()

        existing = conn.exec_driver_sql(
            "SELECT company_id, discord_id FROM company_members"
        ).fetchall()
        existing_set = {(row[0], row[1]) for row in existing}

        for row in result:
            key = (row[0], row[1])
            if key not in existing_set:
                conn.exec_driver_sql(
                    """INSERT INTO company_members
                       (company_id, discord_id, discord_username, discord_avatar, role,
                        session_token, session_created_at, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, 'owner', %s, %s, %s, %s)""",
                    (row[0], row[1], row[2], row[3] or "", row[4] or "", row[5], row[6], row[7]),
                )

    # 4. Migrate session_token + session_created_at from companies to company_members
    # (They were previous columns on companies; now they live per-member)
    if "session_token" in old_cols and "session_created_at" in old_cols:
        # Data was already copied in step 3 if it existed
        pass  # We'll let the app's auto-migration handle cleanup

    logger = sa.logging.getLogger("alembic.runtime.migration")
    logger.info("Migration 004 complete: company_members table created.")


def downgrade() -> None:
    op.drop_table("company_members")
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("companies")]
    if "invite_code" in columns:
        op.drop_column("companies", "invite_code")