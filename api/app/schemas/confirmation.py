"""The confirmation page's view and action bodies (#47, technical-plan.md §9.4).

`GET /api/v1/confirmations/{token}` returns a `ConfirmationView`; the page's actions post
the bodies below. The page mirrors these in `web/src/lib/confirmation/types.ts`; keep the
two in step.

The view wraps the contract's quote models with the page state and the buyer's
acknowledgements. It never carries the token or the link.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .common import Lang, Localized, StrictModel
from .dashboard import Channel
from .quote import DeliverySummary, Flag, GroupSubtotal, NotOrdered, QuoteLine
from .tools import ExclusionLabel

# docs/specs/confirmation-page.md §3. "Updating" is shown by the page while an action
# runs, so it never comes from the server.
PageState = Literal["ready", "requote_needed", "confirmed", "cancelled", "expired", "invalid"]

# The largest quantity in sales units the buyer can set on one line (the page's stepper).
MAX_PAGE_QUANTITY = 10_000


class ViewFlag(Flag):
    """A contract flag plus what the confirmation adds to it."""

    # The code's `ack` in policy/messages.yaml; `choose` flags always need one.
    requires_ack: bool
    acknowledged_at: datetime | None
    # For `choose`: the option the current quote already reflects.
    current_option_id: str | None
    # New, or its text changed, since the buyer first saw the order, and not acknowledged.
    is_new: bool


class ConfirmationCompany(StrictModel):
    name: str


class ConfirmationSession(StrictModel):
    channel: Channel
    started_at: datetime


class ConfirmationQuote(StrictModel):
    quote_id: str
    version: int
    # Sent back with every action, so a stale tab can't act on an old quote.
    quote_hash: str
    total_cents: int
    delivery: DeliverySummary | None


class QuoteChange(StrictModel):
    """What changed compared with the previous quote, after an edit or a requote."""

    reason: Literal["edit", "requote"]
    previous_total_cents: int
    line_ids: list[str]  # lines that are new or changed
    text: Localized | None  # shown above the order for a requote


class AcknowledgedFlag(StrictModel):
    flag_key: str
    code: str
    at: datetime


class ConfirmedOrder(StrictModel):
    order_number: str  # "D-1042"
    confirmed_at: datetime
    acknowledged: list[AcknowledgedFlag]


class ConfirmationView(StrictModel):
    state: PageState
    lang: Lang  # the language of the call or chat; the page starts in it
    expires_at: datetime | None  # null while expiry is off (the event)
    company: ConfirmationCompany
    session: ConfirmationSession
    exclusions: list[ExclusionLabel]
    quote: ConfirmationQuote
    lines: list[QuoteLine]
    groups: list[GroupSubtotal]
    not_ordered: list[NotOrdered]
    flags: list[ViewFlag]
    change: QuoteChange | None
    order: ConfirmedOrder | None  # present once the order is confirmed


# --- Action bodies ----------------------------------------------------------------------


class AcknowledgeRequest(StrictModel):
    """`option_id` is the buyer's pick for a `choose` flag. An option that changes the
    order makes a new quote, with the flag acknowledged on it."""

    quote_hash: str
    flag_key: str
    option_id: str | None = None


class SetQuantityEdit(StrictModel):
    quote_hash: str
    op: Literal["set_quantity"]
    line_id: str
    quantity: int = Field(ge=1, le=MAX_PAGE_QUANTITY)  # in sales units


class RemoveLineEdit(StrictModel):
    quote_hash: str
    op: Literal["remove"]
    line_id: str


class ChooseAlternativeEdit(StrictModel):
    quote_hash: str
    op: Literal["choose_alternative"]
    line_id: str
    alternative_id: str  # a product id from the line's `alternatives`


EditRequest = Annotated[
    SetQuantityEdit | RemoveLineEdit | ChooseAlternativeEdit, Field(discriminator="op")
]


class ConfirmRequest(StrictModel):
    quote_hash: str


class CancelRequest(StrictModel):
    quote_hash: str


class ConfirmResponse(StrictModel):
    order_number: str
    confirmed_at: datetime


class ConfirmationErrorDetail(StrictModel):
    """The `detail` of a refused action: `{"detail": {"text": {...}, "line_id": ...}}`."""

    text: Localized
    line_id: str | None = None
