"""Add the catalogue tables loaded from the product file (#29)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allergen_codes",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("gs1_label", sa.Text(), nullable=False),
        sa.Column("gs1_uri", sa.Text(), nullable=False),
        sa.Column("eu_group", sa.Text(), nullable=True),
        sa.Column("name_fi", sa.Text(), nullable=True),
        sa.Column("name_fi_partitive", sa.Text(), nullable=True),
        sa.Column("voice_note_fi", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_allergen_codes")),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_fi", sa.Text(), nullable=False),
        sa.Column("name_fi_source", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("shop_path_fi", sa.Text(), nullable=True),
        sa.Column("mandate_group", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name_fi", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("name_sv", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Text(), nullable=False),
        sa.Column("sales_unit", sa.Text(), nullable=False),
        sa.Column("base_unit", sa.Text(), nullable=False),
        sa.Column("sales_unit_gtin", sa.Text(), nullable=True),
        sa.Column("synkka_gtin", sa.Text(), nullable=True),
        sa.Column("allowed_lot_size", sa.Numeric(), nullable=False),
        sa.Column("temperature_condition", sa.SmallInteger(), nullable=True),
        sa.Column("min_temperature", sa.Numeric(), nullable=True),
        sa.Column("max_temperature", sa.Numeric(), nullable=True),
        sa.Column("variable_unit", sa.Boolean(), nullable=True),
        sa.Column("vendor_name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("country_of_origin", sa.Text(), nullable=True),
        sa.Column("has_classifications", sa.Boolean(), nullable=False),
        sa.Column("source_updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("loaded_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_products_category_id_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_table(
        "product_allergens",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("containment", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "containment IN ('CONTAINS', 'MAY_CONTAIN', 'FREE_FROM', 'UNDECLARED')",
            name=op.f("ck_product_allergens_containment"),
        ),
        sa.ForeignKeyConstraint(
            ["code"], ["allergen_codes.code"], name=op.f("fk_product_allergens_code_allergen_codes")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_allergens_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "code", "containment", name=op.f("pk_product_allergens")
        ),
    )
    op.create_index(op.f("ix_product_allergens_code"), "product_allergens", ["code"], unique=False)
    op.create_table(
        "product_claims",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("claim_id", sa.Text(), nullable=False),
        sa.Column("qualifier", sa.Text(), nullable=False),
        sa.Column("synkka_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_claims_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "claim_id", "qualifier", name=op.f("pk_product_claims")
        ),
    )
    op.create_index(
        op.f("ix_product_claims_claim_id"), "product_claims", ["claim_id"], unique=False
    )
    op.create_table(
        "product_labels",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("label_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('temperature', 'certificate')", name=op.f("ck_product_labels_kind")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_labels_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "label_id", name=op.f("pk_product_labels")),
    )
    op.create_table(
        "product_substitutions",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("substitute_product_id", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_substitutions_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["substitute_product_id"],
            ["products.id"],
            name=op.f("fk_product_substitutions_substitute_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "substitute_product_id", name=op.f("pk_product_substitutions")
        ),
    )
    op.create_index(
        op.f("ix_product_substitutions_substitute_product_id"),
        "product_substitutions",
        ["substitute_product_id"],
        unique=False,
    )
    op.create_table(
        "product_unit_conversions",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("packaging_type", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=True),
        sa.Column("net_weight_g", sa.Numeric(), nullable=True),
        sa.Column("gross_weight_g", sa.Numeric(), nullable=True),
        sa.Column("volume_ml", sa.Numeric(), nullable=True),
        sa.Column("content_weight_g", sa.Numeric(), nullable=True),
        sa.Column("content_pieces", sa.Numeric(), nullable=True),
        sa.Column("width_mm", sa.Numeric(), nullable=True),
        sa.Column("length_mm", sa.Numeric(), nullable=True),
        sa.Column("height_mm", sa.Numeric(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_unit_conversions_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "packaging_type", name=op.f("pk_product_unit_conversions")
        ),
    )
    op.create_table(
        "product_units",
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("size_in_base_units", sa.Numeric(), nullable=False),
        sa.Column("gtin", sa.Text(), nullable=True),
        sa.Column("is_sales_unit", sa.Boolean(), nullable=False),
        sa.Column("is_base_unit", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_units_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "unit_id", name=op.f("pk_product_units")),
    )


def downgrade() -> None:
    op.drop_table("product_units")
    op.drop_table("product_unit_conversions")
    op.drop_index(
        op.f("ix_product_substitutions_substitute_product_id"), table_name="product_substitutions"
    )
    op.drop_table("product_substitutions")
    op.drop_table("product_labels")
    op.drop_index(op.f("ix_product_claims_claim_id"), table_name="product_claims")
    op.drop_table("product_claims")
    op.drop_index(op.f("ix_product_allergens_code"), table_name="product_allergens")
    op.drop_table("product_allergens")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("allergen_codes")
