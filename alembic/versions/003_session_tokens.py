"""Add session_token and session_created_at columns to companies table.

Revision ID: 003
Revises: 002
Create Date: 2026-06-21 16:54:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add session_token if not already present (auto-migration may have added it)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("companies")]

    if "session_token" not in columns:
        op.add_column(
            "companies",
            sa.Column("session_token", sa.Text(), server_default=""),
        )

    if "session_created_at" not in columns:
        op.add_column(
            "companies",
            sa.Column("session_created_at", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("companies", "session_created_at")
    op.drop_column("companies", "session_token")
