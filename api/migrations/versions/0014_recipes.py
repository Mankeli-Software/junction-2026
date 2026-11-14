"""Add the recipe tables, product links and recipe embeddings (#34)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("default_portions", sa.Integer(), nullable=False),
        sa.Column("portion_unit", sa.Text(), nullable=False),
        sa.Column("default_portion_weight_g", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.SmallInteger(), nullable=True),
        sa.Column("is_inhouse", sa.Boolean(), nullable=False),
        sa.Column("loaded_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("search_fi", postgresql.TSVECTOR(), nullable=True),
        sa.Column("search_trgm", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
    )
    op.create_index("ix_recipes_search_fi", "recipes", ["search_fi"], postgresql_using="gin")
    op.create_index(
        "ix_recipes_search_trgm",
        "recipes",
        ["search_trgm"],
        postgresql_using="gin",
        postgresql_ops={"search_trgm": "gin_trgm_ops"},
    )
    op.create_table(
        "recipe_ingredients",
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("segment", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount_per_portion", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("suffix", sa.Text(), nullable=True),
        sa.Column("recipe_product_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ingredients_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recipe_id", "position", name=op.f("pk_recipe_ingredients")),
    )
    op.create_index(
        op.f("ix_recipe_ingredients_recipe_product_id"),
        "recipe_ingredients",
        ["recipe_product_id"],
    )
    op.create_table(
        "recipe_tags",
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("tag_group", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_tags_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recipe_id", "tag", name=op.f("pk_recipe_tags")),
    )
    # The diet and occasion filters look up recipes by tag.
    op.create_index("ix_recipe_tags_group_value", "recipe_tags", ["tag_group", "value"])
    op.create_table(
        "recipe_product_links",
        sa.Column("recipe_product_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("recipe_product_name", sa.Text(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("sales_unit", sa.Text(), nullable=False),
        sa.Column("base_unit", sa.Text(), nullable=False),
        sa.Column("units_per_sales_unit", sa.Numeric(), nullable=False),
        sa.Column("net_weight_kg", sa.Numeric(), nullable=True),
        sa.Column("weight_source", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("pack_hint", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "recipe_product_id", "product_id", name=op.f("pk_recipe_product_links")
        ),
    )
    # 768 dimensions like product_embeddings (0012): Gemini at output_dimensionality 768,
    # within pgvector's 2,000-dimension HNSW limit. The vectors come from a committed file
    # (data/recipe-embeddings.json.gz), so loading them never calls the API.
    op.execute(
        """
        CREATE TABLE recipe_embeddings (
            recipe_id integer PRIMARY KEY REFERENCES recipes (id) ON DELETE CASCADE,
            model text NOT NULL,
            source_hash text NOT NULL,
            embedding vector(768) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_recipe_embeddings_hnsw ON recipe_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recipe_embeddings")
    op.drop_table("recipe_product_links")
    op.drop_index("ix_recipe_tags_group_value", table_name="recipe_tags")
    op.drop_table("recipe_tags")
    op.drop_index(op.f("ix_recipe_ingredients_recipe_product_id"), table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
    op.drop_index("ix_recipes_search_trgm", table_name="recipes")
    op.drop_index("ix_recipes_search_fi", table_name="recipes")
    op.drop_table("recipes")
