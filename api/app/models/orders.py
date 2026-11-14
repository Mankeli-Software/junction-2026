"""The order record (#47, technical-plan.md §8.4, vision §10).

An order exists only once the buyer confirmed it on the confirmation page. It copies the
confirmed quote's lines, so it stays readable whatever happens to the quote tables later.
No real order is sent to Valio.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now, uuid_pk

# The first order is D-1042, as in the design.
FIRST_ORDER_SEQ = 1042


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Sequential, from an identity column, so the app's role needs no sequence rights.
    seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True, start=FIRST_ORDER_SEQ), nullable=False, unique=True
    )
    # The readable number on the receipt and the dashboard: "D-1042".
    order_number: Mapped[str] = mapped_column(
        Text, Computed("'D-' || seq::text", persisted=True), nullable=False, unique=True
    )
    # One order per confirmation and per quote: a double tap can't make two.
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    quote_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = timestamp_now()


class OrderLine(Base):
    """One confirmed line, copied from the quote. Product ids are not foreign keys, as in
    `quote_lines`."""

    __tablename__ = "order_lines"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    line_id: Mapped[str] = mapped_column(Text, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name_fi: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    sales_unit: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_sales_units: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_gross: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    stock_status: Mapped[str] = mapped_column(Text, nullable=False)
