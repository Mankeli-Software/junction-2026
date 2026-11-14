"""Confirmation requests and the messages that carry their links (#46, technical-plan.md §8.2).

A confirmation holds the SHA-256 of its link's token, never the token. The link itself is
in the `sms_messages` row of the simulated inbox, which is the phone that received it.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now, uuid_pk


class Confirmation(Base):
    """One confirmation link, sent to the account that made the order."""

    __tablename__ = "confirmations"
    __table_args__ = (
        CheckConstraint("channel IN ('phone', 'web', 'web_chat', 'connector')", name="channel"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # The current quote. No foreign key until #45 adds the `quotes` table.
    quote_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    quote_hash: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_e164: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_now()
    # Null while quotes don't expire (the event).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SmsMessage(Base):
    """One message per delivery path: `inbox` now, `twilio` later."""

    __tablename__ = "sms_messages"
    __table_args__ = (
        CheckConstraint("path IN ('inbox', 'twilio')", name="path"),
        # held: waiting for the call to end (phone channel). delivered: in the simulated
        # inbox. queued, sent, failed: Twilio's statuses, for the `twilio` path later.
        CheckConstraint(
            "status IN ('held', 'delivered', 'queued', 'sent', 'failed')", name="status"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # The whole SMS text, link included, as a phone would receive it.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # The same message split for the simulated phone: the text without the link, and the link.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_now()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
