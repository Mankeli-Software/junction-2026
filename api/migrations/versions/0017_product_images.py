"""Product image URLs from our portal crawl (#108)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("image_match", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "image_match IN ('gtin', 'name')", name=op.f("ck_product_images_image_match")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_images_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_product_images")),
    )


def downgrade() -> None:
    op.drop_table("product_images")
