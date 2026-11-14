"""Mark the companies a live test run creates (#98)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("test_run", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "test_run")
