"""The quote service (#45, technical-plan.md §2, §8.1): gather the engine's input, call the
engine, store the quote and write the audit events.

Every function takes the tool call's `AsyncSession` and only flushes. The interface layer
(`app.interfaces.tool_calls`) runs each tool call in one transaction, so the quote, the
session and the audit events always commit or roll back together.

The engine input is stored with the quote, without the rule set (`rules_ref` names it), so
`decide()` on it gives the same output and quote hash again (the replay test).
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.adapters import valio
from app.models import KitchenProfile as KitchenProfileRow
from app.models import Order, OrderSession, Quote
from app.models import QuoteLine as QuoteLineRow
from app.schemas import (
    BuildQuoteRequest,
    ConfirmationRequestResponse,
    Decision,
    EngineInput,
    EngineOutput,
    Exclusion,
    GetOrderStatusRequest,
    HistorySummary,
    KitchenProfile,
    LineRequest,
    Localized,
    Offer,
    OrderStatusResponse,
    ProductRecord,
    QuoteResponse,
    QuoteStatus,
    RequestConfirmationRequest,
    SessionState,
    UpdateQuoteRequest,
    UsualItem,
)
from app.services import audit, catalog, confirmations, customers, sessions, signing
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError
from app.services.policy import get_rule_set

log = logging.getLogger(__name__)

# At most this many product ids per quote go to price and availability (CLAUDE.md: small
# shortlists only). Over the cap, each line keeps its best candidates first.
MAX_CANDIDATES = 100
SEARCH_LIMIT = 20
# The curated substitutes of this many top search hits are added as candidates.
SUBSTITUTES_OF_TOP = 5

# A quote can be replaced by an edit until it is confirmed, cancelled or expired. Answering
# a clarification, or changing a rejected line, is an edit too.
EDITABLE = {
    QuoteStatus.ready,
    QuoteStatus.needs_clarification,
    QuoteStatus.rejected,
    QuoteStatus.pending_confirmation,
}

_STATUS = {
    Decision.ready: QuoteStatus.ready,
    Decision.needs_clarification: QuoteStatus.needs_clarification,
    Decision.rejected: QuoteStatus.rejected,
}
_SESSION_STATE = {
    Decision.ready: SessionState.quote_ready,
    Decision.needs_clarification: SessionState.needs_clarification,
    Decision.rejected: SessionState.rejected,
}


# --- Tools ------------------------------------------------------------------------------


async def build_quote(
    db: AsyncSession, caller: Caller, request: BuildQuoteRequest, *, now: datetime | None = None
) -> QuoteResponse:
    now = now or datetime.now(UTC)
    session = await sessions.current_session(db, caller, now=now)
    _, response = await _new_quote(db, caller, session, request.lines, now=now)
    return response


async def update_quote(
    db: AsyncSession, caller: Caller, request: UpdateQuoteRequest, *, now: datetime | None = None
) -> QuoteResponse:
    """A new quote with the next version, in the old quote's session. The old one is `void`."""
    now = now or datetime.now(UTC)
    old = await _load(db, caller, request.quote_id, for_update=True)
    if QuoteStatus(old.status) not in EDITABLE:
        current = await _newest_descendant(db, old)
        raise StateError(
            f"the quote is {old.status} and can no longer be changed; "
            f"the current quote is {current.id}"
        )
    session = await sessions.quote_session(db, old, now=now)
    new, response = await _new_quote(db, caller, session, request.lines, now=now, parent=old)

    old.status = QuoteStatus.void
    await db.flush()
    await _record(
        db,
        "quote_voided",
        session,
        old.id,
        {"quote_id": str(old.id), "version": old.version, "replaced_by_quote_id": str(new.id)},
        Localized(
            fi=f"Tarjous {old.version} korvattiin uudella",
            en=f"Quote {old.version} was replaced",
        ),
    )
    await _record(
        db,
        "quote_edited",
        session,
        new.id,
        {"quote_id": str(new.id), "version": new.version, "parent_quote_id": str(old.id)},
        Localized(
            fi=f"Tarjousta muutettiin, uusi versio {new.version}",
            en=f"The quote was changed, new version {new.version}",
        ),
    )
    return response


async def request_confirmation(
    db: AsyncSession,
    caller: Caller,
    request: RequestConfirmationRequest,
    *,
    now: datetime | None = None,
) -> ConfirmationRequestResponse:
    """Marks a ready quote as waiting for confirmation and sends the link to the caller's
    own inbox through the confirmations service (#46), in the same transaction."""
    now = now or datetime.now(UTC)
    quote = await _load(db, caller, request.quote_id, for_update=True)
    status = QuoteStatus(quote.status)
    if status in (QuoteStatus.needs_clarification, QuoteStatus.rejected):
        raise StateError(
            f"the quote is {status.value}; "
            "answer the question or change the lines with update_quote first"
        )
    if status != QuoteStatus.ready:
        raise StateError(
            f"the quote is {status.value}; only a ready quote can be sent for confirmation"
        )
    session = await sessions.quote_session(db, quote, now=now)
    quote.status = QuoteStatus.pending_confirmation
    sessions.set_state(session, SessionState.awaiting_confirmation, now)
    await db.flush()
    stored = QuoteResponse(
        **dict(EngineOutput.model_validate(quote.engine_output)),
        quote_id=str(quote.id),
        version=quote.version,
        parent_quote_id=str(quote.parent_quote_id) if quote.parent_quote_id else None,
        status=QuoteStatus(quote.status),
        expires_at=quote.expires_at,
        quote_hash=quote.quote_hash,
    )
    # A StateError here (no account to send to) rolls the status change back with the
    # tool call's savepoint.
    return await confirmations.request_confirmation(db, caller, stored, now=now)


async def get_order_status(
    db: AsyncSession,
    caller: Caller,
    request: GetOrderStatusRequest,
    *,
    now: datetime | None = None,
) -> OrderStatusResponse:
    quote = await _load(db, caller, request.quote_id)
    await sessions.quote_session(db, quote, now=now)
    replaced_by = None
    if quote.status == QuoteStatus.void:
        newest = await _newest_descendant(db, quote)
        replaced_by = str(newest.id) if newest.id != quote.id else None
    return OrderStatusResponse(
        quote_id=str(quote.id),
        status=QuoteStatus(quote.status),
        order_number=await db.scalar(select(Order.order_number).where(Order.quote_id == quote.id)),
        replaced_by_quote_id=replaced_by,
    )


# --- Chat panel helpers (technical-plan.md §9.6, not agent tools) ------------------------


async def get_quote(db: AsyncSession, caller: Caller, quote_id: str) -> QuoteResponse:
    return _response(await _load(db, caller, quote_id))


async def current_quote(db: AsyncSession, caller: Caller) -> QuoteResponse:
    """The newest quote in the caller's sessions, on any channel: the webshop page signs in
    with the cookie while its chat agent uses a token."""
    quote = await db.scalar(
        select(Quote)
        .join(OrderSession, OrderSession.id == Quote.session_id)
        .where(OrderSession.user_id == caller.user_id, Quote.company_id == caller.company_id)
        .order_by(Quote.created_at.desc(), Quote.version.desc())
        .limit(1)
    )
    if quote is None:
        raise NotFoundError("no quote yet")
    return _response(quote)


def _response(quote: Quote) -> QuoteResponse:
    return QuoteResponse(
        **dict(EngineOutput.model_validate(quote.engine_output)),
        quote_id=str(quote.id),
        version=quote.version,
        parent_quote_id=str(quote.parent_quote_id) if quote.parent_quote_id else None,
        status=QuoteStatus(quote.status),
        expires_at=quote.expires_at,
        quote_hash=quote.quote_hash,
    )


# --- Building one quote -----------------------------------------------------------------


async def _new_quote(
    db: AsyncSession,
    caller: Caller,
    session: OrderSession,
    lines: list[LineRequest],
    *,
    now: datetime,
    parent: Quote | None = None,
) -> tuple[Quote, QuoteResponse]:
    """Steps 2 to 10 of #45's spec: candidates, offers, decide, store, audit."""
    quote_id = uuid.uuid4()
    version = parent.version + 1 if parent else 1
    record = _recorder(db, session, quote_id)

    await record(
        "request_received",
        {"lines": [line.model_dump(mode="json") for line in lines]},
        Localized(fi=f"Tilauspyyntö, {len(lines)} riviä", en=f"Order request, {len(lines)} lines"),
    )

    usual_items = customers.usual_items(caller)
    ranked = await _ranked_candidates(lines, usual_items)
    kept = cap_candidates(ranked, MAX_CANDIDATES)
    candidates = {line_id: [i for i in ids if i in kept] for line_id, ids in ranked.items()}
    await record(
        "products_searched",
        {
            "lines": [
                {
                    "line_id": line.line_id,
                    "query": line.model_dump(
                        mode="json", include={"product_id", "usual", "text", "claims", "category"}
                    ),
                    "candidate_ids": candidates[line.line_id],
                }
                for line in lines
            ],
            "candidate_count": len(kept),
            "capped": len(kept) < len({i for ids in ranked.values() for i in ids}),
        },
        Localized(fi=f"Haettiin {len(kept)} tuotetta", en=f"Searched {len(kept)} products"),
    )

    products = await catalog.get_products(sorted(kept))
    offers = await _offers(lines, candidates, products)
    failed = sum(not offer.ok for offer in offers)
    await record(
        "availability_checked",
        {
            "count": len(offers),
            "failed": failed,
            "sources": sorted({offer.source.value for offer in offers}),
            "fetched_at": min((o.fetched_at for o in offers), default=now).isoformat(),
        },
        Localized(
            fi=f"Tarkistettiin hinta ja saatavuus, {len(offers)} tuotetta",
            en=f"Checked price and availability of {len(offers)} products",
        ),
    )

    rules = get_rule_set()
    engine_input = EngineInput(
        lines=lines,
        kitchen=KitchenProfile(exclusions=await _exclusions(db, caller)),
        history=HistorySummary(usual_items=usual_items, recent_lines=[]),
        candidates=candidates,
        products=products,
        offers=offers,
        rules=rules,
        business_now=rules.policy.business_time,
        issued_at=now,
        lang=caller.lang,
    )
    try:
        output = engine.decide(engine_input)
    except Exception:
        log.exception("the engine failed on quote %s", quote_id)
        raise

    ready = output.decision == Decision.ready
    ttl = rules.policy.quote_ttl_seconds
    expires_at = now + timedelta(seconds=ttl) if ready and ttl else None
    quote_hash = jws = None
    if ready:
        payload = quote_payload(
            quote_id, version, caller.company_id, output, issued_at=now, expires_at=expires_at
        )
        quote_hash, jws = signing.quote_hash(payload), signing.sign_quote(payload)

    # Stored once in `rule_sets` (with its audit event), so `rules_ref` resolves on replay.
    await audit.ensure_rule_set(db, rules)
    stored_input = engine_input.model_dump(mode="json", exclude={"rules"})
    stored_output = output.model_dump(mode="json")
    quote = Quote(
        id=quote_id,
        session_id=session.id,
        company_id=caller.company_id,
        version=version,
        parent_quote_id=parent.id if parent else None,
        status=_STATUS[output.decision],
        decision=output.decision,
        quote_hash=quote_hash,
        jws=jws,
        rules_ref=output.rules_ref,
        issued_at=now,
        expires_at=expires_at,
        total_cents=output.total_cents,
        engine_input=stored_input,
        engine_output=stored_output,
    )
    db.add(quote)
    await db.flush()
    db.add_all(
        QuoteLineRow(
            quote_id=quote_id,
            line_id=line.line_id,
            product_id=line.product_id,
            quantity_sales_units=line.quantity_sales_units,
            line_total_cents=line.line_total_cents,
            delivery_date=line.delivery_date,
            stock_status=line.stock_status,
        )
        for line in output.lines
    )
    await db.flush()

    await _record_decision(record, lines, output, stored_input, quote_hash)
    sessions.set_state(session, _SESSION_STATE[output.decision], now)
    await db.flush()

    response = QuoteResponse(
        **dict(output),
        quote_id=str(quote_id),
        version=version,
        parent_quote_id=str(parent.id) if parent else None,
        status=_STATUS[output.decision],
        expires_at=expires_at,
        quote_hash=quote_hash,
    )
    return quote, response


def quote_payload(
    quote_id: uuid.UUID,
    version: int,
    company_id: uuid.UUID,
    output: EngineOutput,
    *,
    issued_at: datetime,
    expires_at: datetime | None,
) -> dict[str, Any]:
    """What the quote hash and signature cover (technical-plan.md §8.1): the customer, the
    lines, totals, delivery dates, issue time, expiry and rule set. Decimals are strings and
    times are UTC ISO 8601, so the canonical JSON is exact."""
    return {
        "quote_id": str(quote_id),
        "version": version,
        "customer": {"company_id": str(company_id)},
        "lines": [
            {
                "line_id": line.line_id,
                "product_id": line.product_id,
                "quantity_sales_units": line.quantity_sales_units,
                "sales_unit": line.sales_unit,
                "unit_price_gross": str(line.unit_price_gross),
                "line_total_cents": line.line_total_cents,
                "delivery_date": line.delivery_date.isoformat(),
            }
            for line in output.lines
        ],
        "total_cents": output.total_cents,
        "delivery": output.delivery.model_dump(mode="json") if output.delivery else None,
        "issued_at": _utc(issued_at),
        "expires_at": _utc(expires_at) if expires_at else None,
        "rules_ref": output.rules_ref,
    }


def cap_candidates(ranked: dict[str, list[str]], limit: int) -> set[str]:
    """At most `limit` distinct ids: every line's best candidate, then every line's second
    best, and so on, lines in request order."""
    kept: set[str] = set()
    depth = max((len(ids) for ids in ranked.values()), default=0)
    for rank in range(depth):
        for ids in ranked.values():
            if rank < len(ids) and ids[rank] not in kept:
                if len(kept) == limit:
                    return kept
                kept.add(ids[rank])
    return kept


async def _ranked_candidates(
    lines: list[LineRequest], usual_items: list[UsualItem]
) -> dict[str, list[str]]:
    """Candidate ids per line, best first, without duplicates."""
    ranked: dict[str, list[str]] = {}
    for line in lines:
        if line.product_id is not None:
            ids = [line.product_id]
            with_substitutes = ids
        elif line.usual:
            words = (line.text or "").lower().split()
            ids = sorted(
                {
                    item.product_id
                    for item in usual_items
                    if all(w in f"{item.name.fi} {item.name.en}".lower() for w in words)
                }
            )
            with_substitutes = ids
        else:
            hits = await catalog.search_candidates(
                line.text, line.claims, line.category, limit=SEARCH_LIMIT
            )
            ids = [hit.product_id for hit in hits]
            with_substitutes = ids[:SUBSTITUTES_OF_TOP]
        substitutes = [
            sub for record in await catalog.get_products(with_substitutes)
            for sub in record.substitutions
        ]  # fmt: skip
        ranked[line.line_id] = _unique([*ids, *substitutes])
    return ranked


async def _offers(
    lines: list[LineRequest], candidates: dict[str, list[str]], products: list[ProductRecord]
) -> list[Offer]:
    """One `get_offers` call per distinct `needed_by`, one offer per product, by product id.

    A product asked for on two dates keeps the offer fetched for the earlier one.
    """
    known = {p.product_id for p in products}
    by_date: dict[date, list[str]] = {}
    for line in lines:
        ids = by_date.setdefault(line.needed_by, [])
        ids.extend(i for i in candidates[line.line_id] if i in known and i not in ids)
    offers: dict[str, Offer] = {}
    for needed_by in sorted(by_date):
        if by_date[needed_by]:
            for offer in await valio.get_offers(sorted(by_date[needed_by]), needed_by):
                offers.setdefault(offer.product_id, offer)
    return [offers[i] for i in sorted(offers)]


async def _exclusions(db: AsyncSession, caller: Caller) -> list[Exclusion]:
    """The company's kitchen profile at this moment, or the caller's if it has none."""
    stored = await db.scalar(
        select(KitchenProfileRow.exclusions).where(
            KitchenProfileRow.company_id == caller.company_id
        )
    )
    if stored is None:
        return list(caller.exclusions)
    known = {e.value for e in Exclusion}
    return [Exclusion(e) for e in stored if e in known]


async def _record_decision(
    record: Any,
    lines: list[LineRequest],
    output: EngineOutput,
    stored_input: dict[str, Any],
    quote_hash: str | None,
) -> None:
    """candidates_filtered, line_resolved per line, then the decision's own event."""
    priced = {line.line_id: line for line in output.lines}
    rejected = {r.line_id: r for r in output.rejections}
    await record(
        "candidates_filtered",
        {
            "lines": [
                {"line_id": line.line_id, "trace": line.trace.model_dump(mode="json")}
                for line in output.lines
            ]
        },
        Localized(fi="Ehdokkaat suodatettiin", en="Candidates filtered"),
        actor="engine",
    )
    for line in lines:
        if line.line_id in priced:
            result = priced[line.line_id]
            payload = {
                "line_id": line.line_id,
                "outcome": "priced",
                "product_id": result.product_id,
                "quantity_sales_units": result.quantity_sales_units,
                "line_total_cents": result.line_total_cents,
                "reason_codes": result.reason_codes,
            }
            text = result.reason_text
        elif line.line_id in rejected:
            rejection = rejected[line.line_id]
            payload = {
                "line_id": line.line_id,
                "outcome": "rejected",
                "reason_codes": [rejection.reason_code],
            }
            text = rejection.text
        else:
            payload = {"line_id": line.line_id, "outcome": "needs_clarification"}
            text = Localized(fi="Rivi vaatii tarkennuksen", en="The line needs an answer")
        await record("line_resolved", payload, text, actor="engine")

    decision_payload = {
        "decision": output.decision.value,
        "rules_ref": output.rules_ref,
        "quote_hash": quote_hash,
        "total_cents": output.total_cents,
        "engine_input": stored_input,
        "engine_output": output.model_dump(mode="json"),
    }
    if output.decision == Decision.ready:
        await record("quote_built", decision_payload, output.speak)
    elif output.decision == Decision.needs_clarification:
        question = output.clarification.question if output.clarification else output.speak
        await record("clarification_asked", decision_payload, question)
    else:
        await record("quote_rejected", decision_payload, output.speak)


def _recorder(db: AsyncSession, session: OrderSession, quote_id: uuid.UUID):
    async def record(
        type: str,
        payload: dict[str, Any],
        text: Localized,
        *,
        actor: str = "service",
    ) -> None:
        await audit.record(
            db,
            type=type,
            actor=actor,
            session_id=session.id,
            quote_id=quote_id,
            payload=payload,
            text=text,
        )

    return record


async def _record(
    db: AsyncSession,
    type: str,
    session: OrderSession,
    quote_id: uuid.UUID,
    payload: dict[str, Any],
    text: Localized,
) -> None:
    await _recorder(db, session, quote_id)(type, payload, text)


# --- Loading ----------------------------------------------------------------------------


async def _load(
    db: AsyncSession, caller: Caller, quote_id: str, *, for_update: bool = False
) -> Quote:
    """The caller's company's quote, or NotFoundError (also for another company's quote)."""
    quote_uuid = sessions.parse_uuid(quote_id)
    if quote_uuid is None:
        raise NotFoundError("quote not found")
    query = select(Quote).where(Quote.id == quote_uuid, Quote.company_id == caller.company_id)
    if for_update:
        query = query.with_for_update()
    quote = await db.scalar(query)
    if quote is None:
        raise NotFoundError("quote not found")
    return quote


async def _newest_descendant(db: AsyncSession, quote: Quote) -> Quote:
    """The newest quote that has this one as an ancestor, or the quote itself."""
    current = quote
    while True:
        child = await db.scalar(
            select(Quote)
            .where(Quote.parent_quote_id == current.id)
            .order_by(Quote.version.desc())
            .limit(1)
        )
        if child is None:
            return current
        current = child


def _unique(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")
