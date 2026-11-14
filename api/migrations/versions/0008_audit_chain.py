"""Chain the audit log and add status events and rule sets

Turns #45's interim `audit_events` into the hash chain of #41 (docs/audit-chain.md): the
writer sets `seq` and `at`, the hash columns are added, and `public` goes (the dashboard
is fully public and shows the whole redacted event). Rows already there are renumbered
without gaps and chained in their existing order, each with a status event.

All three tables are append-only (technical-plan.md §8.5): a trigger refuses UPDATE,
DELETE and TRUNCATE for every role, the owner included, and the app's role gets only
INSERT and SELECT. A trigger on status_events sends the NOTIFY the dashboard listens for.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.audit.chain import GENESIS_HASH, ChainFields, format_at, payload_hash

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_TABLES = ("audit_events", "status_events", "rule_sets")

# The app's database user on the VM (CLAUDE.md). Laptops connect as the owner and have none.
APP_ROLE = "simo_app"


def grant_append_only_sql(role: str) -> str:
    """Revoke everything the role may have through default privileges, then grant only
    INSERT and SELECT. Does nothing when the role doesn't exist."""
    tables = ", ".join(APPEND_ONLY_TABLES)
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON {tables} FROM {role};
                GRANT SELECT, INSERT ON {tables} TO {role};
            END IF;
        END
        $$;
    """


def upgrade() -> None:
    op.execute("ALTER TABLE audit_events ALTER COLUMN seq DROP IDENTITY")
    op.alter_column("audit_events", "at", server_default=None)
    for column in ("session_id", "payload", "text_fi", "text_en"):
        op.alter_column("audit_events", column, nullable=True)
    op.drop_column("audit_events", "public")
    for column in ("payload_hash", "prev_hash", "session_prev_hash", "hash"):
        op.add_column("audit_events", sa.Column(column, sa.Text(), nullable=True))

    op.create_table(
        "status_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("audit_seq", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_status_events"),
        sa.UniqueConstraint("audit_seq", name="uq_status_events_audit_seq"),
        sa.ForeignKeyConstraint(
            ["audit_seq"], ["audit_events.seq"], name="fk_status_events_audit_seq_audit_events"
        ),
    )

    _chain_existing_rows()

    for column in ("payload_hash", "prev_hash", "hash"):
        op.alter_column("audit_events", column, nullable=False)
    op.create_unique_constraint("uq_audit_events_hash", "audit_events", ["hash"])
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.create_index("ix_audit_events_session_id_seq", "audit_events", ["session_id", "seq"])

    op.create_table(
        "rule_sets",
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("rules_hash", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("content_hash", name="pk_rule_sets"),
    )

    op.execute(
        """
        CREATE FUNCTION refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION refuse_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()"
        )

    op.execute(
        """
        CREATE FUNCTION notify_status_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('status_events', NEW.id::text);
            RETURN NULL;
        END
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER status_events_notify AFTER INSERT ON status_events "
        "FOR EACH ROW EXECUTE FUNCTION notify_status_event()"
    )

    op.execute(grant_append_only_sql(APP_ROLE))


def _chain_existing_rows() -> None:
    """Renumber the interim rows 1, 2, 3... in their order and chain them."""
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT seq, at, type, actor, session_id, quote_id, payload, text_fi, text_en "
                "FROM audit_events ORDER BY seq"
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    bind.execute(sa.text("UPDATE audit_events SET seq = -seq"))
    prev_hash = GENESIS_HASH
    last_in_session: dict[str, str] = {}
    for new_seq, row in enumerate(rows, start=1):
        session = None if row["session_id"] is None else str(row["session_id"])
        digest = payload_hash(row["payload"], row["text_fi"], row["text_en"])
        fields = ChainFields(
            prev_hash=prev_hash,
            session_prev_hash=last_in_session.get(session) if session else None,
            seq=new_seq,
            at=format_at(row["at"]),
            type=row["type"],
            actor=row["actor"],
            session_id=session,
            quote_id=None if row["quote_id"] is None else str(row["quote_id"]),
            payload_hash=digest,
        )
        event_hash = fields.hash()
        bind.execute(
            sa.text(
                "UPDATE audit_events SET seq = :new, payload_hash = :ph, prev_hash = :prev, "
                "session_prev_hash = :sprev, hash = :h WHERE seq = :old"
            ),
            {
                "new": new_seq,
                "ph": digest,
                "prev": prev_hash,
                "sprev": fields.session_prev_hash,
                "h": event_hash,
                "old": -row["seq"],
            },
        )
        bind.execute(
            sa.text(
                "INSERT INTO status_events (audit_seq, session_id, type, at) "
                "VALUES (:seq, :sid, :type, :at)"
            ),
            {"seq": new_seq, "sid": row["session_id"], "type": row["type"], "at": row["at"]},
        )
        prev_hash = event_hash
        if session:
            last_in_session[session] = event_hash


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
    op.drop_table("status_events")
    op.drop_table("rule_sets")
    op.execute("DROP FUNCTION notify_status_event()")
    op.execute("DROP FUNCTION refuse_change()")

    # Events with no session or with a deleted payload don't fit the interim table.
    op.execute(
        "DELETE FROM audit_events WHERE session_id IS NULL OR payload IS NULL "
        "OR text_fi IS NULL OR text_en IS NULL"
    )
    op.drop_index("ix_audit_events_session_id_seq", table_name="audit_events")
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.drop_constraint("uq_audit_events_hash", "audit_events", type_="unique")
    for column in ("payload_hash", "prev_hash", "session_prev_hash", "hash"):
        op.drop_column("audit_events", column)
    op.add_column(
        "audit_events",
        sa.Column("public", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("audit_events", "public", server_default=None)
    for column in ("session_id", "payload", "text_fi", "text_en"):
        op.alter_column("audit_events", column, nullable=False)
    op.alter_column("audit_events", "at", server_default=sa.text("clock_timestamp()"))
    op.execute("ALTER TABLE audit_events ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY")
    op.execute(
        "SELECT setval(pg_get_serial_sequence('audit_events', 'seq'), "
        "COALESCE((SELECT max(seq) FROM audit_events), 0) + 1, false)"
    )
