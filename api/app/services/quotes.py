"""In-memory quote service on the stub engine. The persisted, signed service (#45) replaces it.

Quotes live in this process only, so a restart forgets them.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app import engine
from app.db import get_sessionmaker
from app.schemas import (
    BuildQuoteRequest,
    ConfirmationRequestResponse,
    Decision,
    EngineInput,
    GetOrderStatusRequest,
    HistorySummary,
    KitchenProfile,
    LineRequest,
    OrderStatusResponse,
    QuoteResponse,
    QuoteStatus,
    RequestConfirmationRequest,
    UpdateQuoteRequest,
)
from app.services import catalog, confirmations, customers
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError
from app.services.policy import get_rule_set

# The business clock of the demo (technical-plan.md §4.1): cutoffs and delivery dates.
BUSINESS_NOW = datetime.fromisoformat("2026-11-12T09:00:00+02:00")

# A quote can be replaced by an edit until it is confirmed, cancelled or expired.
_EDITABLE = {QuoteStatus.ready, QuoteStatus.pending_confirmation}


@dataclass
class _Stored:
    company_id: str
    quote: QuoteResponse
    replaced_by_quote_id: str | None = None


_quotes: dict[str, _Stored] = {}


def _get(caller: Caller, quote_id: str) -> _Stored:
    stored = _quotes.get(quote_id)
    if stored is None or stored.company_id != caller.company_id:
        raise NotFoundError("quote not found")
    return stored


def _new_quote(
    caller: Caller, lines: list[LineRequest], version: int, parent_quote_id: str | None
) -> QuoteResponse:
    output = engine.decide(
        EngineInput(
            lines=lines,
            kitchen=KitchenProfile(exclusions=caller.exclusions),
            history=HistorySummary(usual_items=customers.usual_items(caller), recent_lines=[]),
            candidates=catalog.candidates(lines),
            products=catalog.records(),
            offers=catalog.offers(),
            rules=get_rule_set(),
            business_now=BUSINESS_NOW,
            issued_at=datetime.now(UTC),
            lang=caller.lang,
        )
    )
    ready = output.decision == Decision.ready
    quote = QuoteResponse(
        **dict(output),
        quote_id=str(uuid.uuid4()),
        version=version,
        parent_quote_id=parent_quote_id,
        status=QuoteStatus.ready,
        expires_at=None,
        # Placeholder: #45 hashes the canonical JSON (RFC 8785) and signs it.
        quote_hash=hashlib.sha256(output.model_dump_json().encode()).hexdigest() if ready else None,
    )
    _quotes[quote.quote_id] = _Stored(company_id=caller.company_id, quote=quote)
    return quote


def build_quote(caller: Caller, request: BuildQuoteRequest) -> QuoteResponse:
    return _new_quote(caller, request.lines, version=1, parent_quote_id=None)


def update_quote(caller: Caller, request: UpdateQuoteRequest) -> QuoteResponse:
    """A new quote with the next version. The old one becomes `void`."""
    old = _get(caller, request.quote_id)
    if old.quote.status not in _EDITABLE:
        raise StateError(f"the quote is {old.quote.status.value} and can no longer be changed")
    quote = _new_quote(
        caller, request.lines, version=old.quote.version + 1, parent_quote_id=old.quote.quote_id
    )
    old.quote = old.quote.model_copy(update={"status": QuoteStatus.void})
    old.replaced_by_quote_id = quote.quote_id
    return quote


async def request_confirmation(
    caller: Caller, request: RequestConfirmationRequest
) -> ConfirmationRequestResponse:
    """Marks a ready quote as waiting for confirmation and sends the link to the caller's
    own inbox (#46, `app/services/confirmations.py`).

    Opens its own database session, because the MCP tools have none; the persisted quote
    service (#45) can take the request's session instead.
    """
    stored = _get(caller, request.quote_id)
    quote = stored.quote
    if quote.status != QuoteStatus.ready:
        raise StateError(
            f"the quote is {quote.status.value}; only a ready quote can be sent for confirmation"
        )
    if quote.decision != Decision.ready:
        raise StateError(
            f"the quote's decision is {quote.decision.value}; "
            "answer the question or change the lines with update_quote first"
        )
    # Marked before the first await, so a second request for the same quote gets a conflict.
    stored.quote = quote.model_copy(update={"status": QuoteStatus.pending_confirmation})
    try:
        async with get_sessionmaker()() as db:
            response = await confirmations.request_confirmation(db, caller, quote)
            await db.commit()
    except BaseException:
        stored.quote = quote
        raise
    return response


def get_order_status(caller: Caller, request: GetOrderStatusRequest) -> OrderStatusResponse:
    stored = _get(caller, request.quote_id)
    return OrderStatusResponse(
        quote_id=stored.quote.quote_id,
        status=stored.quote.status,
        order_number=None,
        replaced_by_quote_id=stored.replaced_by_quote_id,
    )
