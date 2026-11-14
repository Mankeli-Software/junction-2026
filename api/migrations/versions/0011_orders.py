"""Add the orders, order_lines and confirmation_acknowledgements tables (#47)

`confirmations` gets `original_quote_id` (the quote the link was sent for) and
`change_reason` (why the page last replaced its quote). `opened_at` and `used_at` are
there since 0005.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIRST_ORDER_SEQ = 1042


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete="CASCADE"
    )


def upgrade() -> None:
    op.add_column("confirmations", sa.Column("original_quote_id", sa.Text(), nullable=True))
    op.add_column("confirmations", sa.Column("change_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_confirmations_change_reason", "confirmations", "change_reason IN ('edit', 'requote')"
    )

    op.create_table(
        "confirmation_acknowledgements",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("flag_key", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("option_id", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_confirmation_acknowledgements"),
        _fk("confirmation_acknowledgements", "confirmation_id", "confirmations"),
        _fk("confirmation_acknowledgements", "quote_id", "quotes"),
        sa.UniqueConstraint(
            "confirmation_id",
            "flag_key",
            "text_hash",
            name="uq_confirmation_acknowledgements_confirmation_id",
        ),
    )
    op.create_index(
        "ix_confirmation_acknowledgements_confirmation_id",
        "confirmation_acknowledgements",
        ["confirmation_id"],
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True, start=FIRST_ORDER_SEQ), nullable=False
        ),
        sa.Column(
            "order_number",
            sa.Text(),
            sa.Computed("'D-' || seq::text", persisted=True),
            nullable=False,
        ),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("quote_hash", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.UniqueConstraint("seq", name="uq_orders_seq"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        sa.UniqueConstraint("confirmation_id", name="uq_orders_confirmation_id"),
        sa.UniqueConstraint("quote_id", name="uq_orders_quote_id"),
        _fk("orders", "confirmation_id", "confirmations"),
        _fk("orders", "quote_id", "quotes"),
        _fk("orders", "session_id", "sessions"),
        _fk("orders", "company_id", "companies"),
        _fk("orders", "user_id", "users"),
    )
    op.create_index("ix_orders_session_id", "orders", ["session_id"])
    op.create_index("ix_orders_company_id", "orders", ["company_id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])

    op.create_table(
        "order_lines",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("name_fi", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("sales_unit", sa.Text(), nullable=False),
        sa.Column("quantity_sales_units", sa.Integer(), nullable=False),
        sa.Column("unit_price_gross", sa.Numeric(12, 4), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("stock_status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("order_id", "line_id", name="pk_order_lines"),
        _fk("order_lines", "order_id", "orders"),
    )
    op.create_index("ix_order_lines_product_id", "order_lines", ["product_id"])


def downgrade() -> None:
    op.drop_table("order_lines")
    op.drop_table("orders")
    op.drop_table("confirmation_acknowledgements")
    op.drop_constraint("ck_confirmations_change_reason", "confirmations", type_="check")
    op.drop_column("confirmations", "change_reason")
    op.drop_column("confirmations", "original_quote_id")
