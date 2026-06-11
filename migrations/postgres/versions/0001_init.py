"""initial app-state tables

Revision ID: 0001_init
Revises:
Create Date: 2026-06-11

App-owned mutable state. Identity/auth lives in Supabase GoTrue's `auth.users`; here we keep
a profile row keyed by that user id plus saved analysis filters.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "saved_filter",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("saved_filter")
    op.drop_table("user_profile")
