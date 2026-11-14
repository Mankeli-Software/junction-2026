"""The audit log, its dashboard pointers and the rule sets (#41, technical-plan.md §8.5, §8.6).

All three tables are append-only: a trigger refuses UPDATE, DELETE and TRUNCATE, and the
app's role (`simo_app` on the VM) has only INSERT and SELECT. Rows are written only through
`app.services.audit`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditEvent(Base):
    """One hash-chained event. The hash format is in docs/audit-chain.md."""

    __tablename__ = "audit_events"

    # Set by the writer under an advisory lock, so the chain has no gaps.
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    # No foreign keys, so the log never blocks or cascades with other tables.
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Null only when the payload was deleted after the event; the chain still checks.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    text_fi: Mapped[str | None] = mapped_column(Text)
    text_en: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_prev_hash: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    __table_args__ = (
        Index("ix_audit_events_session_id_seq", "session_id", "seq"),
        Index("ix_audit_events_quote_id", "quote_id"),
    )


class StatusEvent(Base):
    """A pointer to an audit event for the dashboard stream. Inserting one sends
    `NOTIFY status_events, '<id>'` (a trigger), which `PgListener` (#49) receives."""

    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    audit_seq: Mapped[int] = mapped_column(
        ForeignKey("audit_events.seq"), nullable=False, unique=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RuleSetRow(Base):
    """Each distinct rule set, stored once, so a quote can be replayed with its exact rules."""

    __tablename__ = "rule_sets"

    content_hash: Mapped[str] = mapped_column(Text, primary_key=True)  # RuleSet.content_hash
    version: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # SHA-256 of the RFC 8785 JSON of `rules`; the rule_set_loaded event carries it.
    rules_hash: Mapped[str] = mapped_column(Text, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
