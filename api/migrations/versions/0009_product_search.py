"""Add the product search columns, indexes and refresh function (#30)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# unaccent() is only STABLE (it reads a dictionary), so it can't be used in an index.
# Naming the dictionary makes the wrapper safe to declare IMMUTABLE.
IMMUTABLE_UNACCENT = """
CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
RETURN public.unaccent('public.unaccent'::regdictionary, $1)
"""

# Not generated columns, because the category names live in another table. The brand is
# left out: it is already in the names, and counting it twice made "Valio" outrank the
# product words. The catalogue loader calls this at the end of its transaction
# (docs/plans/30-product-search.md §4).
REFRESH_PRODUCT_SEARCH = """
CREATE OR REPLACE FUNCTION refresh_product_search() RETURNS void
LANGUAGE sql AS $$
UPDATE products p SET
    search_fi = setweight(to_tsvector('finnish', p.name_fi), 'A')
        || setweight(to_tsvector('finnish', c.name_fi), 'C'),
    search_en = setweight(to_tsvector('english', coalesce(p.name_en, '')), 'A')
        || setweight(to_tsvector('english', c.name_en), 'C'),
    search_trgm = immutable_unaccent(lower(p.name_fi || ' ' || coalesce(p.name_en, '')))
FROM categories c
WHERE c.id = p.category_id
$$
"""


def upgrade() -> None:
    op.execute(IMMUTABLE_UNACCENT)
    op.add_column("products", sa.Column("search_fi", postgresql.TSVECTOR(), nullable=True))
    op.add_column("products", sa.Column("search_en", postgresql.TSVECTOR(), nullable=True))
    op.add_column("products", sa.Column("search_trgm", sa.Text(), nullable=True))
    op.execute(REFRESH_PRODUCT_SEARCH)
    op.execute("SELECT refresh_product_search()")
    op.create_index("ix_products_search_fi", "products", ["search_fi"], postgresql_using="gin")
    op.create_index("ix_products_search_en", "products", ["search_en"], postgresql_using="gin")
    op.create_index(
        "ix_products_search_trgm",
        "products",
        ["search_trgm"],
        postgresql_using="gin",
        postgresql_ops={"search_trgm": "gin_trgm_ops"},
    )
    # Brand words are left out of category inference (app/search/search.py).
    op.execute(
        "CREATE INDEX ix_products_brand_folded ON products (immutable_unaccent(lower(brand)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_brand_folded")
    op.drop_index("ix_products_search_trgm", table_name="products")
    op.drop_index("ix_products_search_en", table_name="products")
    op.drop_index("ix_products_search_fi", table_name="products")
    op.execute("DROP FUNCTION IF EXISTS refresh_product_search()")
    op.drop_column("products", "search_trgm")
    op.drop_column("products", "search_en")
    op.drop_column("products", "search_fi")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
