"""Sessions, quotes and quote lines (#45, `technical-plan.md` §5.2, §8.1, §9.7).

A session is one conversation: a phone call, or the tool calls of one MCP, WebMCP or chat
client with less than 10 minutes between them. Each quote belongs to one session. Edits
make a new quote with the next version; the old one becomes `void`.

The engine input (without the rule set, which `rules_ref` names) and the output are stored
with every quote, so any decision can be replayed (§2, §8.5). `quote_lines` repeats a few
fields of `engine_output` for queries and the dashboard.
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.schemas import Decision, QuoteStatus, SessionState, StockStatus

from .base import Base, timestamp_now, uuid_pk

# The caller's channel (`app.services.caller.Channel`), as in `access_tokens`.
CHANNELS = ("phone", "web", "web_chat", "connector")


def _in(column: str, values: Iterable[object]) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


class OrderSession(Base):
    """One conversation. `state` follows `docs/specs/dashboard.md` §4."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(_in("channel", CHANNELS), name="channel"),
        CheckConstraint(_in("state", SessionState), name="state"),
        Index("ix_sessions_user_channel_activity", "user_id", "channel", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    client_name: Mapped[str | None] = mapped_column(Text)
    call_id: Mapped[str | None] = mapped_column(Text, unique=True)  # phone only (#52)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    state_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(_in("status", QuoteStatus), name="status"),
        CheckConstraint(_in("decision", Decision), name="decision"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str | None] = mapped_column(Text)  # only when the decision is ready
    jws: Mapped[str | None] = mapped_column(Text)  # null until #40
    rules_ref: Mapped[str] = mapped_column(Text, nullable=False)  # RuleSet.ref
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    engine_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = timestamp_now()


class QuoteLine(Base):
    """One priced line of a quote.

    Product ids are not foreign keys, because the interim catalogue is a fixture (#30).
    """

    __tablename__ = "quote_lines"
    __table_args__ = (CheckConstraint(_in("stock_status", StockStatus), name="stock_status"),)

    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), primary_key=True
    )
    line_id: Mapped[str] = mapped_column(Text, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    quantity_sales_units: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    stock_status: Mapped[str] = mapped_column(Text, nullable=False)
