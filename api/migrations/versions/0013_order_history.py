"""Add the kitchen type and the seeded order history of demo companies (#32)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KITCHEN_TYPES = (
    "pizza_restaurant",
    "school_kitchen",
    "lunch_restaurant",
    "bar",
    "vegan_catering",
    "cafe",
    "tech_office",
)


def upgrade() -> None:
    # Null until the company is first used after this migration (#32): then it is chosen
    # from the phone number and the history is generated.
    op.add_column("companies", sa.Column("kitchen_type", sa.Text(), nullable=True))
    op.create_check_constraint(
        "kitchen_type",
        "companies",
        "kitchen_type IN (" + ", ".join(f"'{t}'" for t in KITCHEN_TYPES) + ")",
    )
    op.create_table(
        "order_history_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("product_id", sa.Text(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        # The history's own product when the kitchen's exclusions swapped it (milk -> oat drink).
        sa.Column("replaces_product_id", sa.Text(), sa.ForeignKey("products.id"), nullable=True),
        sa.CheckConstraint("quantity > 0", name="quantity"),
        sa.CheckConstraint("unit IN ('l', 'kg', 'piece', 'sales_unit')", name="unit"),
    )  # fmt: skip
    op.create_index(
        "ix_order_history_lines_company_ordered",
        "order_history_lines",
        ["company_id", "ordered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_order_history_lines_company_ordered", table_name="order_history_lines")
    op.drop_table("order_history_lines")
    op.drop_constraint("kitchen_type", "companies", type_="check")
    op.drop_column("companies", "kitchen_type")
