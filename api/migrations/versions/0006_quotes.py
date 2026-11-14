"""Add the sessions, quotes, quote_lines and interim audit_events tables

`audit_events` has no hash chain yet: #41 adds `payload_hash`, `prev_hash`,
`session_prev_hash` and `hash` together with the chain writer.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SESSION_STATES = (
    "in_conversation",
    "needs_clarification",
    "quote_ready",
    "awaiting_confirmation",
    "link_opened",
    "confirmed",
    "cancelled",
    "expired",
    "rejected",
    "sms_failed",
    "callback_requested",
    "requote_needed",
    "abandoned",
)
QUOTE_STATUSES = (
    "ready",
    "needs_clarification",
    "rejected",
    "pending_confirmation",
    "confirmed",
    "cancelled",
    "expired",
    "void",
)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _timestamp(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("call_id", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        _timestamp("state_since"),
        _timestamp("started_at"),
        _timestamp("last_activity_at"),
        _timestamp("ended_at", nullable=True),
        sa.Column("ended_by", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sessions_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("call_id", name="uq_sessions_call_id"),
        sa.CheckConstraint(
            _in("channel", ("phone", "web", "web_chat", "connector")), name="ck_sessions_channel"
        ),
        sa.CheckConstraint(_in("state", SESSION_STATES), name="ck_sessions_state"),
    )
    op.create_index("ix_sessions_company_id", "sessions", ["company_id"])
    op.create_index(
        "ix_sessions_user_channel_activity", "sessions", ["user_id", "channel", "last_activity_at"]
    )

    op.create_table(
        "quotes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_quote_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("quote_hash", sa.Text(), nullable=True),
        sa.Column("jws", sa.Text(), nullable=True),
        sa.Column("rules_ref", sa.Text(), nullable=False),
        _timestamp("issued_at"),
        _timestamp("expires_at", nullable=True),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("engine_input", postgresql.JSONB(), nullable=False),
        sa.Column("engine_output", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quotes"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_quotes_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_quotes_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_quote_id"],
            ["quotes.id"],
            name="fk_quotes_parent_quote_id_quotes",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in("status", QUOTE_STATUSES), name="ck_quotes_status"),
        sa.CheckConstraint(
            _in("decision", ("ready", "needs_clarification", "rejected")), name="ck_quotes_decision"
        ),
    )
    op.create_index("ix_quotes_session_id", "quotes", ["session_id"])
    op.create_index("ix_quotes_company_id", "quotes", ["company_id"])
    op.create_index("ix_quotes_parent_quote_id", "quotes", ["parent_quote_id"])

    op.create_table(
        "quote_lines",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("quantity_sales_units", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("stock_status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("quote_id", "line_id", name="pk_quote_lines"),
        sa.ForeignKeyConstraint(
            ["quote_id"], ["quotes.id"], name="fk_quote_lines_quote_id_quotes", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            _in("stock_status", ("verified", "unverified", "unavailable")),
            name="ck_quote_lines_stock_status",
        ),
    )
    op.create_index("ix_quote_lines_product_id", "quote_lines", ["product_id"])

    op.create_table(
        "audit_events",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("text_fi", sa.Text(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("public", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("seq", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_quote_id", "audit_events", ["quote_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("quote_lines")
    op.drop_table("quotes")
    op.drop_table("sessions")
