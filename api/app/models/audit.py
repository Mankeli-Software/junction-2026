"""Interim audit log for #45, without the hash chain. #41 (Aku) owns the real one.

The columns are the ones #41 lists, minus `payload_hash`, `prev_hash`, `session_prev_hash`
and `hash`, which #41 adds together with the chain writer. `public` holds the public summary
that `app.services.audit.record()` is given. No foreign keys: the log is append-only and
must outlive what it describes.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # clock_timestamp(), not now(): events written in one transaction get distinct times.
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    text_fi: Mapped[str] = mapped_column(Text, nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    public: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
