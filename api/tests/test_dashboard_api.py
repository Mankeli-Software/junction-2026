"""The public dashboard endpoints and the live feed on a real Postgres (#49). Needs DATABASE_URL.

The app commits for real here (`app_db`), because the stream only hears committed rows;
`app_db` empties the tables afterwards.
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.interfaces.deps import DEV_CALLER
from app.interfaces.rest.dashboard import OrderFilter
from app.main import app
from app.models import Company, KitchenProfile, OrderSession, Quote, User
from app.schemas import (
    BuildQuoteRequest,
    Channel,
    LineRequest,
    Localized,
    SessionState,
    StateGroup,
)
from app.services import audit, dev_caller, quotes
from app.services.caller import Caller
from app.services.dashboard.feed import DashboardFeed, start_feed
from app.services.dashboard.stream import Broadcaster, StreamEvent, get_broadcaster
from app.settings import get_settings
from tests.test_confirmation_page import STOCK_FLAG, Page, ordered
from tests.test_dashboard_routes import Stream

API = "/api/v1/public"
MILK = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}

# A confirmation token in a URL, a full number, a full email: none may leave the API.
TOKEN_URL = re.compile(r"/c/[A-Za-z0-9_\-]{6,}")
FULL_PHONE = re.compile(r"\+\d[\d \-]{7,}\d")
FULL_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]+\.[A-Za-z]{2,}")


@pytest.fixture
def client(app_db: AsyncEngine) -> TestClient:
    return TestClient(app, base_url="http://localhost")


async def _seed(
    engine: AsyncEngine,
    *,
    state: SessionState = SessionState.in_conversation,
    channel: str = "phone",
    last_activity: datetime | None = None,
    started_at: datetime | None = None,
    total_cents: int | None = None,
    client_name: str | None = None,
    email: str | None = None,
    company: str | None = None,
) -> uuid.UUID:
    """One company, user and session (and a minimal quote when `total_cents` is set)."""
    now = datetime.now(UTC)
    last_activity = last_activity or now
    phone = f"+35840{uuid.uuid4().int % 10**7:07d}"
    async with AsyncSession(engine) as db:
        company_id = await db.scalar(
            insert(Company)
            .values(name=company or f"Oy {uuid.uuid4().hex[:8]}", phone_e164=phone)
            .returning(Company.id)
        )
        await db.execute(insert(KitchenProfile).values(company_id=company_id, exclusions=[]))
        user_id = await db.scalar(
            insert(User)
            .values(company_id=company_id, phone_e164=phone, email=email)
            .returning(User.id)
        )
        session_id = await db.scalar(
            insert(OrderSession)
            .values(
                user_id=user_id,
                company_id=company_id,
                channel=channel,
                client_name=client_name,
                state=state.value,
                state_since=last_activity,
                started_at=started_at or last_activity,
                last_activity_at=last_activity,
            )
            .returning(OrderSession.id)
        )
        if total_cents is not None:
            await db.execute(
                insert(Quote).values(
                    session_id=session_id,
                    company_id=company_id,
                    version=1,
                    status="ready",
                    decision="ready",
                    rules_ref="test",
                    issued_at=last_activity,
                    total_cents=total_cents,
                    engine_input={"lines": [MILK]},
                    engine_output={"lines": [], "flags": [], "rejections": [], "delivery": None},
                )
            )
        await db.commit()
    return session_id


def _cards(overview: dict) -> list[dict]:
    return [card for company in overview["companies"] for card in company["orders"]]


async def _built_quote(engine: AsyncEngine, caller: Caller = DEV_CALLER) -> str:
    """A real `build_quote` through the service, committed. Returns the session id."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        await dev_caller.ensure_rows(db, caller)
        response = await quotes.build_quote(
            db, caller, BuildQuoteRequest(lines=[LineRequest.model_validate(MILK)])
        )
        quote = await db.get_one(Quote, uuid.UUID(response.quote_id))
        await audit.record(
            db,
            type="buyer_said",
            actor="buyer",
            session_id=quote.session_id,
            payload={"text": "Tarvitsen 20 litraa maitoa.", "lang": "fi", "transcript": True},
            text=Localized(fi='"Tarvitsen 20 litraa maitoa."', en='"I need 20 litres of milk."'),
        )
        await db.commit()
        return str(quote.session_id)


# --- Overview ---------------------------------------------------------------------------


async def test_totals_and_grouping_for_one_session_in_each_state(client, app_db):
    t = datetime.now(UTC)
    ids = {}
    for i, state in enumerate(SessionState):
        ids[state] = await _seed(
            app_db,
            state=state,
            last_activity=t - timedelta(seconds=len(SessionState) - i),
            total_cents=1000 + i if state == SessionState.confirmed else None,
        )

    overview = client.get(f"{API}/orders").json()

    totals = overview["totals"]
    assert {k: totals[k] for k in ("active", "waiting", "confirmed", "attention")} == {
        "active": 3,
        "waiting": 2,
        "confirmed": 1,
        "attention": 5,
    }
    confirmed_index = list(SessionState).index(SessionState.confirmed)
    assert totals["confirmed_cents"] == 1000 + confirmed_index
    assert totals["by_channel"] == {"phone": 13, "web_chat": 0, "webmcp": 0, "mcp": 0}
    cards = _cards(overview)
    assert {c["session_id"]: c["state"] for c in cards} == {
        str(sid): state.value for state, sid in ids.items()
    }
    # Newest activity first: the last state seeded is the newest.
    assert cards[0]["state"] == list(SessionState)[-1].value
    attention = next(c for c in cards if c["state"] == "sms_failed")
    assert attention["next_step"]["en"].startswith("Next:")
    assert next(c for c in cards if c["state"] == "confirmed")["next_step"] is None
    assert overview["business_now"] == "2026-11-12T09:00:00+02:00"


async def test_an_idle_mcp_session_shows_as_ended(client, app_db):
    now = datetime.now(UTC)
    idle = await _seed(
        app_db, channel="connector", client_name="Claude", last_activity=now - timedelta(minutes=11)
    )
    recent = await _seed(app_db, channel="web", last_activity=now - timedelta(minutes=9))
    call = await _seed(app_db, channel="phone", last_activity=now - timedelta(minutes=30))

    overview = client.get(f"{API}/orders").json()

    cards = {c["session_id"]: c for c in _cards(overview)}
    assert cards[str(idle)]["state"] == "abandoned"
    assert cards[str(idle)]["channel"] == "mcp" and cards[str(idle)]["client"] == "Claude"
    since = datetime.fromisoformat(cards[str(idle)]["state_since"])
    assert abs(since - (now - timedelta(minutes=1))) < timedelta(seconds=5)
    assert cards[str(recent)]["state"] == "in_conversation"
    assert cards[str(recent)]["channel"] == "webmcp"
    assert cards[str(recent)]["client"] == "browser agent"
    # A call has a hang-up: it stays active until the relay ends it.
    assert cards[str(call)]["state"] == "in_conversation"
    assert overview["totals"]["active"] == 2
    # The summary agrees.
    assert client.get(f"{API}/orders/{idle}").json()["state"] == "abandoned"


async def test_state_and_channel_filters(client, app_db):
    active_phone = await _seed(app_db)
    waiting_mcp = await _seed(app_db, state=SessionState.awaiting_confirmation, channel="connector")
    await _seed(app_db, state=SessionState.cancelled, channel="web_chat")

    def ids(query: str) -> set[str]:
        response = client.get(f"{API}/orders{query}")
        assert response.status_code == 200
        return {c["session_id"] for c in _cards(response.json())}

    assert len(ids("")) == 3
    assert ids("?state=active") == {str(active_phone)}
    assert ids("?state=waiting") == {str(waiting_mcp)}
    assert ids("?channel=mcp") == {str(waiting_mcp)}
    assert ids("?state=active&channel=mcp") == set()
    assert ids("?since=2999-01-01T00:00:00Z") == set()
    # The totals ignore the filters.
    assert client.get(f"{API}/orders?state=active").json()["totals"]["waiting"] == 1
    assert client.get(f"{API}/orders?state=bogus").status_code == 422


async def test_at_most_200_cards_newest_first(client, app_db):
    t = datetime.now(UTC)
    async with AsyncSession(app_db) as db:
        company_id = await db.scalar(
            insert(Company).values(name="Iso Oy", phone_e164="+358401111111").returning(Company.id)
        )
        user_id = await db.scalar(
            insert(User)
            .values(company_id=company_id, phone_e164="+358401111111")
            .returning(User.id)
        )
        await db.execute(
            insert(OrderSession),
            [
                {
                    "user_id": user_id,
                    "company_id": company_id,
                    "channel": "phone",
                    "state": "in_conversation",
                    "state_since": t - timedelta(seconds=i),
                    "started_at": t - timedelta(seconds=i),
                    "last_activity_at": t - timedelta(seconds=i),
                }
                for i in range(205)
            ],
        )
        await db.commit()

    overview = client.get(f"{API}/orders").json()

    cards = _cards(overview)
    assert len(cards) == 200
    assert overview["totals"]["active"] == 205
    times = [c["state_since"] for c in cards]
    assert times == sorted(times, reverse=True)


async def test_event_start_hides_older_sessions(client, app_db, monkeypatch):
    now = datetime.now(UTC)
    await _seed(app_db, started_at=now - timedelta(days=2), last_activity=now)
    newer = await _seed(app_db)
    monkeypatch.setenv("EVENT_START", (now - timedelta(days=1)).isoformat())
    get_settings.cache_clear()
    try:
        overview = client.get(f"{API}/orders").json()
    finally:
        monkeypatch.delenv("EVENT_START")
        get_settings.cache_clear()
    assert [c["session_id"] for c in _cards(overview)] == [str(newer)]
    assert overview["totals"]["by_channel"]["phone"] == 1


# --- One order --------------------------------------------------------------------------


async def test_summary_steps_transcript_and_events_of_a_built_quote(client, app_db):
    session_id = await _built_quote(app_db)

    overview = client.get(f"{API}/orders").json()
    card = _cards(overview)[0]
    assert card["session_id"] == session_id
    assert card["state"] == "quote_ready"
    assert card["title"] == {"fi": "20 l maito", "en": "20 l maito"}
    assert card["line_count"] == 1 and card["total_cents"] > 0
    assert card["identity_masked"] == "+358 40 *** **12"
    assert card["step_text"]["en"] == '"I need 20 litres of milk."'
    assert overview["companies"][0]["name"] == "Hassu Hauki Oy"
    assert overview["companies"][0]["exclusions"] == ["lactose_free"]

    summary = client.get(f"{API}/orders/{session_id}").json()
    assert summary["company"]["name"] == "Hassu Hauki Oy"
    assert summary["channel"] == "webmcp"
    assert summary["quote"]["version"] == 1 and len(summary["quote"]["hash"]) == 64
    assert summary["signature_valid"] is True
    [request] = summary["requests"]
    assert request["request_id"] == "l1"
    assert request["lines"][0]["product_id"] == "464306"
    assert request["lines"][0]["trace"]["found"] >= 1

    steps = client.get(f"{API}/orders/{session_id}/steps").json()
    assert [s["order_index"] for s in steps] == list(range(1, len(steps) + 1))
    assert steps[0]["type"] == "session_started" and steps[0]["session_prev_hash"] is None
    assert all(s["session_id"] == session_id for s in steps)
    assert steps[-1]["type"] == "buyer_said"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", steps[0]["at"])

    [line] = client.get(f"{API}/orders/{session_id}/transcript").json()
    assert {k: line[k] for k in ("who", "text", "lang")} == {
        "who": "buyer",
        "text": "Tarvitsen 20 litraa maitoa.",
        "lang": "fi",
    }

    events = client.get(f"{API}/orders/{session_id}/events")
    assert "content-disposition" not in events.headers
    body = events.json()
    assert [e["seq"] for e in body] == [s["seq"] for s in steps]
    assert body[0]["payload"]["channel"] == "web"
    assert body[0]["identity_masked"] == "+358 40 *** **12"
    # The raw sentences, for the browser's payload hash.
    assert body[-1]["text_fi"] == '"Tarvitsen 20 litraa maitoa."'
    download = client.get(f"{API}/orders/{session_id}/events?download=1")
    assert download.headers["content-disposition"].startswith("attachment; filename=")
    assert download.json() == body


async def test_transcript_line_keeps_the_event_time(client, app_db):
    session_id = await _built_quote(app_db)
    [line] = client.get(f"{API}/orders/{session_id}/transcript").json()
    last = client.get(f"{API}/orders/{session_id}/steps").json()[-1]
    assert datetime.fromisoformat(line["at"]) == datetime.fromisoformat(
        last["at"].replace("Z", "+00:00")
    )


@pytest.mark.parametrize("suffix", ["", "/steps", "/transcript", "/events"])
async def test_unknown_session_gives_404(client, app_db, suffix):
    assert client.get(f"{API}/orders/{uuid.uuid4()}{suffix}").status_code == 404
    assert client.get(f"{API}/orders/not-a-uuid{suffix}").status_code == 404


async def test_verify_fails_at_the_tampered_seq(client, app_db):
    session_id = await _built_quote(app_db)
    other = await _built_quote(
        app_db,
        DEV_CALLER.model_copy(update={"channel": "connector", "client_name": "Claude"}),
    )
    assert other != session_id

    ok = client.get(f"{API}/audit/verify", params={"session_id": session_id}).json()
    assert ok == {
        "ok": True,
        "checked": ok["checked"],
        "first_bad_seq": None,
        "signature_valid": True,
    }
    assert ok["checked"] == len(client.get(f"{API}/orders/{session_id}/steps").json())
    assert client.get(f"{API}/audit/verify").json()["ok"] is True

    steps = client.get(f"{API}/orders/{session_id}/steps").json()
    bad_seq = steps[2]["seq"]
    async with app_db.begin() as conn:
        # How #41's tests tamper: switch the append-only guard off for one change.
        await conn.execute(
            text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only")
        )
        await conn.execute(
            text("UPDATE audit_events SET text_en = 'changed' WHERE seq = :seq"), {"seq": bad_seq}
        )
        await conn.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only"))

    bad = client.get(f"{API}/audit/verify", params={"session_id": session_id}).json()
    assert (bad["ok"], bad["first_bad_seq"]) == (False, bad_seq)
    assert client.get(f"{API}/audit/verify").json()["first_bad_seq"] == bad_seq
    assert client.get(f"{API}/audit/verify", params={"session_id": other}).json()["ok"] is True
    assert (
        client.get(f"{API}/audit/verify", params={"session_id": str(uuid.uuid4())}).status_code
        == 404
    )


# --- Redaction --------------------------------------------------------------------------


async def test_no_endpoint_shows_a_token_link_or_full_number(client, app_db):
    session_id = await _built_quote(app_db)
    connector = await _seed(
        app_db,
        channel="connector",
        client_name="Claude +358401234567 jane.doe@example.com",
        email="jane.doe@example.com",
    )
    # Plant what the writer would refuse: a link with a token, a full number and email.
    async with app_db.begin() as conn:
        await conn.execute(
            text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only")
        )
        await conn.execute(
            text(
                "UPDATE audit_events SET payload = CAST(:p AS jsonb), "
                "text_en = 'see https://simo.mankeli.co/c/AbCdEf123456_x' "
                "WHERE session_id = :sid"
            ),
            {
                "sid": uuid.UUID(session_id),
                "p": json.dumps(
                    {
                        "link": "https://simo.mankeli.co/c/AbCdEf123456_x",
                        "token": "AbCdEf123456_x",
                        "note": "sent /c/AbCdEf123456_x to +358401234512, jane.doe@example.com",
                    }
                ),
            },
        )
        await conn.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only"))

    hub = Broadcaster()
    app.dependency_overrides[get_broadcaster] = lambda: hub
    try:
        async with Stream(f"{API}/stream") as s:
            snapshot = (await s.next_event())["data"]
    finally:
        app.dependency_overrides.pop(get_broadcaster, None)

    outputs = {"stream snapshot": snapshot}
    for path in [
        "/orders",
        "/orders?channel=mcp",
        f"/orders/{session_id}",
        f"/orders/{session_id}/steps",
        f"/orders/{session_id}/transcript",
        f"/orders/{session_id}/events",
        f"/orders/{session_id}/events?download=1",
        f"/orders/{connector}",
        f"/orders/{connector}/events",
        f"/audit/verify?session_id={session_id}",
        "/audit/verify",
    ]:
        response = client.get(f"{API}{path}")
        assert response.status_code == 200, path
        outputs[path] = response.text

    for where, body in outputs.items():
        assert not TOKEN_URL.search(body), where
        assert not FULL_PHONE.search(body), where
        assert not FULL_EMAIL.search(body), where
        assert '"token"' not in body and '"link"' not in body, where
    events = client.get(f"{API}/orders/{session_id}/events").json()
    assert "/c/…" in events[0]["payload"]["note"]
    assert "+358 40 *** **12" in events[0]["payload"]["note"]
    assert client.get(f"{API}/orders/{connector}").json()["identity_masked"] == "j***@example.com"


# --- Stream -----------------------------------------------------------------------------


async def _next(events, kind: str, session_id: str, within: float) -> dict:
    async with asyncio.timeout(within):
        async for sse in events:
            if sse.event == kind:
                data = json.loads(sse.data)
                if data.get("session_id", data.get("order", {}).get("session_id")) == session_id:
                    return {"id": sse.id, "data": data}
    raise AssertionError("stream ended")


async def _empty_snapshot() -> dict:
    return {}


def _test_dsn(engine: AsyncEngine) -> str:
    return engine.url.render_as_string(hide_password=False)


async def test_build_quote_reaches_the_stream_within_a_second(app_db):
    hub = Broadcaster()
    listener, feed = start_feed(
        hub, dsn=_test_dsn(app_db), sessionmaker=async_sessionmaker(app_db, expire_on_commit=False)
    )
    try:
        async with asyncio.timeout(5):
            await feed.ready.wait()
        events = hub.subscribe(_empty_snapshot)
        assert (await anext(events)).event == "snapshot"

        session_id = await _built_quote(app_db)
        start = asyncio.get_running_loop().time()
        update = await _next(events, "order_updated", session_id, within=1.0)
        assert asyncio.get_running_loop().time() - start < 1.0

        order = update["data"]["order"]
        assert order["state"] == "quote_ready" and order["channel"] == "webmcp"
        assert update["data"]["company"]["name"] == "Hassu Hauki Oy"
        assert update["data"]["totals"]["active"] == 1
        assert update["id"] == str(feed.last_id)
        await events.aclose()

        # The transcript line and the steps came out as well, with status_events ids.
        history = [e for e in hub._history if e.event in ("step", "transcript")]
        assert {e.event for e in history} == {"step", "transcript"}
        ids = [e.id for e in hub._history]
        assert ids == sorted(ids)
    finally:
        await listener.stop()


async def test_last_event_id_resume_gets_missed_events_then_live_ones(app_db):
    hub = Broadcaster()
    feed = DashboardFeed(hub, async_sessionmaker(app_db, expire_on_commit=False))
    await feed.on_connect()  # starts after the newest row
    session_id = await _built_quote(app_db)
    # The listener was down: a reconnect catches up from the table.
    await feed.on_connect()
    published = list(hub._history)
    assert published and all(e.id is not None for e in published)
    first_id = published[0].id
    expected = [e for e in published if e.id >= first_id]

    events = hub.subscribe(_empty_snapshot, last_event_id=first_id)
    missed = [await anext(events) for _ in expected]
    assert [(e.event, int(e.id)) for e in missed] == [(e.event, e.id) for e in expected]
    assert missed[-1].event == "order_updated"

    # Then live: another event in the same session.
    async with AsyncSession(app_db) as db:
        await audit.record(
            db,
            type="agent_said",
            actor="agent",
            session_id=uuid.UUID(session_id),
            payload={"text": "Lähetänkö tarjouksen?", "lang": "fi", "transcript": True},
            text=Localized(fi='"Lähetänkö tarjouksen?"', en='"Shall I send the quote?"'),
        )
        await db.commit()
    await feed.on_notify(str(feed.last_id + 1))
    live = await _next(events, "transcript", session_id, within=1.0)
    assert int(live["id"]) > int(missed[-1].id)
    assert live["data"]["line"]["who"] == "agent"
    assert live["data"]["line"]["text"] == "Lähetänkö tarjouksen?"
    await events.aclose()


# --- Orders and acknowledgements from the confirmation page (#47) -----------------------


async def _session_of(engine: AsyncEngine, quote_id: str) -> str:
    async with AsyncSession(engine) as db:
        quote = await db.get_one(Quote, uuid.UUID(quote_id))
        return str(quote.session_id)


def _card(client: TestClient, session_id: str) -> dict:
    cards = _cards(client.get(f"{API}/orders").json())
    [card] = [c for c in cards if c["session_id"] == session_id]
    return card


def _last_update(hub: Broadcaster, session_id: str) -> dict:
    return [
        e.data
        for e in hub._history
        if e.event == "order_updated" and e.data["order"]["session_id"] == session_id
    ][-1]


@pytest.mark.usefixtures("no_caller")
async def test_a_confirmed_order_shows_its_number_and_the_checked_flags(client, app_db):
    hub = Broadcaster()
    feed = DashboardFeed(hub, async_sessionmaker(app_db, expire_on_commit=False))
    await feed.on_connect()

    _, quote, token = ordered()
    session_id = await _session_of(app_db, quote["quote_id"])
    page = Page(token)
    view = page.view()
    assert page.ack(view["quote"]["quote_hash"], STOCK_FLAG).status_code == 204
    # An edit makes version 2: the order is on it, and the tick carries over.
    edit = {"quote_hash": view["quote"]["quote_hash"], "op": "set_quantity", "line_id": "l2"}
    assert page.post("edits", {**edit, "quantity": 6}).status_code == 204
    view = page.view()
    receipt = page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]}).json()
    number = receipt["order_number"]
    assert re.fullmatch(r"D-\d{4,}", number)

    card = _card(client, session_id)
    assert card["state"] == "confirmed" and card["order_number"] == number

    summary = client.get(f"{API}/orders/{session_id}").json()
    assert summary["order_number"] == number
    assert summary["quote"]["version"] == 2
    stock = next(f for f in summary["flags"] if f["flag_key"] == STOCK_FLAG)
    assert stock["acknowledged_at"] is not None
    assert summary["status_line"]["en"] == "by the buyer, after checking 1 flag"

    await feed.catch_up()
    update = _last_update(hub, session_id)
    assert update["order"]["state"] == "confirmed"
    assert update["order"]["order_number"] == number
    assert update["totals"]["confirmed"] == 1
    assert update["totals"]["confirmed_cents"] == view["quote"]["total_cents"]


@pytest.mark.usefixtures("no_caller")
async def test_an_unconfirmed_session_has_no_order_number(client, app_db):
    hub = Broadcaster()
    feed = DashboardFeed(hub, async_sessionmaker(app_db, expire_on_commit=False))
    await feed.on_connect()

    _, quote, token = ordered()
    session_id = await _session_of(app_db, quote["quote_id"])
    page = Page(token)
    view = page.view()
    assert page.ack(view["quote"]["quote_hash"], STOCK_FLAG).status_code == 204

    card = _card(client, session_id)
    assert card["state"] == "link_opened" and card["order_number"] is None

    summary = client.get(f"{API}/orders/{session_id}").json()
    assert summary["order_number"] is None
    stock = next(f for f in summary["flags"] if f["flag_key"] == STOCK_FLAG)
    assert stock["acknowledged_at"] is not None
    others = [f for f in summary["flags"] if f["flag_key"] != STOCK_FLAG]
    assert all(f["acknowledged_at"] is None for f in others)

    await feed.catch_up()
    update = _last_update(hub, session_id)
    assert update["order"]["state"] == "link_opened"
    assert update["order"]["order_number"] is None


@pytest.mark.usefixtures("no_caller")
async def test_a_cancelled_session_shows_as_cancelled_without_a_number(client, app_db):
    _, quote, token = ordered()
    session_id = await _session_of(app_db, quote["quote_id"])
    page = Page(token)
    view = page.view()
    assert page.post("cancel", {"quote_hash": view["quote"]["quote_hash"]}).status_code == 204

    card = _card(client, session_id)
    assert card["state"] == "cancelled" and card["order_number"] is None


# --- Per-subscriber filter (no database) ------------------------------------------------


def _update(session_id: str, state: str, channel: str) -> StreamEvent:
    return StreamEvent(
        "order_updated",
        {"order": {"session_id": session_id, "state": state, "channel": channel}},
        1,
    )


def test_order_filter_sends_matching_cards_and_one_last_update_for_cards_that_leave():
    accept = OrderFilter(StateGroup.active, Channel.phone)
    assert accept(StreamEvent("step", {"session_id": "a"}, 1))
    assert accept(_update("a", "in_conversation", "phone"))
    assert not accept(_update("b", "in_conversation", "mcp"))
    assert not accept(_update("c", "confirmed", "phone"))
    # "a" leaves the filter: sent once so the page drops it, then no more.
    assert accept(_update("a", "awaiting_confirmation", "phone"))
    assert not accept(_update("a", "awaiting_confirmation", "phone"))
