"""import job reports

Revision ID: 0002_imports
Revises: 0001_init
Create Date: 2026-06-13

One row per staged object; rows sharing session_id form one user-facing upload report
(added vs skipped-duplicate counts for hands and tournaments).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_imports"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("hands_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hands_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tournaments_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tournaments_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("import_job")
