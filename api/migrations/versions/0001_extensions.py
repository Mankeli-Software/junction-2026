"""Enable the vector, pg_trgm and unaccent extensions

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("vector", "pg_trgm", "unaccent")


def upgrade() -> None:
    for name in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {name}")


def downgrade() -> None:
    for name in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {name}")
