"""Where the conversation's latest quote stands, read from the database each turn (#57).

The buyer may confirm, cancel or change the order on the confirmation page between two
chat messages. So before every turn the chat looks up its latest quote's real status:

- still open: it stays the latest quote;
- replaced by a newer version (an edit on the confirmation page voids it): the newest
  version becomes the latest, and the model is told the current quote id;
- confirmed, cancelled or expired: the conversation has no open quote any more, and the
  model is told in plain words that the previous order is closed, so it starts a new
  quote with `build_quote` instead of editing or resending the closed one.

One query in the usual case (the quote and its order number together); a replaced quote
takes one more per newer version.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Quote
from app.schemas import QuoteStatus

CLOSED = {
    QuoteStatus.confirmed: "confirmed",
    QuoteStatus.cancelled: "cancelled",
    QuoteStatus.expired: "expired",
}

CLOSED_NOTE = """

# The previous order
The buyer's previous order (quote {quote_id}) is {how}. It is closed: never change it with \
`update_quote` and never send it for confirmation again. Don't call it the current order. \
If the buyer orders something now, start a new quote with `build_quote`."""

REPLACED_NOTE = """

# The current quote
The buyer changed the order on the confirmation page. The current quote is now {quote_id}; \
use that id for `update_quote` and `request_confirmation`."""


@dataclass(frozen=True)
class Standing:
    open_quote_id: str | None  # the latest quote, while it is open
    note: str  # for the system prompt this turn; empty when there is nothing to say
    closed_quote_id: str | None = None


async def standing(
    db: AsyncSession, quote_id: str | None, *, now: datetime | None = None
) -> Standing:
    """The latest quote as it stands now, and what to tell the model about it."""
    now = now or datetime.now(UTC)
    if quote_id is None:
        return Standing(None, "")
    try:
        current = uuid.UUID(quote_id)
    except ValueError:
        return Standing(None, "")
    replaced = False
    while True:
        row = (
            await db.execute(
                select(Quote.status, Quote.expires_at, Order.order_number)
                .outerjoin(Order, Order.quote_id == Quote.id)
                .where(Quote.id == current)
            )
        ).one_or_none()
        if row is None:
            return Standing(None, "")
        status, expires_at, order_number = row
        if status != QuoteStatus.void:
            break
        newer = await db.scalar(
            select(Quote.id)
            .where(Quote.parent_quote_id == current)
            .order_by(Quote.version.desc())
            .limit(1)
        )
        if newer is None:  # voided without a newer version: nothing open
            return Standing(None, "")
        current, replaced = newer, True
    status = QuoteStatus(status)
    if status not in CLOSED and expires_at is not None and now >= expires_at:
        status = QuoteStatus.expired
    if status in CLOSED:
        how = CLOSED[status]
        if status == QuoteStatus.confirmed and order_number:
            how = f"confirmed by the buyer on the confirmation page, order number {order_number}"
        elif status == QuoteStatus.cancelled:
            how = "cancelled by the buyer on the confirmation page"
        return Standing(
            None, CLOSED_NOTE.format(quote_id=current, how=how), closed_quote_id=str(current)
        )
    note = REPLACED_NOTE.format(quote_id=current) if replaced else ""
    return Standing(str(current), note)
