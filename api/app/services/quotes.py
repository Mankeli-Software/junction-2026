"""The quote service (#45, technical-plan.md §2, §8.1): gather the engine's input, call the
engine, store the quote and write the audit events.

Every function takes the tool call's `AsyncSession` and only flushes. The interface layer
(`app.interfaces.tool_calls`) runs each tool call in one transaction, so the quote, the
session and the audit events always commit or roll back together.

The engine input is stored with the quote, without the rule set (`rules_ref` names it), so
`decide()` on it gives the same output and quote hash again (the replay test).

A quote from a confirmed recipe draft (#80) stores the draft's id and confirmed hash in the
engine input (`recipe_drafts`, which the engine doesn't read) and its unticked ingredients in
`not_ordered`. `with_recipe_drafts()` then labels the draft's group `source="photo"`, the
same way on replay; the quote hash covers the draft reference too.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine, telemetry
from app.adapters import valio
from app.engine.filters import may_block
from app.engine.units import without_size
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
    QuoteLine,
    QuoteResponse,
    QuoteStatus,
    RecipeDraftRef,
    RequestConfirmationRequest,
    RuleSet,
    SessionState,
    UpdateQuoteRequest,
    UsualItem,
)
from app.search.substitutes import category_substitutes
from app.services import (
    audit,
    catalog,
    confirmations,
    customers,
    recipe_drafts,
    recipes,
    sessions,
    signing,
)
from app.services.caller import Caller
from app.services.errors import InvalidLinesError, NotFoundError, StateError
from app.services.policy import get_rule_set

log = logging.getLogger(__name__)

# At most this many product ids per quote go to price and availability (CLAUDE.md: small
# shortlists only). Over the cap, each line keeps its best candidates first.
MAX_CANDIDATES = 100
SEARCH_LIMIT = 20
# When every search hit may be blocked, the curated substitutes of this many top hits are
# added as candidates.
SUBSTITUTES_OF_TOP = 5
# From each category in data/category_substitutes.csv, this many alternatives (#78).
MAPPED_SUBSTITUTES = 5
# For a named product, this many hits in its category, searched by its name without the
# pack size: other packs and exact-fit alternatives for the engine (#39, #42).
NAMED_ALTERNATIVES = 5

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
    timer = telemetry.Timer()
    session = await sessions.current_session(db, caller, now=now)
    lines, drafts = list(request.lines), []
    if request.recipe_draft_id is not None:
        needed_by = request.needed_by or min(
            (line.needed_by for line in lines), default=next_weekday(get_rule_set())
        )
        lines, draft = await recipe_drafts.quote_lines(
            db, caller, request.recipe_draft_id, lines, needed_by
        )
        drafts.append(draft)
    refuse_invalid_lines(lines)
    _, response = await _new_quote(db, caller, session, lines, now=now, drafts=drafts)
    telemetry.quote_duration.record(
        timer.ms, telemetry.metric_attrs(tool="build_quote", decision=response.decision.value)
    )
    return response


async def update_quote(
    db: AsyncSession,
    caller: Caller,
    request: UpdateQuoteRequest,
    *,
    now: datetime | None = None,
    refuse_invalid: bool = True,
) -> QuoteResponse:
    """A new quote with the next version, in the old quote's session. The old one is `void`.

    Lines with input errors refuse the whole update and the old quote stays current
    (#106). The confirmation page turns that off: it builds the lines itself and shows a
    rejected line in its own words.
    """
    now = now or datetime.now(UTC)
    old = await _load(db, caller, request.quote_id, for_update=True)
    if refuse_invalid:
        refuse_invalid_lines(request.lines, current=old)
    if QuoteStatus(old.status) not in EDITABLE:
        current = await _newest_descendant(db, old)
        raise StateError(
            f"the quote is {old.status} and can no longer be changed; "
            f"the current quote is {current.id}"
        )
    session = await sessions.quote_session(db, old, now=now)
    # The new lines still carry a recipe draft's group: the group keeps its photo label.
    groups = {line.group for line in request.lines}
    drafts = [
        draft
        for draft in map(RecipeDraftRef.model_validate, old.engine_input.get("recipe_drafts", []))
        if draft.group in groups
    ]
    new, response = await _new_quote(
        db, caller, session, request.lines, now=now, parent=old, drafts=drafts
    )

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


def refuse_invalid_lines(lines: Sequence[LineRequest], *, current: Quote | None = None) -> None:
    """Raises InvalidLinesError when a line has an input error, naming every one: the line,
    the code, the field and the fix. Nothing is stored, so the agent corrects the lines
    and calls again without asking the buyer for what it already has."""
    rules = get_rule_set()
    errors = engine.input_errors(lines, rules.policy.business_time.date())
    if not errors:
        return
    problems = [(lines[index].line_id, code.value) for index, code in errors]
    listed = [
        f"- line {lines[index].line_id}, {code.value}: {rules.messages[code].en} "
        f"{rules.messages[code].next.en}"
        for index, code in errors
    ]
    kept = (
        f"The current quote {current.id} is unchanged."
        if current is not None
        else "No quote was made."
    )
    raise InvalidLinesError(
        "\n".join(
            [
                f"{len(listed)} input error(s) in the lines. {kept} Fix them and call again "
                "with the same lines; don't ask the buyer again for what you already have.",
                *listed,
            ]
        ),
        problems,
    )


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
    drafts: Sequence[RecipeDraftRef] = (),
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

    # A whole recipe becomes one line per linked ingredient; the rest is not ordered (#34).
    lines, not_ordered = await recipes.expand_lines(db, lines)
    usual_items = await customers.usual_items(db, caller)
    rules = get_rule_set()
    exclusions = await _exclusions(db, caller)
    with telemetry.span("quote search", lines=len(lines)):
        ranked, substitutes = await _ranked_candidates(db, lines, usual_items, exclusions, rules)
        kept = cap_candidates(ranked, MAX_CANDIDATES)
        candidates = {line_id: [i for i in ids if i in kept] for line_id, ids in ranked.items()}
        telemetry.annotate(
            candidates=len(kept),
            substitutes=sum(len(ids) for ids in substitutes.values()),
            empty_lines=sum(not ids for ids in candidates.values()),
        )
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
                    "substitute_ids": [i for i in substitutes[line.line_id] if i in kept],
                }
                for line in lines
            ],
            "candidate_count": len(kept),
            "capped": len(kept) < len({i for ids in ranked.values() for i in ids}),
        },
        Localized(fi=f"Haettiin {len(kept)} tuotetta", en=f"Searched {len(kept)} products"),
    )

    products = await catalog.get_products(db, sorted(kept))
    with telemetry.span("quote offers", products=len(products)):
        offers = await _offers(lines, candidates, products)
        failed = sum(not offer.ok for offer in offers)
        telemetry.annotate(
            offers=len(offers),
            failed=failed,
            sources=",".join(sorted({offer.source.value for offer in offers})),
        )
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

    engine_input = EngineInput(
        lines=lines,
        kitchen=KitchenProfile(exclusions=exclusions),
        history=HistorySummary(
            usual_items=usual_items, recent_lines=await customers.recent_lines(db, caller)
        ),
        candidates=candidates,
        substitutes={line: [i for i in ids if i in kept] for line, ids in substitutes.items()},
        products=products,
        offers=offers,
        rules=rules,
        business_now=rules.policy.business_time,
        issued_at=now,
        lang=caller.lang,
        # A recipe draft's unticked ingredients are listed with the recipes' (#34).
        not_ordered=[*not_ordered, *(item for d in drafts for item in d.not_ordered)],
        recipe_drafts=list(drafts),
    )
    # The engine is pure; its span is made here, from its output (#84).
    engine_timer = telemetry.Timer()
    with telemetry.span("engine decide", lines=len(lines), products=len(products)):
        try:
            output = with_recipe_drafts(engine.decide(engine_input), engine_input.recipe_drafts)
        except Exception:
            log.exception("the engine failed on quote %s", quote_id)
            raise
        telemetry.annotate(
            decision=output.decision.value,
            quote_lines=len(output.lines),
            flags=",".join(sorted({f.code for f in output.flags})) or None,
            rejections=",".join(sorted({r.reason_code for r in output.rejections})) or None,
            clarification=output.clarification.question.en if output.clarification else None,
            total_cents=output.total_cents,
            rules_ref=output.rules_ref,
            speak=output.speak.en,
        )
    telemetry.engine_duration.record(engine_timer.ms, telemetry.metric_attrs())
    telemetry.quote_decisions.add(1, telemetry.metric_attrs(decision=output.decision.value))

    ready = output.decision == Decision.ready
    ttl = rules.policy.quote_ttl_seconds
    expires_at = now + timedelta(seconds=ttl) if ready and ttl else None
    quote_hash = jws = None
    if ready:
        payload = quote_payload(
            quote_id,
            version,
            caller.company_id,
            output,
            engine_input.offers,
            issued_at=now,
            expires_at=expires_at,
            recipe_drafts=engine_input.recipe_drafts,
        )
        quote_hash, jws = signing.quote_hash(payload), signing.sign_quote(payload)

    # Stored once in `rule_sets` (with its audit event), so `rules_ref` resolves on replay.
    await audit.ensure_rule_set(db, rules)
    # Without a draft, the stored input is exactly as before #80.
    exclude = {"rules"} if engine_input.recipe_drafts else {"rules", "recipe_drafts"}
    stored_input = engine_input.model_dump(mode="json", exclude=exclude)
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
    offers: Iterable[Offer],
    *,
    issued_at: datetime,
    expires_at: datetime | None,
    recipe_drafts: Iterable[RecipeDraftRef] = (),
) -> dict[str, Any]:
    """What the quote hash and signature cover (technical-plan.md §8.1): the customer, the
    lines with their labelled claims, totals, delivery dates, issue time, expiry and rule
    set. Decimals are strings and times are UTC ISO 8601, so the canonical JSON is exact.
    `offers` are the engine input's, where each line's price came from. A quote from a
    recipe draft also covers the draft's id and confirmed hash (#80)."""
    offer_by_product = {offer.product_id: offer for offer in offers}
    payload = {
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
                "claims": line_claims(line, offer_by_product.get(line.product_id)),
            }
            for line in output.lines
        ],
        "total_cents": output.total_cents,
        "delivery": output.delivery.model_dump(mode="json") if output.delivery else None,
        "issued_at": _utc(issued_at),
        "expires_at": _utc(expires_at) if expires_at else None,
        "rules_ref": output.rules_ref,
    }
    drafts = [{"draft_id": d.draft_id, "confirmed_hash": d.confirmed_hash} for d in recipe_drafts]
    if drafts:
        payload["recipe_drafts"] = drafts
    return payload


def with_recipe_drafts(output: EngineOutput, drafts: Iterable[RecipeDraftRef]) -> EngineOutput:
    """The engine's output with each recipe draft's group labelled as from a photo (#80).
    Unchanged without a draft. The draft's unticked ingredients are already in the engine
    input's `not_ordered`, which the engine returns as they are."""
    by_group = {draft.group: draft for draft in drafts}
    if not by_group:
        return output
    groups = [
        group.model_copy(
            update={"source": "photo", "recipe_draft_id": by_group[group.group].draft_id}
        )
        if group.group in by_group
        else group
        for group in output.groups
    ]
    return output.model_copy(update={"groups": groups})


def next_weekday(rules: RuleSet) -> date:
    """The business day after today, skipping the weekend: a recipe draft's lines are
    needed by then unless the request says otherwise."""
    day = rules.policy.business_time.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def line_claims(line: QuoteLine, offer: Offer | None) -> dict[str, Any]:
    """Where each fact on a line comes from (vision §12): stock verified or not, the price
    from the Valio API (live or the recorded snapshot) and the origin from product data."""
    return {
        "stock": line.stock_status.value,
        "price": {
            "source": "valio_api",
            "fetched": offer.source.value if offer else None,
            "fetched_at": _utc(offer.fetched_at) if offer else None,
        },
        "origin": {"value": line.origin, "source": "product_data"},
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
    db: AsyncSession,
    lines: list[LineRequest],
    usual_items: list[UsualItem],
    exclusions: list[Exclusion],
    rules: RuleSet,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Candidate ids per line, best first, without duplicates, and the substitute ids
    among them.

    A named product or "my usual" brings its curated substitutes. A text line is its search
    hits; only when every hit may be blocked by the kitchen (`may_block`) are the
    substitute candidates added after them (docs/plans/30-product-search.md §7.2): the
    curated substitutes of the top hits, then the best few by meaning in the categories
    mapped from the top hit's category (data/category_substitutes.csv, #78), then a second
    search in the top hit's category with the line's claims and no words.
    Substitutes that may be blocked themselves are left out, so they don't use up the cap.
    """
    ranked: dict[str, list[str]] = {}
    substitutes: dict[str, list[str]] = {}
    for line in lines:
        if line.product_id is not None or line.usual:
            if line.product_id is not None:
                ids = [line.product_id]
            else:
                words = (line.text or "").lower().split()
                ids = sorted(
                    {
                        item.product_id
                        for item in usual_items
                        if all(w in f"{item.name.fi} {item.name.en}".lower() for w in words)
                    }
                )
            records = await catalog.get_products(db, ids)
            subs = [sub for record in records for sub in record.substitutions]
            for record in records:
                similar = await catalog.search_candidates(
                    db,
                    without_size(record.name.fi),
                    line.claims,
                    record.category,
                    limit=NAMED_ALTERNATIVES,
                )
                subs += [hit.product_id for hit in similar]
        else:
            hits = await catalog.search_candidates(
                db, line.text, line.claims, line.category, limit=SEARCH_LIMIT
            )
            ids = [hit.product_id for hit in hits]
            subs = []
            if hits and all(may_block(hit, exclusions, rules) for hit in hits):
                curated = [s for hit in hits[:SUBSTITUTES_OF_TOP] for s in hit.substitutions]
                # Alternatives in other categories (#78): "maito" searched by meaning in
                # plant-based drinks. Only the best few, so the engine's price ranking can't
                # prefer a cheap wrong kind (vegan meatballs for "nakit").
                # Without a query vector ("maito" matches no word in a plant-drink name),
                # the category's products by product id, like the same-category step.
                mapped = []
                for to_category in category_substitutes().get(hits[0].category, ()):
                    found = await catalog.search_candidates(
                        db,
                        line.text,
                        line.claims,
                        to_category,
                        limit=MAPPED_SUBSTITUTES,
                        semantic=True,
                    )
                    mapped += found or await catalog.search_candidates(
                        db, None, line.claims, to_category, limit=MAPPED_SUBSTITUTES
                    )
                same_category = await catalog.search_candidates(
                    db, None, line.claims, hits[0].category, limit=SEARCH_LIMIT
                )
                records = {r.product_id: r for r in await catalog.get_products(db, curated)}
                records.update({r.product_id: r for r in [*mapped, *same_category]})
                subs = [
                    i
                    for i in _unique(
                        [
                            *curated,
                            *(r.product_id for r in mapped),
                            *(r.product_id for r in same_category),
                        ]
                    )
                    if i in records and not may_block(records[i], exclusions, rules)
                ]
        unique = _unique([*ids, *subs])
        ranked[line.line_id] = unique
        substitutes[line.line_id] = [i for i in unique if i not in ids]
    return ranked, substitutes


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
