"""Demo companies, their users and kitchen profiles (#44, minimal until #32).

The customer tables of `technical-plan.md` §5.2. #32 adds the seeded order history and
better company names on top.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, text
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
    """A person acting for a company. Each browser that types a number is its own user."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("lang IN ('fi', 'en')", name="lang"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_e164: Mapped[str] = mapped_column(Text, nullable=False)
    # Email and password come with the connector signup (#48).
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="fi")
    created_at: Mapped[datetime] = timestamp_now()
