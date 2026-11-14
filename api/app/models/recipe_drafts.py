"""Recipe drafts (#80, docs/plans/80-recipe-photo.md §4).

A recipe read from a photo (or proposed by a connector's own model), which the buyer checks,
edits and confirms before it can be quoted. A confirmed draft is frozen: changing it means
a new draft, which keeps the audit trail honest. The photo itself is never stored, only
the SHA-256 of the normalised image.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now, uuid_pk

SOURCES = ("notebook", "dish_photo")
STATUSES = ("draft", "confirmed", "discarded")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RecipeDraftRow(Base):
    __tablename__ = "recipe_drafts"
    __table_args__ = (
        CheckConstraint(_in("source", SOURCES), name="source"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint("portions BETWEEN 1 AND 1000", name="portions"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    dish: Mapped[str] = mapped_column(Text, nullable=False)
    portions: Mapped[int] = mapped_column(Integer, nullable=False)
    servings_on_source: Mapped[int | None] = mapped_column(Integer)
    # DraftIngredient[] as edited, not scaled.
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # A dish photo that matched one of our recipes starts from that recipe; what the AI saw
    # is kept here for the card's "Use what the AI saw instead":
    # {"servings_on_source": int | None, "ingredients": DraftIngredient[]}.
    ai_reading: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    matched_recipe_id: Mapped[str | None] = mapped_column(Text)
    image_sha256: Mapped[str | None] = mapped_column(Text)  # webshop chat only
    # "Edit as new draft": the confirmed draft this one was copied from.
    copied_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recipe_drafts.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)  # bumped on each edit
    # SHA-256 of the canonical confirmed content, which a quote from the draft stores.
    confirmed_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp_now()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
