"""Add the web_sessions and access_tokens tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_web_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_web_sessions_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_web_sessions_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_web_sessions_user_id", "web_sessions", ["user_id"])
    op.create_table(
        "access_tokens",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("token_hash", name="pk_access_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_access_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "channel IN ('phone', 'web_chat', 'connector')", name="ck_access_tokens_channel"
        ),
    )
    op.create_index("ix_access_tokens_user_id", "access_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("access_tokens")
    op.drop_table("web_sessions")
