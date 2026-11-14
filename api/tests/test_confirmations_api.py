"""The confirmation request and the inbox over HTTP: REST, MCP and the inbox routes (#46).

Needs DATABASE_URL.
"""

import json
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.interfaces.deps import SESSION_COOKIE
from app.main import app
from app.services import confirmations, voice_calls
from app.services.accounts import resolve_session
from app.services.tokens import issue_caller_token

pytestmark = pytest.mark.usefixtures("app_db")

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


def new_number() -> str:
    return f"+35840{random.randrange(10**6, 10**7)}"


def browser(phone: str, lang: str = "en") -> TestClient:
    """A fresh browser signed in with `phone`."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": lang}
    )
    assert response.status_code == 201, response.text
    return client


def build(client: TestClient) -> dict:
    response = client.post("/api/v1/quotes", json={"lines": [LINE]})
    assert response.status_code == 200, response.text
    return response.json()


async def user_id_of(engine: AsyncEngine, client: TestClient):
    async with AsyncSession(engine) as db:
        session = await resolve_session(db, client.cookies[SESSION_COOKIE])
        await db.commit()
    assert session is not None
    return session.user_id


@pytest.mark.usefixtures("no_caller")
def test_rest_twin_sends_to_this_browsers_inbox_only():
    phone = new_number()
    client = browser(phone)
    same_number = browser(phone)
    quote = build(client)
    url = f"/api/v1/quotes/{quote['quote_id']}/confirmation-request"

    response = client.post(url)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "sent_to_masked": f"+358 40 *** **{phone[-2:]}",
        "delivery_status": "off",
        "inbox": True,
    }
    assert "/c/" not in response.text
    status = client.get(f"/api/v1/quotes/{quote['quote_id']}/status").json()
    assert status["status"] == "pending_confirmation"
    assert client.post(url).status_code == 409

    inbox = client.get("/api/v1/private/inbox")
    assert inbox.status_code == 200
    assert inbox.headers["cache-control"] == "no-store"
    [message] = inbox.json()
    assert set(message) == {"id", "at", "text", "link"}
    assert message["text"].startswith("S.I.MO: confirm your order, ")
    assert message["link"].startswith("http://localhost:5173/c/")
    assert same_number.get("/api/v1/private/inbox").json() == []


@pytest.mark.usefixtures("dev_caller")
def test_the_dev_callers_link_goes_to_its_own_account_and_no_browser_can_read_it():
    # Since #45 the dev caller has database rows, so its link lands in the dev account's
    # inbox. That inbox is cookie only, so without a session nobody can read it.
    client = TestClient(app)
    quote = build(client)

    response = client.post(f"/api/v1/quotes/{quote['quote_id']}/confirmation-request")

    assert response.status_code == 200, response.text
    assert "link" not in response.text and "/c/" not in response.text
    status = client.get(f"/api/v1/quotes/{quote['quote_id']}/status").json()
    assert status["status"] == "pending_confirmation"
    assert client.get("/api/v1/private/inbox").status_code == 401
    assert client.get("/api/v1/private/inbox/stream").status_code == 401


@pytest.mark.usefixtures("dev_caller")
async def test_the_inbox_takes_the_cookie_and_nothing_else(app_db):
    client = browser(new_number())
    async with AsyncSession(app_db) as db:
        token = await issue_caller_token(
            db, await user_id_of(app_db, client), "phone", "S.I.MO phone"
        )
        await db.commit()

    bearer = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert bearer.get("/api/v1/private/inbox").status_code == 401
    assert bearer.get("/api/v1/private/inbox/stream").status_code == 401
    assert client.get("/api/v1/private/inbox").status_code == 200


def _call_tool(client: TestClient, token: str, name: str, arguments: dict):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    )


def _rpc_result(response) -> dict:
    text = response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        text = next(line[5:] for line in text.splitlines() if line.startswith("data:"))
    return json.loads(text)["result"]


@pytest.mark.usefixtures("no_caller")
async def test_mcp_on_a_phone_call_holds_the_message_until_released(
    app_db, live_client: TestClient
):
    client = browser(new_number(), lang="fi")
    user_id = await user_id_of(app_db, client)
    async with AsyncSession(app_db) as db:
        start = await voice_calls.start_call(db, user_id, prompt_version="test")
        await db.commit()
    assert start is not None
    token = start.token

    built = _rpc_result(_call_tool(live_client, token, "build_quote", {"lines": [LINE]}))
    quote_id = built["structuredContent"]["quote_id"]
    response = _call_tool(live_client, token, "request_confirmation", {"quote_id": quote_id})

    assert response.status_code == 200, response.text
    result = _rpc_result(response)
    assert not result["isError"], result
    assert result["structuredContent"]["delivery_status"] == "held"
    assert result["structuredContent"]["inbox"] is True
    assert "/c/" not in response.text
    assert client.get("/api/v1/private/inbox").json() == []

    # The relay (#52) does this when the call ends.
    async with AsyncSession(app_db) as db:
        assert await confirmations.release_held_messages(db, user_id) == [quote_id]
        await db.commit()

    [message] = client.get("/api/v1/private/inbox").json()
    assert message["text"].startswith("S.I.MO: vahvista tilauksesi, ")


@pytest.mark.usefixtures("no_caller")
def test_the_stream_starts_with_this_users_snapshot():
    client = browser(new_number())
    quote = build(client)
    client.post(f"/api/v1/quotes/{quote['quote_id']}/confirmation-request")
    [message] = client.get("/api/v1/private/inbox").json()

    with client.stream("GET", "/api/v1/private/inbox/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = []
        for line in response.iter_lines():
            if not line:
                break
            lines.append(line)

    assert lines[0] == "event: snapshot"
    assert json.loads(lines[1].removeprefix("data: ")) == [message]
