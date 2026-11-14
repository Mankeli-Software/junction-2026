"""The quote service on Postgres (#45). Needs DATABASE_URL.

Service-level tests use the rolled-back `db` session; the tool-call wrapper tests go
through the REST twins with `app_db`.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import engine
from app.adapters import valio
from app.interfaces.deps import DEV_CALLER
from app.interfaces.mcp.server import mcp
from app.main import app
from app.models import AuditEvent, OrderSession, ProductSubstitution, Quote, QuoteLine
from app.schemas import (
    BuildQuoteRequest,
    Claim,
    Decision,
    EngineInput,
    Exclusion,
    GetOrderStatusRequest,
    LineRequest,
    ProductRecord,
    QuoteStatus,
    RequestConfirmationRequest,
    SessionState,
    UpdateQuoteRequest,
)
from app.services import accounts, catalog, dev_caller, quotes, sessions, signing
from app.services.audit import load_rule_set_by_ref
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError
from app.services.policy import get_rule_set

MILK = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)

QUOTE_EVENTS = [
    "request_received",
    "products_searched",
    "availability_checked",
    "candidates_filtered",
    "line_resolved",
]


def lines(*overrides: dict) -> list[LineRequest]:
    return [LineRequest.model_validate({**MILK, **o}) for o in overrides or ({},)]


def build(*overrides: dict) -> BuildQuoteRequest:
    return BuildQuoteRequest(lines=lines(*overrides))


@pytest.fixture
async def caller(db: AsyncSession) -> Caller:
    """The dev caller (lactose-free kitchen), with its rows."""
    await dev_caller.ensure_rows(db, DEV_CALLER)
    return DEV_CALLER


async def other_caller(db: AsyncSession, exclusions: list[Exclusion] = ()) -> Caller:
    account = await accounts.create_demo_account(
        db, f"+35840{random.randrange(10**6, 10**7)}", exclusions, "en"
    )
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=list(exclusions),
        lang="en",
        channel="web",
    )


async def event_types(db: AsyncSession, session_id) -> list[str]:
    rows = await db.scalars(
        select(AuditEvent.type).where(AuditEvent.session_id == session_id).order_by(AuditEvent.seq)
    )
    return list(rows)


async def stored(db: AsyncSession, quote_id: str) -> Quote:
    return await db.get_one(Quote, uuid.UUID(quote_id))


# --- build_quote and replay -------------------------------------------------------------


async def test_build_quote_stores_the_engine_input_and_output_and_replays(db, caller):
    response = await quotes.build_quote(db, caller, build(), now=T0)

    assert response.decision == Decision.ready
    assert response.status == QuoteStatus.ready
    assert response.version == 1
    assert response.lines[0].product_id == "464306"
    quote = await stored(db, response.quote_id)
    assert quote.company_id == caller.company_id
    assert quote.quote_hash == response.quote_hash
    assert quote.jws is None
    assert quote.expires_at is None  # quote_ttl_seconds is null for the event
    assert "rules" not in quote.engine_input
    assert quote.engine_input["candidates"]["l1"]
    assert quote.engine_output["lines"][0]["product_id"] == "464306"
    line = await db.get_one(QuoteLine, (quote.id, "l1"))
    assert (line.product_id, line.line_total_cents) == (
        "464306",
        response.lines[0].line_total_cents,
    )

    # Replay: the stored input and the rule set it names give the same output and hash.
    rules = await load_rule_set_by_ref(db, quote.rules_ref)
    replayed_input = EngineInput.model_validate({**quote.engine_input, "rules": rules})
    replayed = engine.decide(replayed_input)
    assert replayed.model_dump(mode="json") == quote.engine_output
    payload = quotes.quote_payload(
        quote.id,
        quote.version,
        quote.company_id,
        replayed,
        replayed_input.offers,
        issued_at=replayed_input.issued_at,
        expires_at=quote.expires_at,
    )
    assert signing.quote_hash(payload) == quote.quote_hash
    [offer] = [o for o in replayed_input.offers if o.product_id == "464306"]
    assert payload["lines"][0]["claims"] == {
        "stock": response.lines[0].stock_status.value,
        "price": {
            "source": "valio_api",
            "fetched": offer.source.value,
            "fetched_at": payload["lines"][0]["claims"]["price"]["fetched_at"],
        },
        "origin": {"value": response.lines[0].origin, "source": "product_data"},
    }


async def test_build_quote_writes_the_events_in_order(db, caller):
    response = await quotes.build_quote(db, caller, build(), now=T0)
    quote = await stored(db, response.quote_id)

    assert await event_types(db, quote.session_id) == [
        "session_started",
        *QUOTE_EVENTS,
        "quote_built",
    ]
    built = await db.scalar(select(AuditEvent).where(AuditEvent.type == "quote_built"))
    assert built.quote_id == quote.id
    assert built.payload["engine_input"] == quote.engine_input
    assert built.payload["quote_hash"] == quote.quote_hash


async def test_rolling_back_removes_the_quote_and_its_events(db, caller):
    savepoint = await db.begin_nested()
    response = await quotes.build_quote(db, caller, build(), now=T0)
    session_id = (await stored(db, response.quote_id)).session_id
    await savepoint.rollback()

    assert await db.get(Quote, uuid.UUID(response.quote_id)) is None
    assert await event_types(db, session_id) == []


async def test_an_unfinished_quote_gets_the_decision_as_status(db, caller):
    response = await quotes.build_quote(db, caller, build({"text": "zzz"}), now=T0)

    assert response.decision == Decision.needs_clarification
    assert response.status == QuoteStatus.needs_clarification
    assert response.quote_hash is None
    quote = await stored(db, response.quote_id)
    session = await db.get_one(OrderSession, quote.session_id)
    assert session.state == SessionState.needs_clarification
    types = await event_types(db, quote.session_id)
    assert types[-1] == "clarification_asked"

    with pytest.raises(StateError, match="update_quote"):
        await quotes.request_confirmation(
            db, caller, RequestConfirmationRequest(quote_id=response.quote_id), now=T0
        )

    # Answering is an edit.
    answered = await quotes.update_quote(
        db, caller, UpdateQuoteRequest(quote_id=response.quote_id, lines=lines()), now=T0
    )
    assert answered.status == QuoteStatus.ready
    assert (await db.get_one(OrderSession, quote.session_id)).state == SessionState.quote_ready


async def test_a_rejected_quote_sets_the_session_state(db, caller):
    # A product id that doesn't exist is a hard stop.
    response = await quotes.build_quote(db, caller, build({"product_id": "000000"}), now=T0)

    assert response.status == QuoteStatus.rejected
    quote = await stored(db, response.quote_id)
    assert (await db.get_one(OrderSession, quote.session_id)).state == SessionState.rejected
    assert (await event_types(db, quote.session_id))[-1] == "quote_rejected"


# --- Sessions ---------------------------------------------------------------------------


async def test_calls_within_10_minutes_share_a_session(db, caller):
    first = await quotes.build_quote(db, caller, build(), now=T0)
    second = await quotes.build_quote(db, caller, build(), now=T0 + timedelta(minutes=9))
    later = await quotes.build_quote(db, caller, build(), now=T0 + timedelta(minutes=20))

    one, two, three = [(await stored(db, q.quote_id)).session_id for q in (first, second, later)]
    assert one == two
    assert three != two  # 11 minutes after the second call


async def test_another_channel_gets_its_own_session(db, caller):
    web = await quotes.build_quote(db, caller, build(), now=T0)
    connector = caller.model_copy(update={"channel": "connector", "client_name": "Claude"})
    other = await quotes.build_quote(db, connector, build(), now=T0)

    a, b = (
        (await stored(db, web.quote_id)).session_id,
        (await stored(db, other.quote_id)).session_id,
    )
    assert a != b
    session = await db.get_one(OrderSession, b)
    assert (session.channel, session.client_name) == ("connector", "Claude")


async def test_a_call_session_is_used_by_the_calls_tools(db, caller):
    phone = caller.model_copy(update={"channel": "phone", "client_name": "S.I.MO phone"})
    session = await sessions.start_call_session(
        db, phone, call_id="call-1", prompt_version="p1", now=T0
    )

    response = await quotes.build_quote(db, phone, build(), now=T0 + timedelta(minutes=1))

    assert (await stored(db, response.quote_id)).session_id == session.id
    assert session.state == SessionState.quote_ready


# --- update_quote and get_order_status --------------------------------------------------


async def test_update_quote_makes_version_2_and_voids_the_old_one(db, caller):
    old = await quotes.build_quote(db, caller, build(), now=T0)

    new = await quotes.update_quote(
        db,
        caller,
        UpdateQuoteRequest(quote_id=old.quote_id, lines=lines({"quantity": 40})),
        now=T0 + timedelta(hours=1),  # still the quote's own session
    )

    assert new.version == 2
    assert new.parent_quote_id == old.quote_id
    old_row, new_row = await stored(db, old.quote_id), await stored(db, new.quote_id)
    assert old_row.status == QuoteStatus.void
    assert new_row.session_id == old_row.session_id
    status = await quotes.get_order_status(db, caller, GetOrderStatusRequest(quote_id=old.quote_id))
    assert status.status == QuoteStatus.void
    assert status.replaced_by_quote_id == new.quote_id
    assert (await event_types(db, old_row.session_id))[-2:] == ["quote_voided", "quote_edited"]

    with pytest.raises(StateError, match=new.quote_id):
        await quotes.update_quote(
            db, caller, UpdateQuoteRequest(quote_id=old.quote_id, lines=lines()), now=T0
        )


async def test_replaced_by_follows_the_newest_descendant(db, caller):
    v1 = await quotes.build_quote(db, caller, build(), now=T0)
    v2 = await quotes.update_quote(
        db, caller, UpdateQuoteRequest(quote_id=v1.quote_id, lines=lines()), now=T0
    )
    v3 = await quotes.update_quote(
        db, caller, UpdateQuoteRequest(quote_id=v2.quote_id, lines=lines()), now=T0
    )

    status = await quotes.get_order_status(db, caller, GetOrderStatusRequest(quote_id=v1.quote_id))
    assert status.replaced_by_quote_id == v3.quote_id
    assert v3.version == 3


async def test_request_confirmation_sets_pending_and_the_session_waits(db, caller):
    quote = await quotes.build_quote(db, caller, build(), now=T0)

    response = await quotes.request_confirmation(
        db, caller, RequestConfirmationRequest(quote_id=quote.quote_id), now=T0
    )

    assert response.sent_to_masked == "+358 40 *** **12"
    row = await stored(db, quote.quote_id)
    assert row.status == QuoteStatus.pending_confirmation
    session = await db.get_one(OrderSession, row.session_id)
    assert session.state == SessionState.awaiting_confirmation
    with pytest.raises(StateError):
        await quotes.request_confirmation(
            db, caller, RequestConfirmationRequest(quote_id=quote.quote_id), now=T0
        )


async def test_another_companys_quote_is_not_found(db, caller):
    quote = await quotes.build_quote(db, caller, build(), now=T0)
    stranger = await other_caller(db)

    with pytest.raises(NotFoundError):
        await quotes.get_order_status(db, stranger, GetOrderStatusRequest(quote_id=quote.quote_id))
    with pytest.raises(NotFoundError):
        await quotes.update_quote(
            db, stranger, UpdateQuoteRequest(quote_id=quote.quote_id, lines=lines()), now=T0
        )
    with pytest.raises(NotFoundError):
        await quotes.request_confirmation(
            db, stranger, RequestConfirmationRequest(quote_id=quote.quote_id), now=T0
        )
    with pytest.raises(NotFoundError):
        await quotes.get_order_status(db, caller, GetOrderStatusRequest(quote_id="nope"))


# --- Candidates and offers --------------------------------------------------------------


def test_the_cap_keeps_each_lines_best_candidates_first():
    ranked = {"a": ["a1", "a2", "a3", "a4"], "b": ["b1", "a1", "b2"], "c": ["c1"]}

    assert quotes.cap_candidates(ranked, 4) == {"a1", "b1", "c1", "a2"}
    assert quotes.cap_candidates(ranked, 100) == {"a1", "a2", "a3", "a4", "b1", "b2", "c1"}


async def test_over_100_candidates_are_capped(db, caller, monkeypatch):
    template = (await catalog.get_products(db, ["464306"]))[0]

    async def search(db, q, claims, category, limit=20):
        return [template.model_copy(update={"product_id": f"{q}{i:03}"}) for i in range(60)]

    async def get_products(db, ids):
        return [template.model_copy(update={"product_id": i, "substitutions": []}) for i in ids]

    monkeypatch.setattr(catalog, "search_candidates", search)
    monkeypatch.setattr(catalog, "get_products", get_products)
    request = build({"line_id": "a", "text": "a"}, {"line_id": "b", "text": "b"})

    response = await quotes.build_quote(db, caller, request, now=T0)

    quote = await stored(db, response.quote_id)
    candidates = quote.engine_input["candidates"]
    assert candidates["a"] == [f"a{i:03}" for i in range(50)]
    assert candidates["b"] == [f"b{i:03}" for i in range(50)]
    ids = [p["product_id"] for p in quote.engine_input["products"]]
    assert ids == sorted(ids) and len(ids) == 100
    searched = await db.scalar(select(AuditEvent).where(AuditEvent.type == "products_searched"))
    assert searched.payload["capped"] is True
    assert searched.payload["candidate_count"] == 100


async def test_the_cap_holds_with_substitutes(db, monkeypatch):
    """Lines whose hits may all be blocked get substitutes, and still at most 100 ids:
    each line's hits come before any substitute."""
    milk = (await catalog.get_products(db, ["464306"]))[0]
    oat = (await catalog.get_products(db, ["460825"]))[0]

    async def search(db, q, claims, category, limit=20):
        if q:  # the line's search: milks, each line in a category of its own
            return [
                milk.model_copy(update={"category": q, "product_id": f"{q}{i:02}"})
                for i in range(20)
            ]
        # The second search, in the top hit's category: milk-free products.
        return [oat.model_copy(update={"product_id": f"{category}s{i:02}"}) for i in range(20)]

    async def get_products(db, ids):
        return []  # no curated substitutes

    monkeypatch.setattr(catalog, "search_candidates", search)
    monkeypatch.setattr(catalog, "get_products", get_products)
    milk_free = await other_caller(db, [Exclusion.milk_free])
    request = build(*({"line_id": f"l{n}", "text": f"q{n}"} for n in range(4)))

    response = await quotes.build_quote(db, milk_free, request, now=T0)

    quote = await stored(db, response.quote_id)
    candidates = quote.engine_input["candidates"]
    searched = await searched_lines(db, quote)
    assert len({i for ids in candidates.values() for i in ids}) == 100
    for n in range(4):
        hits = [f"q{n}{i:02}" for i in range(20)]
        substitutes = [f"q{n}s{i:02}" for i in range(5)]
        assert candidates[f"l{n}"] == hits + substitutes
        assert searched[f"l{n}"]["substitute_ids"] == substitutes


async def test_a_failed_offer_reaches_the_engine(db, caller, monkeypatch):
    async def get_offers(ids, needed_by):
        return [valio._failed(i) for i in ids]

    monkeypatch.setattr(valio, "get_offers", get_offers)
    # Only lactose-free hits, so every candidate the kitchen allows lacks an offer: the
    # engine asks back (a low-lactose hit would be rejected for the allergen first).
    request = build({"claims": ["lactose_free"]})

    response = await quotes.build_quote(db, caller, request, now=T0)

    quote = await stored(db, response.quote_id)
    assert quote.engine_input["offers"] and not any(o["ok"] for o in quote.engine_input["offers"])
    assert response.decision == Decision.needs_clarification


async def test_a_named_product_brings_its_curated_substitutes(db, caller):
    response = await quotes.build_quote(
        db, caller, build({"product_id": "464306", "text": None}), now=T0
    )

    quote = await stored(db, response.quote_id)
    # 464201 is 464306's curated substitute in the product file.
    assert quote.engine_input["candidates"]["l1"] == ["464306", "464201"]


# --- Real search and substitute candidates (#30) ----------------------------------------


async def searched_lines(db: AsyncSession, quote: Quote) -> dict[str, dict]:
    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.type == "products_searched", AuditEvent.quote_id == quote.id
        )
    )
    return {line["line_id"]: line for line in event.payload["lines"]}


async def test_a_lactose_free_kitchen_gets_a_lactose_free_milk(db, caller):
    response = await quotes.build_quote(db, caller, build(), now=T0)

    assert response.decision == Decision.ready
    quote = await stored(db, response.quote_id)
    chosen = next(
        p for p in quote.engine_input["products"] if p["product_id"] == response.lines[0].product_id
    )
    assert "lactose_free" in chosen["claims"]
    assert "maito" in chosen["name"]["fi"].lower()
    # Lactose-free milks pass the kitchen, so no substitutes are added.
    assert (await searched_lines(db, quote))["l1"]["substitute_ids"] == []


async def test_a_milk_free_kitchen_asking_for_milk_gets_a_rejection_with_a_next_step(db):
    milk_free = await other_caller(db, [Exclusion.milk_free])

    response = await quotes.build_quote(db, milk_free, build(), now=T0)

    assert response.decision == Decision.rejected
    assert response.status == QuoteStatus.rejected
    (rejection,) = response.rejections
    assert rejection.reason_code == "ALLERGEN_CONFLICT"
    assert rejection.next_step.en
    quote = await stored(db, response.quote_id)
    # Every hit lists milk, and so does every other product in the milk category, so no
    # substitute gets past the hint.
    assert (await searched_lines(db, quote))["l1"]["substitute_ids"] == []


async def test_a_milk_free_kitchen_gets_a_curated_oat_drink_for_milk(db, monkeypatch):
    # A curated pair from the top hit for "maito" to the oat drink, in this test only.
    db.add(ProductSubstitution(product_id="464119", substitute_product_id="460825", position=9))
    await db.flush()
    real_offers = valio.get_offers

    async def get_offers(ids, needed_by):
        # The oat drink has no recorded offer; it borrows the milk's.
        offers = {o.product_id: o for o in await real_offers(sorted({*ids, "464306"}), needed_by)}
        offers["460825"] = offers["464306"].model_copy(update={"product_id": "460825"})
        return [offers[i] for i in ids]

    monkeypatch.setattr(valio, "get_offers", get_offers)
    milk_free = await other_caller(db, [Exclusion.milk_free])

    response = await quotes.build_quote(db, milk_free, build(), now=T0)

    quote = await stored(db, response.quote_id)
    assert (await searched_lines(db, quote))["l1"]["substitute_ids"] == ["460825"]
    assert quote.engine_input["candidates"]["l1"][-1] == "460825"
    assert response.decision == Decision.ready
    assert response.lines[0].product_id == "460825"


async def test_candidate_order_is_deterministic(db, caller):
    milk_free = await other_caller(db, [Exclusion.milk_free])
    request = build({"line_id": "a"}, {"line_id": "b", "text": "naudan jauheliha"})

    for who in (caller, milk_free):
        first = await quotes.build_quote(db, who, request, now=T0)
        second = await quotes.build_quote(db, who, request, now=T0)

        a = (await stored(db, first.quote_id)).engine_input["candidates"]
        b = (await stored(db, second.quote_id)).engine_input["candidates"]
        assert a == b
        assert len(a["a"]) == len(set(a["a"])) and "464306" in a["a"]


def record(**changes) -> ProductRecord:
    base = {
        "product_id": "1",
        "name": {"fi": "x", "en": "x"},
        "category": "10400",
        "sales_unit": "ST",
        "base_unit": "ST",
        "units": ["ST"],
        "unit_conversions": [],
        "allergens": [],
        "allergen_listing": True,
        "claims": [],
        "origin": None,
        "image_url": None,
        "substitutions": [],
    }
    return ProductRecord.model_validate(base | changes)


@pytest.mark.parametrize(
    ("allergens", "claims", "exclusions", "blocked"),
    [
        ([], [], [], False),
        ([("AM", "CONTAINS")], [], [], False),  # no exclusion
        ([("AM", "CONTAINS")], [], [Exclusion.milk_free], True),
        ([("AM", "MAY_CONTAIN")], [], [Exclusion.milk_free], True),
        ([("AM", "FREE_FROM")], [], [Exclusion.milk_free], False),
        ([("AM", "CONTAINS")], [], [Exclusion.lactose_free], True),
        ([("AM", "CONTAINS")], [Claim.lactose_free], [Exclusion.lactose_free], False),
        ([("AM", "CONTAINS")], [Claim.lactose_free], [Exclusion.milk_free], True),
        ([], [], [Exclusion.vegan], True),  # vegan requires the claim
        ([], [Claim.vegan], [Exclusion.vegan], False),
    ],
)
def test_may_be_blocked_follows_the_kitchen_rules(allergens, claims, exclusions, blocked):
    product = record(allergens=[{"code": c, "containment": k} for c, k in allergens], claims=claims)
    assert quotes.may_be_blocked(product, exclusions, get_rule_set()) is blocked


# --- The tool-call wrapper (REST twins) -------------------------------------------------


@pytest.mark.usefixtures("dev_caller")
async def test_every_tool_call_writes_tool_called_and_tool_returned(app_db: AsyncEngine):
    client = TestClient(app)

    quote = client.post("/api/v1/quotes", json={"lines": [MILK]}).json()
    missing = client.get("/api/v1/quotes/00000000-0000-4000-8000-00000000dead/status")

    assert missing.status_code == 404
    async with AsyncSession(app_db) as db:
        session_id = (await db.get_one(Quote, uuid.UUID(quote["quote_id"]))).session_id
        events = list(
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.session_id == session_id)
                .order_by(AuditEvent.seq)
            )
        )
        quotes_in_db = await db.scalar(select(func.count()).select_from(Quote))
    assert [e.type for e in events] == [
        "session_started",
        "tool_called",
        *QUOTE_EVENTS,
        "quote_built",
        "tool_returned",
        "tool_called",
        "tool_returned",
    ]
    called, returned = events[1], events[-3]
    assert called.payload == {"tool": "build_quote", "arguments": {"lines": [MILK | {
        "product_id": None, "usual": False, "claims": [], "category": None,
        "package_word": None, "recipe_ref": None, "group": None,
    }]}}  # fmt: skip
    assert returned.payload["response"]["quote_id"] == quote["quote_id"]
    assert returned.quote_id is not None
    assert events[-1].payload == {"tool": "get_order_status", "error": "quote not found"}
    assert quotes_in_db == 1


@pytest.mark.usefixtures("dev_caller")
async def test_build_quote_over_mcp_stores_a_quote_that_replays(app_db: AsyncEngine):
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("build_quote", {"lines": [MILK]})

    assert not result.isError, result.content
    async with AsyncSession(app_db) as db:
        quote = await stored(db, result.structuredContent["quote_id"])
        rules = await load_rule_set_by_ref(db, quote.rules_ref)
    assert quote.quote_hash == result.structuredContent["quote_hash"]
    replayed_input = EngineInput.model_validate({**quote.engine_input, "rules": rules})
    replayed = engine.decide(replayed_input)
    payload = quotes.quote_payload(
        quote.id,
        quote.version,
        quote.company_id,
        replayed,
        replayed_input.offers,
        issued_at=replayed_input.issued_at,
        expires_at=quote.expires_at,
    )
    assert signing.quote_hash(payload) == quote.quote_hash


# --- Chat panel helpers -----------------------------------------------------------------


@pytest.mark.usefixtures("app_db", "dev_caller")
def test_current_quote_and_one_quote():
    client = TestClient(app)
    assert client.get("/api/v1/quotes/current").status_code == 404

    first = client.post("/api/v1/quotes", json={"lines": [MILK]}).json()
    second = client.post(
        f"/api/v1/quotes/{first['quote_id']}/update", json={"lines": [MILK | {"quantity": 40}]}
    ).json()

    assert client.get("/api/v1/quotes/current").json() == second
    old = client.get(f"/api/v1/quotes/{first['quote_id']}").json()
    assert old == first | {"status": "void"}
    assert client.get("/api/v1/quotes/nope").status_code == 404
