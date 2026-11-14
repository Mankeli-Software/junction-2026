"""Add the confirmations and sms_messages tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confirmations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("token_hash", sa.Text(), nullable=False),
        # No foreign key until #45 adds the quotes table.
        sa.Column("quote_id", sa.Text(), nullable=False),
        sa.Column("quote_hash", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_e164", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_confirmations"),
        sa.UniqueConstraint("token_hash", name="uq_confirmations_token_hash"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_confirmations_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_confirmations_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "channel IN ('phone', 'web', 'web_chat', 'connector')",
            name="ck_confirmations_channel",
        ),
    )
    op.create_index("ix_confirmations_quote_id", "confirmations", ["quote_id"])
    op.create_index("ix_confirmations_company_id", "confirmations", ["company_id"])
    op.create_index("ix_confirmations_user_id", "confirmations", ["user_id"])
    op.create_table(
        "sms_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sms_messages"),
        sa.ForeignKeyConstraint(
            ["confirmation_id"],
            ["confirmations.id"],
            name="fk_sms_messages_confirmation_id_confirmations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sms_messages_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("path IN ('inbox', 'twilio')", name="ck_sms_messages_path"),
        sa.CheckConstraint(
            "status IN ('held', 'delivered', 'queued', 'sent', 'failed')",
            name="ck_sms_messages_status",
        ),
    )
    op.create_index("ix_sms_messages_confirmation_id", "sms_messages", ["confirmation_id"])
    op.create_index("ix_sms_messages_user_id", "sms_messages", ["user_id"])


def downgrade() -> None:
    op.drop_table("sms_messages")
    op.drop_table("confirmations")
