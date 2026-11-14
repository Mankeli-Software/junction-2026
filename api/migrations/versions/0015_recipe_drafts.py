"""Add the recipe_drafts table for ordering from a recipe photo (#80)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_drafts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("dish", sa.Text(), nullable=False),
        sa.Column("portions", sa.Integer(), nullable=False),
        sa.Column("servings_on_source", sa.Integer(), nullable=True),
        sa.Column("ingredients", postgresql.JSONB(), nullable=False),
        sa.Column("ai_reading", postgresql.JSONB(), nullable=True),
        sa.Column("matched_recipe_id", sa.Text(), nullable=True),
        sa.Column("image_sha256", sa.Text(), nullable=True),
        sa.Column("copied_from_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("confirmed_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recipe_drafts"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_recipe_drafts_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_recipe_drafts_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_recipe_drafts_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["copied_from_id"],
            ["recipe_drafts.id"],
            name="fk_recipe_drafts_copied_from_id_recipe_drafts",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("source IN ('notebook', 'dish_photo')", name="ck_recipe_drafts_source"),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'discarded')", name="ck_recipe_drafts_status"
        ),
        sa.CheckConstraint("portions BETWEEN 1 AND 1000", name="ck_recipe_drafts_portions"),
    )
    op.create_index("ix_recipe_drafts_session_id", "recipe_drafts", ["session_id"])
    op.create_index("ix_recipe_drafts_company_id", "recipe_drafts", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_recipe_drafts_company_id", table_name="recipe_drafts")
    op.drop_index("ix_recipe_drafts_session_id", table_name="recipe_drafts")
    op.drop_table("recipe_drafts")
