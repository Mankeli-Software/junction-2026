"""Confirmation requests, the messages that carry their links (#46, technical-plan.md §8.2)
and the buyer's acknowledgements on the confirmation page (#47, §8.3).

A confirmation holds the SHA-256 of its link's token, never the token. The link itself is
in the `sms_messages` row of the simulated inbox, which is the phone that received it.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now, uuid_pk


class Confirmation(Base):
    """One confirmation link, sent to the account that made the order."""

    __tablename__ = "confirmations"
    __table_args__ = (
        CheckConstraint("channel IN ('phone', 'web', 'web_chat', 'connector')", name="channel"),
        CheckConstraint("change_reason IN ('edit', 'requote')", name="change_reason"),
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
    # The first time the link was opened.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When Confirm or Cancel used the link up. It stays readable as a receipt.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The quote the link was sent for, kept when edits repoint `quote_id`. A flag that was
    # not on it is new to the buyer. Filled on the first use of the link (#47).
    original_quote_id: Mapped[str | None] = mapped_column(Text)
    # Why `quote_id` last changed on the page: `edit` or `requote`; null before any change.
    change_reason: Mapped[str | None] = mapped_column(Text)


class ConfirmationAcknowledgement(Base):
    """The buyer ticked a flag on the confirmation page (technical-plan.md §8.3).

    Carries over to a new quote by `flag_key` while the flag's text stays the same
    (`text_hash`), so only new or changed flags need a new tick.
    """

    __tablename__ = "confirmation_acknowledgements"
    __table_args__ = (UniqueConstraint("confirmation_id", "flag_key", "text_hash"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    flag_key: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256 of the RFC 8785 JSON of the flag's text in both languages.
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    option_id: Mapped[str | None] = mapped_column(Text)  # the pick for a `choose` flag
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
