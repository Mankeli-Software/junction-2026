"""Add product and query embeddings for the search vector experiment (#30)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 768 dimensions: Gemini embeddings at output_dimensionality 768 (technical-plan.md §5.4),
# within pgvector's 2,000-dimension HNSW limit.


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE product_embeddings (
            product_id text PRIMARY KEY REFERENCES products (id) ON DELETE CASCADE,
            model text NOT NULL,
            source_text text NOT NULL,
            embedding vector(768) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_product_embeddings_hnsw ON product_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    # Search reads query vectors only from here, so it never calls the API itself and the
    # same text always gives the same vector (docs/plans/30-product-search.md §7.11).
    op.execute(
        """
        CREATE TABLE query_embeddings (
            query_text text NOT NULL,
            model text NOT NULL,
            embedding vector(768) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (query_text, model)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_embeddings")
    op.execute("DROP TABLE IF EXISTS product_embeddings")
