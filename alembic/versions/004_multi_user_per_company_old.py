"""Add company_members table for multi-user per company support.

Revision ID: 004
Revises: 003
Create Date: 2026-06-21 18:30:00.000000
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

    if "company_members" not in tables:
        op.create_table(
            "company_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("discord_id", sa.Text(), unique=True, nullable=False),
            sa.Column("discord_username", sa.Text(), nullable=False),
            sa.Column("discord_avatar", sa.Text(), default=""),
            sa.Column("role", sa.Text(), default="member"),  # 'owner', 'admin', 'member'
            sa.Column("session_token", sa.Text(), default=""),
            sa.Column("session_created_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
        )

    # Migrate existing companies -> company_members (one owner row per company)
    if "company_members" in op.get_bind().dialect.server_version_info or "company_members" not in tables:
        # Check if there are existing companies that need migration
        result = conn.exec_driver_sql(
            "SELECT id, discord_id, discord_username, discord_avatar, "
            "session_token, session_created_at, created_at, updated_at "
            "FROM companies WHERE discord_id != ''"
        )
        existing_members = conn.exec_driver_sql(
            "SELECT discord_id FROM company_members"
        ).fetchall()
        existing_discord_ids = {row[0] for row in existing_members}

        for row in result:
            if row[1] not in existing_discord_ids:
                conn.exec_driver_sql(
                    """INSERT INTO company_members
                       (company_id, discord_id, discord_username, discord_avatar, role,
                        session_token, session_created_at, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, 'owner', %s, %s, %s, %s)""",
                    (row[0], row[1], row[2], row[3] or "", row[4] or "", row[5], row[6], row[7]),
                )


def downgrade() -> None:
    op.drop_table("company_members")