"""Demo companies, their users, kitchen profiles and order history (#44, #32).

The customer tables of `technical-plan.md` §5.2. #32 adds the seeded order history and
better company names on top.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now, uuid_pk


class Company(Base):
    """One generated demo company per phone number (`call-screen.md` §2.2)."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    phone_e164: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = timestamp_now()
    # Chosen from the number on first use (#32); null for a company created before that.
    kitchen_type: Mapped[str | None] = mapped_column(Text)
    # The run id of the live test that created it (`X-Simo-Test-Run`, #98). Its sessions
    # stay off the public dashboard's overview and stream.
    test_run: Mapped[str | None] = mapped_column(Text)


class KitchenProfile(Base):
    """The company's exclusions (keys of `policy/allergen_rules.yaml`). Last write wins."""

    __tablename__ = "kitchen_profiles"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    exclusions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    updated_at: Mapped[datetime] = timestamp_now()


class User(Base):
    """A person acting for a company. Each browser that types a number is its own user.

    A connector account (#48) also has an email and a password. A hand-out account starts
    unclaimed: no phone number and so no company until its first login asks for the number.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("lang IN ('fi', 'en')", name="lang"),
        # The number and the company come together; only an email account may lack them.
        CheckConstraint("(phone_e164 IS NULL) = (company_id IS NULL)", name="phone_company"),
        CheckConstraint("phone_e164 IS NOT NULL OR email IS NOT NULL", name="unclaimed_email"),
        CheckConstraint("email = lower(email)", name="email_lower"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    phone_e164: Mapped[str | None] = mapped_column(Text)
    # Email (lower-cased) and an argon2 password hash for connector accounts (#48).
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="fi")
    created_at: Mapped[datetime] = timestamp_now()


class OrderHistoryLine(Base):
    """One line of a demo company's seeded order history (#32, `docs/plans/61-order-history.md`).

    Regenerated, not edited: the same number, type and exclusions always give the same lines.
    """

    __tablename__ = "order_history_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("unit IN ('l', 'kg', 'piece', 'sales_unit')", name="unit"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The history's own product when the kitchen's exclusions swapped it (milk -> oat drink).
    replaces_product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
