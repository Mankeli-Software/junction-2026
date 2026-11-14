"""Add connector accounts and the OAuth tables for /mcp (#48)

Hand-out accounts start without a phone number and so without a company, so both
become nullable on users, together or not at all.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _scopes() -> sa.Column:
    return sa.Column(
        "scopes", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
    )


def _client_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["client_id"],
        ["oauth_clients.client_id"],
        name=f"fk_{table}_client_id_oauth_clients",
        ondelete="CASCADE",
    )


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=f"fk_{table}_user_id_users", ondelete="CASCADE"
    )


def upgrade() -> None:
    op.alter_column("users", "company_id", nullable=True)
    op.alter_column("users", "phone_e164", nullable=True)
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint(
        "ck_users_phone_company", "users", "(phone_e164 IS NULL) = (company_id IS NULL)"
    )
    op.create_check_constraint(
        "ck_users_unclaimed_email", "users", "phone_e164 IS NOT NULL OR email IS NOT NULL"
    )
    op.create_check_constraint("ck_users_email_lower", "users", "email = lower(email)")

    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret_hash", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "registration",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("client_id", name="pk_oauth_clients"),
    )
    op.create_table(
        "oauth_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        _scopes(),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_requests"),
        _client_fk("oauth_requests"),
    )
    op.create_table(
        "oauth_codes",
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        _scopes(),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("code_hash", name="pk_oauth_codes"),
        _client_fk("oauth_codes"),
        _user_fk("oauth_codes"),
    )
    op.create_index("ix_oauth_codes_user_id", "oauth_codes", ["user_id"])
    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _scopes(),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("token_hash", name="pk_oauth_refresh_tokens"),
        _client_fk("oauth_refresh_tokens"),
        _user_fk("oauth_refresh_tokens"),
    )
    op.create_index("ix_oauth_refresh_tokens_user_id", "oauth_refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("oauth_refresh_tokens")
    op.drop_table("oauth_codes")
    op.drop_table("oauth_requests")
    op.drop_table("oauth_clients")
    op.drop_constraint("ck_users_email_lower", "users", type_="check")
    op.drop_constraint("ck_users_unclaimed_email", "users", type_="check")
    op.drop_constraint("ck_users_phone_company", "users", type_="check")
    # Unclaimed hand-out accounts can't satisfy NOT NULL, so they go.
    op.execute("DELETE FROM users WHERE phone_e164 IS NULL")
    op.alter_column("users", "phone_e164", nullable=False)
    op.alter_column("users", "company_id", nullable=False)
