"""Phone calls in the database (#52): the call's token and session, the transcript events,
and the release of the held link at every kind of ending, through `/voice/ws` with Gemini
faked and the tools on the real `/mcp`. Needs DATABASE_URL."""

import asyncio
import json
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.types import Tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.agent import PROMPT_VERSION
from app.interfaces.deps import SESSION_COOKIE
from app.interfaces.voice import relay
from app.main import app
from app.models import AuditEvent, OrderSession
from app.schemas import BuildQuoteRequest, RequestConfirmationRequest
from app.services import accounts, quotes, tokens, voice_calls
from tests import voice_fakes as fx
from tests.phones import new_number

pytestmark = pytest.mark.usefixtures("app_db", "no_caller")

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


def browser(lang: str = "fi") -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/demo/accounts",
        json={
            "phone_e164": new_number(),
            "exclusions": [],
            "lang": lang,
        },
    )
    assert response.status_code == 201, response.text
    return client


async def user_id_of(engine: AsyncEngine, client: TestClient) -> uuid.UUID:
    async with AsyncSession(engine) as db:
        session = await accounts.resolve_session(db, client.cookies[SESSION_COOKIE])
        await db.commit()
    assert session is not None
    return session.user_id


async def events(engine: AsyncEngine, session_id: uuid.UUID) -> list[AuditEvent]:
    async with AsyncSession(engine) as db:
        return list(
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.session_id == session_id)
                .order_by(AuditEvent.seq)
            )
        )


# --- The service ------------------------------------------------------------------------


async def test_start_call_makes_a_phone_token_and_session(app_db):
    client = browser()
    user_id = await user_id_of(app_db, client)
    async with AsyncSession(app_db) as db:
        start = await voice_calls.start_call(db, user_id, prompt_version=PROMPT_VERSION)
        await db.commit()
    assert start is not None
    assert start.caller.channel == "phone" and start.caller.client_name == "S.I.MO phone"
    assert start.context.company_name == start.caller.company_name

    async with AsyncSession(app_db) as db:
        token = await tokens.resolve_access_token(db, start.token)
        session = await db.get_one(OrderSession, start.session_id)
    assert token is not None and token.channel == "phone" and token.client_name == "S.I.MO phone"
    assert session.channel == "phone" and session.call_id == start.call_id
    assert session.prompt_version == PROMPT_VERSION
    types = [e.type for e in await events(app_db, start.session_id)]
    assert types == ["session_started", "customer_identified"]


async def test_start_call_without_an_account_is_none(app_db):
    async with AsyncSession(app_db) as db:
        assert await voice_calls.start_call(db, uuid.uuid4(), prompt_version="x") is None


async def test_end_call_releases_once_and_ends_the_session(app_db):
    client = browser()
    user_id = await user_id_of(app_db, client)
    async with AsyncSession(app_db) as db:
        start = await voice_calls.start_call(db, user_id, prompt_version=PROMPT_VERSION)
        built = await quotes.build_quote(db, start.caller, BuildQuoteRequest(lines=[LINE]))
        await quotes.request_confirmation(
            db, start.caller, RequestConfirmationRequest(quote_id=built.quote_id)
        )
        await db.commit()
    assert client.get("/api/v1/private/inbox").json() == []

    async with AsyncSession(app_db) as db:
        end = await voice_calls.end_call(
            db, user_id, start.session_id, ended_by="visitor", duration_s=95
        )
        await db.commit()
    assert end.released_quote_ids == [built.quote_id]
    assert end.quote_id == built.quote_id and end.total_cents == built.total_cents
    [message] = client.get("/api/v1/private/inbox").json()
    assert message["link"].startswith("http")

    async with AsyncSession(app_db) as db:
        again = await voice_calls.end_call(
            db, user_id, start.session_id, ended_by="dropped", duration_s=99
        )
        await db.commit()
        session = await db.get_one(OrderSession, start.session_id)
    assert again.released_quote_ids == [] and again.quote_id is None
    assert session.ended_by == "visitor" and session.ended_at is not None

    recorded = await events(app_db, start.session_id)
    ended = [e for e in recorded if e.type == "session_ended"]
    assert len(ended) == 1
    assert ended[0].payload["ended_by"] == "visitor" and ended[0].payload["duration_s"] == 95
    assert ended[0].text_en == "Call ended (the caller hung up), 1:35 long"
    assert [e.type for e in recorded].count("inbox_delivered") == 1


# --- A request_confirmation that finishes after the hang-up (#88) ------------------------


async def quote_in_a_call(
    engine: AsyncEngine, client: TestClient
) -> tuple[uuid.UUID, voice_calls.CallStart, str]:
    """A started call with a ready quote: (user id, the call, the quote id)."""
    user_id = await user_id_of(engine, client)
    async with AsyncSession(engine) as db:
        start = await voice_calls.start_call(db, user_id, prompt_version=PROMPT_VERSION)
        assert start is not None
        built = await quotes.build_quote(db, start.caller, BuildQuoteRequest(lines=[LINE]))
        await db.commit()
    return user_id, start, built.quote_id


async def end(engine: AsyncEngine, user_id: uuid.UUID, start: voice_calls.CallStart):
    async with AsyncSession(engine) as db:
        ended = await voice_calls.end_call(
            db, user_id, start.session_id, ended_by="visitor", duration_s=60
        )
        await db.commit()
    return ended


async def test_a_confirmation_after_the_call_ended_is_delivered_at_once(app_db):
    client = browser()
    user_id, start, quote_id = await quote_in_a_call(app_db, client)
    assert (await end(app_db, user_id, start)).released_quote_ids == []

    async with AsyncSession(app_db) as db:
        sent = await quotes.request_confirmation(
            db, start.caller, RequestConfirmationRequest(quote_id=quote_id)
        )
        await db.commit()
    assert sent.delivery_status == "off"
    [message] = client.get("/api/v1/private/inbox").json()
    assert message["link"].startswith("http")
    delivered = [e for e in await events(app_db, start.session_id) if e.type == "inbox_delivered"]
    assert [e.payload["quote_id"] for e in delivered] == [quote_id]


async def test_the_end_of_a_call_waits_for_a_running_confirmation(app_db):
    """The confirmation holds the call's session; the end of the call waits for its commit
    and then releases its held link."""
    client = browser()
    user_id, start, quote_id = await quote_in_a_call(app_db, client)

    async with AsyncSession(app_db) as db:
        sent = await quotes.request_confirmation(
            db, start.caller, RequestConfirmationRequest(quote_id=quote_id)
        )
        assert sent.delivery_status == "held"
        ending = asyncio.create_task(end(app_db, user_id, start))
        await asyncio.sleep(0.5)
        assert not ending.done()  # waiting for the session lock
        await db.commit()
    ended = await asyncio.wait_for(ending, 10)

    assert ended.released_quote_ids == [quote_id]
    assert len(client.get("/api/v1/private/inbox").json()) == 1


async def test_a_confirmation_waiting_on_the_end_of_the_call_is_delivered_at_once(app_db):
    """The end of the call holds the session; the confirmation waits for it, then finds the
    call ended and delivers the link itself."""
    client = browser()
    user_id, start, quote_id = await quote_in_a_call(app_db, client)

    async with AsyncSession(app_db) as db:
        ended = await voice_calls.end_call(
            db, user_id, start.session_id, ended_by="visitor", duration_s=60
        )
        assert ended.released_quote_ids == []

        async def confirm() -> str:
            async with AsyncSession(app_db) as other:
                sent = await quotes.request_confirmation(
                    other, start.caller, RequestConfirmationRequest(quote_id=quote_id)
                )
                await other.commit()
            return sent.delivery_status

        confirming = asyncio.create_task(confirm())
        await asyncio.sleep(0.5)
        assert not confirming.done()  # waiting for the session lock
        await db.commit()
    assert await asyncio.wait_for(confirming, 10) == "off"
    assert len(client.get("/api/v1/private/inbox").json()) == 1


async def test_a_confirmation_in_another_open_call_stays_held(app_db):
    """A quote from an earlier session, sent during a call, still waits for that call."""
    client = browser()
    user_id, first, quote_id = await quote_in_a_call(app_db, client)
    await end(app_db, user_id, first)
    async with AsyncSession(app_db) as db:
        second = await voice_calls.start_call(db, user_id, prompt_version=PROMPT_VERSION)
        await db.commit()
    assert second is not None

    async with AsyncSession(app_db) as db:
        sent = await quotes.request_confirmation(
            db, second.caller, RequestConfirmationRequest(quote_id=quote_id)
        )
        await db.commit()
    assert sent.delivery_status == "held"
    assert client.get("/api/v1/private/inbox").json() == []
    assert (await end(app_db, user_id, second)).released_quote_ids == [quote_id]
    assert len(client.get("/api/v1/private/inbox").json()) == 1


async def test_transcripts_are_public_events_with_masked_numbers(app_db):
    client = browser()
    user_id = await user_id_of(app_db, client)
    async with AsyncSession(app_db) as db:
        start = await voice_calls.start_call(db, user_id, prompt_version=PROMPT_VERSION)
        await voice_calls.record_said(
            db, start.session_id, "buyer", "Soita numeroon +358 40 123 4567", lang="fi"
        )
        await voice_calls.record_said(db, start.session_id, "agent", "Selvä.")
        await db.commit()
    said = [e for e in await events(app_db, start.session_id) if e.type.endswith("_said")]
    assert [(e.type, e.actor) for e in said] == [("buyer_said", "buyer"), ("agent_said", "agent")]
    assert "123 4567" not in said[0].payload["text"]
    assert said[0].payload["transcript"] is True and said[0].payload["lang"] == "fi"


async def test_custom_vocabulary_comes_from_the_catalogue(app_db, monkeypatch):
    monkeypatch.setattr(voice_calls, "_vocabulary", None)
    async with AsyncSession(app_db) as db:
        terms = await voice_calls.custom_vocabulary(db)
    assert terms[: len(voice_calls.BASE_VOCABULARY)] == list(voice_calls.BASE_VOCABULARY)
    assert len(terms) <= voice_calls.MAX_VOCABULARY
    assert len({t.lower() for t in terms}) == len(terms)
    assert any(len(t) >= 9 and t.islower() for t in terms[len(voice_calls.BASE_VOCABULARY) :])


# --- A whole call through /voice/ws -----------------------------------------------------


class RpcTools:
    """The relay's tools on the real `/mcp`, over HTTP with the call's bearer token."""

    def __init__(self, live_client: TestClient) -> None:
        self.client = live_client
        self.token: str | None = None

    def open(self, token: str):
        self.token = token
        tools = self

        class Session:
            async def __aenter__(self):
                return tools

            async def __aexit__(self, *exc):
                return None

        return Session()

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self.token}",
            },
        )
        assert response.status_code == 200, response.text
        text = response.text
        if response.headers["content-type"].startswith("text/event-stream"):
            text = next(line[5:] for line in text.splitlines() if line.startswith("data:"))
        return json.loads(text)["result"]

    async def list_tools(self) -> list[Tool]:
        result = await asyncio.to_thread(self._rpc, "tools/list", {})
        return [Tool.model_validate(t) for t in result["tools"]]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await asyncio.to_thread(
            self._rpc, "tools/call", {"name": name, "arguments": arguments}
        )
        if result.get("isError"):
            return {"error": result["content"][0]["text"]}
        return {"output": result["structuredContent"]}


@pytest.mark.parametrize("ending", ["hangup", "drop", "time_limit"])
async def test_a_call_releases_the_link_at_every_ending(app_db, live_client, monkeypatch, ending):
    live = fx.FakeLive()
    tools = RpcTools(live_client)
    monkeypatch.setattr(relay, "connect_gemini", live.connect)
    monkeypatch.setattr(relay, "open_tools", tools.open)
    limit = 60.0 if ending != "time_limit" else 3.0
    monkeypatch.setattr(
        relay, "call_limits", lambda: relay.Limits(max_call_s=limit, warn_before_s=1)
    )

    client = browser()
    user_id = await user_id_of(app_db, client)
    texts: list[str] = []

    def run_call() -> dict[str, Any] | None:
        with client.websocket_connect("/voice/ws") as ws:

            def next_json(type_: str) -> dict[str, Any]:
                while True:
                    message = ws.receive()
                    assert message["type"] != "websocket.close", message
                    if message.get("text") is not None:
                        texts.append(message["text"])
                        data = json.loads(message["text"])
                        if data["type"] == type_:
                            return data

            next_json("ready")
            live.push(fx.heard("Kaksikymmentä litraa maitoa maanantaiksi, siinä kaikki."))
            live.push(fx.tool_call("build_quote", {"lines": [LINE]}, "b1"))
            live.wait_for(lambda: len(live.tool_responses) == 1, timeout=20)
            quote = live.tool_responses[0].response["output"]
            live.push(fx.tool_call("request_confirmation", {"quote_id": quote["quote_id"]}, "r0"))
            live.wait_for(lambda: len(live.tool_responses) == 2, timeout=10)
            live.push(fx.heard("Kyllä, lähetä."))
            live.push(fx.tool_call("request_confirmation", {"quote_id": quote["quote_id"]}, "r1"))
            live.wait_for(lambda: len(live.tool_responses) == 3, timeout=10)
            if ending == "drop":
                # The browser goes away without a word. (Leaving the `with` would also cancel
                # the handler, which a real server doesn't do.)
                ws.close(1006)
                for _ in range(200):
                    if client.get("/api/v1/private/inbox").json():
                        break
                    time.sleep(0.05)
                return None
            if ending == "hangup":
                ws.send_text(json.dumps({"type": "hangup"}))
            return next_json("ended")

    ended = await asyncio.to_thread(run_call)

    refused, sent = live.tool_responses[1].response, live.tool_responses[2].response
    assert "error" in refused
    assert sent["output"]["delivery_status"] == "held"
    if ended is not None:
        assert ended["ended_by"] == {"hangup": "visitor", "time_limit": "time_limit"}[ending]
        assert ended["inbox"] is True and ended["delivery_status"] == "off"
        assert ended["total_cents"] == live.tool_responses[0].response["output"]["total_cents"]
    assert all("/c/" not in t for t in texts)

    async def inbox() -> list[dict[str, Any]]:
        for _ in range(100):
            messages = client.get("/api/v1/private/inbox").json()
            if messages:
                return messages
            await asyncio.sleep(0.05)
        return []

    [message] = await inbox()
    assert "/c/" in message["link"]

    async with AsyncSession(app_db) as db:
        session = await db.scalar(
            select(OrderSession).where(
                OrderSession.user_id == user_id, OrderSession.channel == "phone"
            )
        )
    assert session is not None
    expected = {"hangup": "visitor", "drop": "dropped", "time_limit": "time_limit"}[ending]
    for _ in range(100):
        async with AsyncSession(app_db) as db:
            session = await db.get_one(OrderSession, session.id)
        if session.ended_by:
            break
        await asyncio.sleep(0.05)
    assert session.ended_by == expected
    types = [e.type for e in await events(app_db, session.id)]
    for wanted in ("session_started", "customer_identified", "buyer_said", "tool_called"):
        assert wanted in types
    assert types[-1] == "session_ended"
    # The caller's line is logged before the tool call it led to.
    assert types.index("buyer_said") < types.index("tool_called")
    # The refused request is on the record too, answered by the relay.
    returned = [e for e in await events(app_db, session.id) if e.type == "tool_returned"]
    assert any(e.payload.get("answered_by") == "relay" for e in returned)
