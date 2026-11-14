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
