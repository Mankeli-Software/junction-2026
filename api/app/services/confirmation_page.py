"""The confirmation page's backend (#47, technical-plan.md §8.3, §8.4, §9.4).

The page `/c/<token>` is the only place an order can be confirmed. The token in the path
is the authorisation: whoever holds the link can open the page and act on it, with no
login (`docs/specs/confirmation-page.md` §2). The token is looked up by its SHA-256 and
never stored, logged or written into an event.

- `get_view()` never uses the token up. The first open sets `opened_at` and writes
  `link_opened`. After Confirm or Cancel it stays readable as the receipt.
- Every action sends the hash of the quote on screen, so a stale tab can't act on an old
  version (409).
- Edits, and a `choose` option that changes the order, go through `quotes.replace_quote()`:
  a new quote with the next version, the old one void, and the confirmation repointed to
  the new one. An edit the engine can't fulfil is refused (422) and changes nothing.
- Acknowledgements carry over to a new quote by flag key while the flag's text stays the
  same, so only new or changed flags need a new tick.
- Confirm re-checks the availability of the quote's products through the Valio adapter
  and the engine. If it got worse, the quote is replaced and the page shows the new one
  (409). Otherwise the order is created.
- Confirm and Cancel use the link up (`used_at`), and both are idempotent, so a double tap
  or a second tab can't make two orders.

Like the other services, these functions take the request's `AsyncSession` and only
flush: the caller commits, also after a `ConfirmationRefused` (a requote must be kept).
"""

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import rfc8785
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.adapters import valio
from app.models import (
    Company,
    Confirmation,
    ConfirmationAcknowledgement,
    Order,
    OrderLine,
    OrderSession,
    Quote,
)
from app.schemas import (
    AcknowledgedFlag,
    AcknowledgeRequest,
    CancelRequest,
    Channel,
    ChooseAlternativeEdit,
    Clarification,
    ConfirmationCompany,
    ConfirmationErrorDetail,
    ConfirmationQuote,
    ConfirmationSession,
    ConfirmationView,
    ConfirmedOrder,
    ConfirmRequest,
    ConfirmResponse,
    Decision,
    EngineInput,
    EngineOutput,
    Exclusion,
    Flag,
    LineRequest,
    Localized,
    Offer,
    PageState,
    QuoteChange,
    QuoteLine,
    QuoteResponse,
    QuoteStatus,
    RemoveLineEdit,
    RuleSet,
    SessionState,
    SetQuantityEdit,
    StockStatus,
    ViewFlag,
)
from app.services import accounts, audit, customers, quotes, sessions
from app.services.caller import Caller
from app.services.errors import NotFoundError, ServiceError, StateError
from app.services.policy import get_rule_set
from app.services.tokens import hash_token


class ConfirmationRefused(ServiceError):
    """The page's action was refused. `status` follows technical-plan.md §9.4: 409 stale or
    closed, or availability got worse; 410 expired; 422 not possible or a flag unchecked."""

    def __init__(self, status: int, text: Localized, line_id: str | None = None):
        super().__init__(text.en)
        self.status = status
        self.text = text
        self.line_id = line_id

    def detail(self) -> ConfirmationErrorDetail:
        return ConfirmationErrorDetail(text=self.text, line_id=self.line_id)


# --- Texts ------------------------------------------------------------------------------

STALE = Localized(
    fi="Tilaus muuttui toisessa ikkunassa. Tämä on uusin versio.",
    en="The order changed in another window. This is the latest version.",
)
CLOSED = Localized(fi="Tämä tilaus on jo käsitelty.", en="This order is already closed.")
EXPIRED = Localized(
    fi="Tämä tarjous on vanhentunut. Mitään ei tilattu.",
    en="This quote has expired. Nothing was ordered.",
)
UNCHECKED = Localized(fi="Tarkista merkityt kohdat ensin.", en="Check the flagged items first.")
NOTHING_TO_ORDER = Localized(
    fi="Tilauksessa ei ole mitään tilattavaa.", en="There is nothing to order."
)
REQUOTE = Localized(
    fi="Saatavuus muuttui tarjouksen jälkeen. Tässä päivitetty tilaus.",
    en="Stock changed since the quote. Here is the updated order.",
)
UNKNOWN_FLAG = Localized(
    fi="Tätä kohtaa ei ole enää tilauksessa.", en="This item is no longer on the order."
)
UNKNOWN_OPTION = Localized(fi="Valitse yksi vaihtoehdoista.", en="Choose one of the options.")
UNKNOWN_LINE = Localized(
    fi="Tätä riviä ei ole enää tilauksessa.", en="This line is no longer on the order."
)
LAST_LINE = Localized(
    fi="Tämä on tilauksen ainoa rivi. Jos et halua tilata mitään, peru tilaus.",
    en="This is the only line. To order nothing, cancel the order.",
)
NOT_OFFERED = Localized(
    fi="Tätä tuotetta ei tarjottu tälle riville.", en="This product was not offered for this line."
)
TOO_MUCH = Localized(fi="Määrä on liian suuri.", en="That amount is too large.")

# Caller channels (`app.services.caller.Channel`) as the page and the dashboard name them.
_CHANNELS = {
    "phone": Channel.phone,
    "web": Channel.webmcp,
    "web_chat": Channel.web_chat,
    "connector": Channel.mcp,
}
# Statuses of a quote the buyer can still act on. `needs_clarification` and `rejected`
# only after a requote at confirm that the engine could not fulfil.
_OPEN = {
    QuoteStatus.pending_confirmation,
    QuoteStatus.ready,
    QuoteStatus.needs_clarification,
    QuoteStatus.rejected,
}
_STOCK_RANK = {StockStatus.verified: 0, StockStatus.unverified: 1, StockStatus.unavailable: 2}
# A `choose` option with this id keeps the order as it is. Any other option is
# `<kind>:<product_id>` and puts that product on the flag's line (e.g. `exact:464119`).
KEEP_OPTION = "keep"


# --- The view ---------------------------------------------------------------------------


async def get_view(
    db: AsyncSession, token: str, *, now: datetime | None = None
) -> ConfirmationView | None:
    """The page for this token, or None for an unknown one. Never uses the token up."""
    now = now or datetime.now(UTC)
    confirmation = await _find(db, token)
    if confirmation is None:
        return None
    quote = await _current_quote(db, confirmation)
    await _mark_opened(db, confirmation, quote, now)
    return await _view(db, confirmation, quote, now)


async def _view(
    db: AsyncSession, confirmation: Confirmation, quote: Quote, now: datetime
) -> ConfirmationView:
    output = _output(quote)
    session = await db.get_one(OrderSession, quote.session_id)
    company = await db.get_one(Company, quote.company_id)
    order = await _order(db, confirmation)
    flags = await _view_flags(db, confirmation, quote, output)
    state = _state(confirmation, quote, order, now)
    exclusions = [Exclusion(e) for e in quote.engine_input["kitchen"]["exclusions"]]
    return ConfirmationView(
        state=state,
        lang=quote.engine_input["lang"],
        expires_at=quote.expires_at,
        company=ConfirmationCompany(name=company.name),
        session=ConfirmationSession(
            channel=_CHANNELS[session.channel], started_at=session.started_at
        ),
        exclusions=customers.exclusion_labels(exclusions),
        quote=ConfirmationQuote(
            quote_id=str(quote.id),
            version=quote.version,
            quote_hash=_screen_hash(quote),
            total_cents=quote.total_cents,
            delivery=output.delivery,
        ),
        lines=output.lines,
        groups=output.groups,
        not_ordered=output.not_ordered,
        flags=flags,
        change=await _change(db, confirmation, quote, output)
        if state in ("ready", "requote_needed")
        else None,
        order=_receipt(order, flags) if order is not None else None,
    )


def _state(
    confirmation: Confirmation, quote: Quote, order: Order | None, now: datetime
) -> PageState:
    if order is not None:
        return "confirmed"
    status = QuoteStatus(quote.status)
    if status == QuoteStatus.cancelled:
        return "cancelled"
    if status == QuoteStatus.expired or (quote.expires_at is not None and now >= quote.expires_at):
        return "expired"
    if status in _OPEN:
        return "requote_needed" if confirmation.change_reason == "requote" else "ready"
    # Void: the agent replaced the quote with update_quote; its new quote needs a new link.
    return "invalid"


async def _view_flags(
    db: AsyncSession, confirmation: Confirmation, quote: Quote, output: EngineOutput
) -> list[ViewFlag]:
    rules = await _rules(db, quote.rules_ref)
    acks = await _acknowledgements(db, confirmation)
    seen: set[tuple[str, str]] = set()
    original = confirmation.original_quote_id
    if original is not None and original != str(quote.id):
        first = await db.get(Quote, uuid.UUID(original))
        if first is not None:
            seen = {(f.flag_key, text_hash(f.text)) for f in _output(first).flags}
    lines = {line.line_id: line for line in output.lines}
    flags = []
    for flag in output.flags:
        key = (flag.flag_key, text_hash(flag.text))
        acknowledged_at = acks.get(key)
        is_first_quote = original is None or original == str(quote.id)
        flags.append(
            ViewFlag(
                **flag.model_dump(),
                requires_ack=flag.kind == "choose" or _ack_setting(rules, flag.code),
                acknowledged_at=acknowledged_at,
                current_option_id=_current_option(flag, lines),
                is_new=not is_first_quote and key not in seen and acknowledged_at is None,
            )
        )
    return flags


def _ack_setting(rules: RuleSet, code: str) -> bool:
    """The code's `ack` in policy/messages.yaml. An unknown code needs a tick, to be safe."""
    message = rules.messages.get(code)  # type: ignore[call-overload]
    return True if message is None or message.ack is None else message.ack


def _current_option(flag: Flag, lines: dict[str, QuoteLine]) -> str | None:
    """For `choose`: the option the current quote already reflects."""
    if flag.kind != "choose" or not flag.options:
        return None
    ids = [option.option_id for option in flag.options]
    if KEEP_OPTION in ids:
        return KEEP_OPTION
    line = lines.get(flag.line_ids[0]) if flag.line_ids else None
    for option_id in ids:
        if line is not None and _option_product(option_id) == line.product_id:
            return option_id
    return None


def _option_product(option_id: str) -> str | None:
    _, sep, product_id = option_id.partition(":")
    return product_id if sep and product_id else None


async def _change(
    db: AsyncSession, confirmation: Confirmation, quote: Quote, output: EngineOutput
) -> QuoteChange | None:
    """What changed since the previous quote, after an edit or a requote on the page."""
    reason = confirmation.change_reason
    if reason is None or quote.parent_quote_id is None:
        return None
    parent = await db.get_one(Quote, quote.parent_quote_id)
    before = {line.line_id: _line_key(line) for line in _output(parent).lines}
    return QuoteChange(
        reason=reason,  # type: ignore[arg-type]
        previous_total_cents=parent.total_cents,
        line_ids=[
            line.line_id for line in output.lines if before.get(line.line_id) != _line_key(line)
        ],
        text=REQUOTE if reason == "requote" else None,
    )


def _line_key(line: QuoteLine) -> tuple[str, int, int]:
    return line.product_id, line.quantity_sales_units, line.line_total_cents


def _receipt(order: Order, flags: list[ViewFlag]) -> ConfirmedOrder:
    return ConfirmedOrder(
        order_number=order.order_number,
        confirmed_at=order.confirmed_at,
        acknowledged=[
            AcknowledgedFlag(flag_key=f.flag_key, code=f.code, at=f.acknowledged_at)
            for f in flags
            if f.acknowledged_at is not None
        ],
    )


async def _mark_opened(
    db: AsyncSession, confirmation: Confirmation, quote: Quote, now: datetime
) -> None:
    """The first open: `opened_at`, the session's `link_opened` state and the event."""
    if confirmation.opened_at is not None:
        return
    await db.refresh(confirmation, with_for_update=True)
    if confirmation.opened_at is not None:  # another request was first
        return
    confirmation.opened_at = now
    session = await sessions.quote_session(db, quote, now=now)
    # After a failed SMS too: the buyer opened the link from the demo phone's inbox (#46).
    if session.state in (SessionState.awaiting_confirmation, SessionState.sms_failed):
        sessions.set_state(session, SessionState.link_opened, now)
    await db.flush()
    await _record(
        db,
        "link_opened",
        quote,
        {"confirmation_id": str(confirmation.id), "quote_id": str(quote.id)},
        Localized(fi="Vahvistuslinkki avattiin", en="The confirmation link was opened"),
    )


# --- Actions ----------------------------------------------------------------------------


async def acknowledge(
    db: AsyncSession, token: str, body: AcknowledgeRequest, *, now: datetime | None = None
) -> None:
    """Tick a flag. For a `choose` flag, `option_id` picks an option; one that changes the
    order makes a new quote, with the flag ticked on it if it is still there."""
    now = now or datetime.now(UTC)
    confirmation, quote = await _open(db, token)
    await _require_open(db, confirmation, quote, body.quote_hash, now)
    output = _output(quote)
    flag = next((f for f in output.flags if f.flag_key == body.flag_key), None)
    if flag is None:
        raise ConfirmationRefused(422, UNKNOWN_FLAG)
    option_id = None
    if flag.kind == "choose":
        option = next((o for o in flag.options if o.option_id == body.option_id), None)
        if option is None:
            raise ConfirmationRefused(422, UNKNOWN_OPTION)
        option_id = option.option_id
        lines = {line.line_id: line for line in output.lines}
        if option_id != _current_option(flag, lines):
            product_id = _option_product(option_id)
            line_id = flag.line_ids[0] if flag.line_ids else None
            if product_id is None or line_id is None:
                raise ConfirmationRefused(422, UNKNOWN_OPTION)
            requested = _with_product(_priced_requests(quote, output), line_id, product_id)
            new = await _replace(db, confirmation, quote, requested, "edit", line_id, now)
            same = next((f for f in _output(new).flags if f.flag_key == flag.flag_key), None)
            if same is not None:
                await _tick(db, confirmation, new, same, option_id, now)
            return
    await _tick(db, confirmation, quote, flag, option_id, now)


async def edit(
    db: AsyncSession,
    token: str,
    body: SetQuantityEdit | RemoveLineEdit | ChooseAlternativeEdit,
    *,
    now: datetime | None = None,
) -> None:
    """Change an amount (in sales units), remove a line or take an offered alternative."""
    now = now or datetime.now(UTC)
    confirmation, quote = await _open(db, token)
    await _require_open(db, confirmation, quote, body.quote_hash, now)
    output = _output(quote)
    line = next((x for x in output.lines if x.line_id == body.line_id), None)
    if line is None:
        raise ConfirmationRefused(422, UNKNOWN_LINE, body.line_id)
    requested = _priced_requests(quote, output)

    if isinstance(body, RemoveLineEdit):
        requested = [r for r in requested if r.line_id != line.line_id]
        if not requested:
            raise ConfirmationRefused(422, LAST_LINE, line.line_id)
    elif isinstance(body, SetQuantityEdit):
        if body.quantity == line.quantity_sales_units:
            return
        requested = _with_quantity(requested, line, body.quantity)
    else:
        if body.alternative_id not in {a.product_id for a in line.alternatives}:
            raise ConfirmationRefused(422, NOT_OFFERED, line.line_id)
        requested = _with_product(requested, line.line_id, body.alternative_id)
    await _replace(db, confirmation, quote, requested, "edit", line.line_id, now)


async def confirm(
    db: AsyncSession, token: str, body: ConfirmRequest, *, now: datetime | None = None
) -> ConfirmResponse:
    """Re-check availability and create the order. Idempotent for the same quote hash."""
    now = now or datetime.now(UTC)
    confirmation, quote = await _open(db, token)
    order = await _order(db, confirmation)
    if order is not None:
        if body.quote_hash == order.quote_hash:
            return ConfirmResponse(order_number=order.order_number, confirmed_at=order.confirmed_at)
        raise ConfirmationRefused(409, CLOSED)
    await _require_open(db, confirmation, quote, body.quote_hash, now)
    output = _output(quote)
    if output.decision != Decision.ready or not output.lines or quote.quote_hash is None:
        raise ConfirmationRefused(422, NOTHING_TO_ORDER)
    flags = await _view_flags(db, confirmation, quote, output)
    if any(f.requires_ack and f.acknowledged_at is None for f in flags):
        raise ConfirmationRefused(422, UNCHECKED)

    if await _availability_got_worse(db, quote, output, now):
        new = await _replace(
            db, confirmation, quote, _priced_requests(quote, output), "requote", None, now
        )
        await _record(
            db,
            "requote_needed",
            new,
            {
                "confirmation_id": str(confirmation.id),
                "voided_quote_id": str(quote.id),
                "quote_id": str(new.id),
                "version": new.version,
                "previous_total_cents": quote.total_cents,
                "total_cents": new.total_cents,
            },
            Localized(
                fi="Saatavuus heikkeni ennen vahvistusta, tilaus päivitettiin",
                en="Availability got worse before confirming, the order was updated",
            ),
            actor="confirmation",
        )
        raise ConfirmationRefused(409, REQUOTE)

    order = await _create_order(db, confirmation, quote, output, now)
    acknowledged = _receipt(order, flags).acknowledged
    await _record(
        db,
        "order_confirmed",
        quote,
        {
            "confirmation_id": str(confirmation.id),
            "order_number": order.order_number,
            "quote_id": str(quote.id),
            "quote_hash": quote.quote_hash,
            "total_cents": order.total_cents,
            "acknowledged": [a.model_dump(mode="json") for a in acknowledged],
        },
        Localized(
            fi=f"Tilaus {order.order_number} vahvistettiin",
            en=f"Order {order.order_number} was confirmed",
        ),
        actor="buyer",
    )
    return ConfirmResponse(order_number=order.order_number, confirmed_at=order.confirmed_at)


async def cancel(
    db: AsyncSession, token: str, body: CancelRequest, *, now: datetime | None = None
) -> None:
    """Cancel: nothing is ordered. Idempotent for the same quote hash."""
    now = now or datetime.now(UTC)
    confirmation, quote = await _open(db, token)
    if await _order(db, confirmation) is not None:
        raise ConfirmationRefused(409, CLOSED)
    if quote.status == QuoteStatus.cancelled:
        if body.quote_hash == _screen_hash(quote):
            return
        raise ConfirmationRefused(409, CLOSED)
    await _require_open(db, confirmation, quote, body.quote_hash, now)
    quote.status = QuoteStatus.cancelled
    confirmation.used_at = now
    session = await sessions.quote_session(db, quote, now=now)
    sessions.set_state(session, SessionState.cancelled, now)
    await db.flush()
    await _record(
        db,
        "order_cancelled",
        quote,
        {"confirmation_id": str(confirmation.id), "quote_id": str(quote.id)},
        Localized(fi="Tilaus peruttiin, mitään ei tilattu", en="Order cancelled, nothing ordered"),
        actor="buyer",
    )


# --- Steps ------------------------------------------------------------------------------


async def _tick(
    db: AsyncSession,
    confirmation: Confirmation,
    quote: Quote,
    flag: Flag,
    option_id: str | None,
    now: datetime,
) -> None:
    """Store one acknowledgement and its `flags_acknowledged` event, once per flag text."""
    inserted = await db.scalar(
        insert(ConfirmationAcknowledgement)
        .values(
            confirmation_id=confirmation.id,
            quote_id=quote.id,
            flag_key=flag.flag_key,
            code=flag.code,
            text_hash=text_hash(flag.text),
            option_id=option_id,
            acknowledged_at=now,
        )
        .on_conflict_do_nothing()
        .returning(ConfirmationAcknowledgement.id)
    )
    if inserted is None:
        return
    await _record(
        db,
        "flags_acknowledged",
        quote,
        {
            "confirmation_id": str(confirmation.id),
            "quote_id": str(quote.id),
            "flag_key": flag.flag_key,
            "code": flag.code,
            "option_id": option_id,
        },
        Localized(fi=f"Ostaja kuittasi: {flag.text.fi}", en=f"The buyer checked: {flag.text.en}"),
        actor="buyer",
    )


async def _replace(
    db: AsyncSession,
    confirmation: Confirmation,
    quote: Quote,
    requested: list[LineRequest],
    reason: str,
    refuse_line: str | None,
    now: datetime,
) -> Quote:
    """A new quote through `replace_quote` (the old one is voided there), repointed on the
    confirmation. For an edit (`refuse_line` set), a result that isn't ready is refused
    and nothing changes."""
    caller = await _caller(db, confirmation, quote)
    try:
        async with db.begin_nested():
            response = await quotes.replace_quote(db, caller, str(quote.id), requested, now=now)
            if refuse_line is not None and response.decision != Decision.ready:
                raise _NotReady(response)
    except _NotReady as not_ready:
        text = _why_not(not_ready.response, refuse_line)
        raise ConfirmationRefused(422, text, refuse_line) from not_ready
    except StateError as error:
        raise ConfirmationRefused(409, CLOSED) from error

    new = await db.get_one(Quote, uuid.UUID(response.quote_id))
    if new.status == QuoteStatus.ready:
        new.status = QuoteStatus.pending_confirmation
    confirmation.quote_id = str(new.id)
    if new.quote_hash is not None:
        confirmation.quote_hash = new.quote_hash
    confirmation.change_reason = reason
    session = await sessions.quote_session(db, new, now=now)
    state = SessionState.requote_needed if reason == "requote" else SessionState.link_opened
    sessions.set_state(session, state, now)
    await db.flush()
    return new


# --- The page's "Ask for changes" chat (#57, webshop-chat.md §5) ----------------------------


@dataclass(frozen=True)
class ChatTarget:
    """What the page's chat acts on: the link's user and its current quote."""

    user_id: uuid.UUID
    quote_id: str
    session_id: uuid.UUID
    lines: list[LineRequest]


async def chat_target(db: AsyncSession, token: str, *, now: datetime | None = None) -> ChatTarget:
    """The link's user and current quote, for the chat. NotFoundError (404) for an unknown
    token; ConfirmationRefused 410 when expired and 409 when no longer open."""
    now = now or datetime.now(UTC)
    confirmation = await _find(db, token)
    if confirmation is None:
        raise NotFoundError("unknown confirmation link")
    quote = await _current_quote(db, confirmation)
    state = _state(confirmation, quote, await _order(db, confirmation), now)
    if state == "expired":
        raise ConfirmationRefused(410, EXPIRED)
    if state not in ("ready", "requote_needed"):
        raise ConfirmationRefused(409, CLOSED)
    return ChatTarget(
        user_id=confirmation.user_id,
        quote_id=str(quote.id),
        session_id=quote.session_id,
        lines=_priced_requests(quote, _output(quote)),
    )


@dataclass(frozen=True)
class ChatEdit:
    """The result of the chat's change: the new quote, or why the page refused it (and the
    engine's question when the result needed one)."""

    quote: QuoteResponse | None
    refused: Localized | None = None
    clarification: Clarification | None = None


async def chat_edit(
    db: AsyncSession, token: str, lines: list[LineRequest], *, now: datetime | None = None
) -> ChatEdit:
    """The chat's `update_quote` on the link's quote, exactly as an edit with the page
    controls (`_replace`): a result that isn't ready is refused and nothing changes, so the
    link stays on its quote. ConfirmationRefused (409, 410) when the order is closed."""
    now = now or datetime.now(UTC)
    confirmation, quote = await _open(db, token)
    await _require_open(db, confirmation, quote, _screen_hash(quote), now)
    try:
        new = await _replace(db, confirmation, quote, lines, "edit", "", now)
    except ConfirmationRefused as refused:
        if refused.status != 422:
            raise
        cause = refused.__cause__
        clarification = cause.response.clarification if isinstance(cause, _NotReady) else None
        return ChatEdit(quote=None, refused=refused.text, clarification=clarification)
    caller = await _caller(db, confirmation, new)
    return ChatEdit(quote=await quotes.get_quote(db, caller, str(new.id)))


class _NotReady(Exception):
    def __init__(self, response: QuoteResponse):
        self.response = response


def _why_not(response: QuoteResponse, line_id: str | None) -> Localized:
    """The engine's own words for a refused edit (spec §4.4, §5)."""
    rejections = sorted(response.rejections, key=lambda r: r.line_id != line_id)
    if rejections:
        r = rejections[0]
        return Localized(fi=f"{r.text.fi} {r.next_step.fi}", en=f"{r.text.en} {r.next_step.en}")
    if response.clarification is not None:
        return response.clarification.question
    return response.speak


async def _availability_got_worse(
    db: AsyncSession, quote: Quote, output: EngineOutput, now: datetime
) -> bool:
    """Fetch fresh availability for the quote's products (a small shortlist) and decide
    again with the quote's own input and prices. Worse: a line changes or is lost, or its
    stock status drops. Writes `stock_rechecked`."""
    rules = await _rules(db, quote.rules_ref)
    stored = EngineInput.model_validate({**quote.engine_input, "rules": rules})
    needed_by = {r.line_id: r.needed_by for r in stored.lines}
    by_date: dict[date, set[str]] = {}
    for line in output.lines:
        by_date.setdefault(needed_by[line.line_id], set()).add(line.product_id)
    fresh: dict[str, Offer] = {}
    for day in sorted(by_date):
        for offer in await valio.get_offers(sorted(by_date[day]), day):
            fresh.setdefault(offer.product_id, offer)
    failed = sorted(pid for pid, offer in fresh.items() if not offer.ok)
    offers = [_with_availability(o, fresh.get(o.product_id)) for o in stored.offers]
    rechecked = engine.decide(stored.model_copy(update={"offers": offers}))

    after = {line.line_id: line for line in rechecked.lines}
    worse = rechecked.decision != Decision.ready or any(
        (new := after.get(line.line_id)) is None
        or _line_key(new) != _line_key(line)
        or _STOCK_RANK[new.stock_status] > _STOCK_RANK[line.stock_status]
        for line in output.lines
    )
    await _record(
        db,
        "stock_rechecked",
        quote,
        {
            "quote_id": str(quote.id),
            "worse": worse,
            "failed": failed,
            "lines": [
                {
                    "line_id": line.line_id,
                    "product_id": line.product_id,
                    "stock_before": line.stock_status.value,
                    "stock_after": after[line.line_id].stock_status.value
                    if line.line_id in after
                    else None,
                }
                for line in output.lines
            ],
        },
        Localized(fi="Saatavuus heikkeni", en="Availability got worse")
        if worse
        else Localized(fi="Saatavuus tarkistettiin uudelleen", en="Availability checked again"),
        actor="confirmation",
    )
    return worse


def _with_availability(stored: Offer, fresh: Offer | None) -> Offer:
    """The stored offer with fresh availability. The quote's price is fixed, and a fetch
    that failed leaves the stored offer as it was."""
    if fresh is None or not fresh.ok:
        return stored
    return stored.model_copy(
        update={
            "schedule": fresh.schedule,
            "sales_unit": fresh.sales_unit,
            "sales_block": fresh.sales_block,
            "closing_time": fresh.closing_time,
            "fetched_at": fresh.fetched_at,
            "source": fresh.source,
        }
    )


async def _create_order(
    db: AsyncSession,
    confirmation: Confirmation,
    quote: Quote,
    output: EngineOutput,
    now: datetime,
) -> Order:
    assert quote.quote_hash is not None
    order = Order(
        confirmation_id=confirmation.id,
        quote_id=quote.id,
        quote_hash=quote.quote_hash,
        session_id=quote.session_id,
        company_id=quote.company_id,
        user_id=confirmation.user_id,
        total_cents=quote.total_cents,
        confirmed_at=now,
    )
    db.add(order)
    await db.flush()
    await db.refresh(order, ["seq", "order_number"])
    db.add_all(
        OrderLine(
            order_id=order.id,
            line_id=line.line_id,
            product_id=line.product_id,
            name_fi=line.name.fi,
            name_en=line.name.en,
            sales_unit=line.sales_unit,
            quantity_sales_units=line.quantity_sales_units,
            unit_price_gross=line.unit_price_gross,
            line_total_cents=line.line_total_cents,
            delivery_date=line.delivery_date,
            stock_status=line.stock_status.value,
        )
        for line in output.lines
    )
    quote.status = QuoteStatus.confirmed
    confirmation.used_at = now
    session = await sessions.quote_session(db, quote, now=now)
    sessions.set_state(session, SessionState.confirmed, now)
    await db.flush()
    return order


# --- Requested lines --------------------------------------------------------------------


def _priced_requests(quote: Quote, output: EngineOutput) -> list[LineRequest]:
    """The quote's requested lines that are on the order. Rejected lines aren't on the page,
    so an edit leaves them out."""
    priced = {line.line_id for line in output.lines}
    return [
        LineRequest.model_validate(r) for r in quote.engine_input["lines"] if r["line_id"] in priced
    ]


def _replaced(requested: Iterable[LineRequest], line_id: str, **changes: Any) -> list[LineRequest]:
    try:
        return [
            LineRequest.model_validate({**r.model_dump(), **changes}) if r.line_id == line_id else r
            for r in requested
        ]
    except ValidationError as error:
        raise ConfirmationRefused(422, TOO_MUCH, line_id) from error


def _with_product(requested: list[LineRequest], line_id: str, product_id: str) -> list[LineRequest]:
    """The line asks for this product, with the same amount."""
    return _replaced(requested, line_id, product_id=product_id)


def _with_quantity(
    requested: list[LineRequest], line: QuoteLine, sales_units: int
) -> list[LineRequest]:
    """The line's product, `sales_units` of it. The amount stays in the asked unit, so the
    page still shows "3 pcs = 7,5 kg"."""
    per_sales_unit = line.quantity_in_asked_unit / line.quantity_sales_units
    return _replaced(
        requested,
        line.line_id,
        product_id=line.product_id,
        quantity=per_sales_unit * sales_units,
    )


# --- Loading ----------------------------------------------------------------------------


async def _find(db: AsyncSession, token: str, *, lock: bool = False) -> Confirmation | None:
    query = select(Confirmation).where(Confirmation.token_hash == hash_token(token))
    if lock:
        query = query.with_for_update()
    confirmation = await db.scalar(query)
    if confirmation is not None and confirmation.original_quote_id is None:
        # The first use of the link, before anything can repoint it.
        confirmation.original_quote_id = confirmation.quote_id
        await db.flush()
    return confirmation


async def _current_quote(db: AsyncSession, confirmation: Confirmation) -> Quote:
    return await db.get_one(Quote, uuid.UUID(confirmation.quote_id))


async def _open(db: AsyncSession, token: str) -> tuple[Confirmation, Quote]:
    """The confirmation and its quote, locked for an action, so double taps run one at a
    time. NotFoundError (404) for an unknown token.

    Lock order (#87): confirmation, then the quote's session, then the quote; the audit
    lock comes last, at commit. The agent's tools lock the session before the quote too
    (`run_tool`), and never lock a confirmation, so the two can't wait on each other."""
    confirmation = await _find(db, token, lock=True)
    if confirmation is None:
        raise NotFoundError("unknown confirmation link")
    quote = await _current_quote(db, confirmation)  # unlocked: only for its session
    await db.get_one(OrderSession, quote.session_id, with_for_update=True)
    await db.refresh(quote, with_for_update=True)
    return confirmation, quote


async def _require_open(
    db: AsyncSession, confirmation: Confirmation, quote: Quote, quote_hash: str, now: datetime
) -> None:
    state = _state(confirmation, quote, await _order(db, confirmation), now)
    if state == "expired":
        raise ConfirmationRefused(410, EXPIRED)
    if state not in ("ready", "requote_needed"):
        raise ConfirmationRefused(409, CLOSED)
    if quote_hash != _screen_hash(quote):
        raise ConfirmationRefused(409, STALE)


async def _order(db: AsyncSession, confirmation: Confirmation) -> Order | None:
    return await db.scalar(select(Order).where(Order.confirmation_id == confirmation.id))


async def _caller(db: AsyncSession, confirmation: Confirmation, quote: Quote) -> Caller:
    """The account that made the order, on the quote's channel, for `update_quote`."""
    account = await accounts.me(db, confirmation.user_id)
    if account is None:
        raise ConfirmationRefused(409, CLOSED)
    session = await db.get_one(OrderSession, quote.session_id)
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=account.exclusions,
        lang=account.lang,
        channel=session.channel,  # type: ignore[arg-type]
        client_name=session.client_name,
    )


async def _acknowledgements(
    db: AsyncSession, confirmation: Confirmation
) -> dict[tuple[str, str], datetime]:
    rows = await db.execute(
        select(
            ConfirmationAcknowledgement.flag_key,
            ConfirmationAcknowledgement.text_hash,
            ConfirmationAcknowledgement.acknowledged_at,
        ).where(ConfirmationAcknowledgement.confirmation_id == confirmation.id)
    )
    return {(key, digest): at for key, digest, at in rows}


async def _rules(db: AsyncSession, ref: str) -> RuleSet:
    current = get_rule_set()
    return current if current.ref == ref else await audit.load_rule_set_by_ref(db, ref)


def _output(quote: Quote) -> EngineOutput:
    return EngineOutput.model_validate(quote.engine_output)


def _screen_hash(quote: Quote) -> str:
    """The hash the page sends back. A quote the engine couldn't make ready (only after a
    requote) has none, so its id stands in."""
    return quote.quote_hash or f"quote:{quote.id}"


def text_hash(text: Localized) -> str:
    """Identifies a flag's text, so a changed text needs a new tick."""
    return hashlib.sha256(rfc8785.dumps(text.model_dump())).hexdigest()


async def _record(
    db: AsyncSession,
    type: str,
    quote: Quote,
    payload: dict[str, Any],
    text: Localized,
    *,
    actor: str = "buyer",
) -> None:
    """One audit event in the quote's session. Payloads hold ids only, never the token or
    the link (technical-plan.md §9.5); the writer refuses them anyway."""
    await audit.record(
        db,
        type=type,
        actor=actor,
        session_id=quote.session_id,
        quote_id=quote.id,
        payload=payload,
        text=text,
    )
