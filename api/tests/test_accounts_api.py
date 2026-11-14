"""Demo accounts, web sessions and caller resolution over HTTP (#44). Needs DATABASE_URL."""

import json
import random
import uuid
from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.interfaces.deps import DEV_CALLER, SESSION_COOKIE, web_session_user
from app.main import app
from app.services.accounts import SessionUser, resolve_session
from app.services.caller import Caller
from app.services.tokens import issue_caller_token
from app.settings import get_settings

pytestmark = pytest.mark.usefixtures("app_db")

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


def new_number() -> str:
    """A random Finnish mobile number, so numbers in one test never collide."""
    return f"+35840{random.randrange(10**6, 10**7)}"


def browser() -> TestClient:
    """A fresh cookie jar."""
    return TestClient(app)


def log_in(client: TestClient, phone: str, exclusions=(), lang="fi") -> dict:
    response = client.post(
        "/api/v1/demo/accounts",
        json={"phone_e164": phone, "exclusions": list(exclusions), "lang": lang},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def session_of(engine: AsyncEngine, client: TestClient) -> SessionUser:
    async with AsyncSession(engine) as db:
        session = await resolve_session(db, client.cookies[SESSION_COOKIE])
        await db.commit()
    assert session is not None
    return session


async def caller_token(engine: AsyncEngine, user_id: uuid.UUID, ttl=timedelta(minutes=15)) -> str:
    async with AsyncSession(engine) as db:
        token = await issue_caller_token(db, user_id, "phone", "S.I.MO phone", ttl)
        await db.commit()
    return token


async def test_same_number_in_two_browsers_shares_the_company_not_the_user(app_db):
    phone = new_number()
    first, second = browser(), browser()

    a = log_in(first, phone)
    b = log_in(second, phone)

    assert a["company_name"] == b["company_name"]
    one, two = await session_of(app_db, first), await session_of(app_db, second)
    assert one.company_id == two.company_id
    assert one.user_id != two.user_id


async def test_same_browser_twice_stays_the_same_user(app_db):
    client = browser()
    phone = new_number()
    log_in(client, phone)
    first = await session_of(app_db, client)

    log_in(client, phone.replace("+358", "0"))  # typed differently, same number
    again = await session_of(app_db, client)
    assert again.user_id == first.user_id
    assert again.session_id != first.session_id

    log_in(client, new_number())
    other = await session_of(app_db, client)
    assert other.user_id != first.user_id
    assert other.company_id != first.company_id


@pytest.mark.usefixtures("no_caller")
def test_new_exclusions_overwrite_the_kitchen_profile():
    phone = new_number()
    first, second = browser(), browser()

    created = log_in(first, phone, ["lactose_free", "nut_free"])
    assert created["exclusions"] == ["lactose_free", "nut_free"]
    log_in(second, phone, ["gluten_free"], lang="en")

    # Per company, last write wins, for every browser on the number.
    for client in (first, second):
        assert client.get("/api/v1/me").json()["exclusions"] == ["gluten_free"]
    assert second.get("/api/v1/me").json()["lang"] == "en"


def test_response_shape_and_masked_number():
    body = log_in(browser(), "+358401234512" if False else new_number(), [], "fi")

    # The shape the phone page reads (web/src/lib/demo/types.ts, DemoAccount).
    assert set(body) == {
        "user_id",
        "company_id",
        "company_name",
        "phone_masked",
        "exclusions",
        "usual_items",
        "new_company",
        "new_user",
    }
    assert uuid.UUID(body["user_id"]) and uuid.UUID(body["company_id"])
    assert body["new_company"] is True and body["new_user"] is True
    assert body["exclusions"] == []
    assert body["company_name"].endswith(" Oy")
    assert body["phone_masked"].startswith("+358 40 *** **")
    assert body["usual_items"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"phone_e164": "12", "exclusions": [], "lang": "fi"},
        {"phone_e164": "not a number", "exclusions": [], "lang": "fi"},
        {"phone_e164": "+358401234512", "exclusions": ["sugar_free"], "lang": "fi"},
        {"phone_e164": "+358401234512", "exclusions": [], "lang": "fi", "role": "admin"},
        {"phone_e164": "+358401234512", "exclusions": [], "lang": "sv"},
    ],
    ids=["too-short", "not-a-number", "unknown-exclusion", "extra-field", "unknown-lang"],
)
def test_bad_requests_are_422_and_set_no_cookie(body):
    client = browser()

    response = client.post("/api/v1/demo/accounts", json=body)

    assert response.status_code == 422, response.text
    assert SESSION_COOKIE not in client.cookies


def test_cookie_attributes(monkeypatch):
    response = browser().post(
        "/api/v1/demo/accounts", json={"phone_e164": new_number(), "exclusions": [], "lang": "fi"}
    )
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for part in ("HttpOnly", "Path=/", "SameSite=lax", "expires="):
        assert part in cookie
    assert "Secure" not in cookie

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()
    try:
        response = browser().post(
            "/api/v1/demo/accounts",
            json={"phone_e164": new_number(), "exclusions": [], "lang": "fi"},
        )
    finally:
        monkeypatch.delenv("ENV")
        get_settings.cache_clear()
    assert "Secure" in response.headers["set-cookie"]


# /me and log out read the browser's own session only, so the dev caller never stands in.
@pytest.mark.usefixtures("no_caller")
def test_me_without_a_session_is_401():
    assert browser().get("/api/v1/me").status_code == 401


@pytest.mark.usefixtures("dev_caller")
def test_me_falls_back_to_the_dev_caller_without_a_session():
    me = browser().get("/api/v1/me")

    assert me.status_code == 200
    # The shape the phone page reads (web/src/lib/demo/types.ts, Me).
    assert set(me.json()) == {
        "user_id",
        "company_id",
        "company_name",
        "phone_masked",
        "exclusions",
        "lang",
    }
    assert me.json()["company_name"] == DEV_CALLER.company_name


@pytest.mark.usefixtures("no_caller")
def test_log_out_revokes_the_session_and_clears_the_cookie():
    client = browser()
    created = log_in(client, new_number())
    stolen = client.cookies[SESSION_COOKIE]

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["company_name"] == created["company_name"]
    assert me.json()["phone_masked"] == created["phone_masked"]

    response = client.delete("/api/v1/session")
    assert response.status_code == 204
    assert f'{SESSION_COOKIE}=""' in response.headers["set-cookie"]
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/v1/me").status_code == 401
    # The old cookie is dead on the server too, not just dropped by the browser.
    old_cookie = TestClient(app, cookies={SESSION_COOKIE: stolen})
    assert old_cookie.get("/api/v1/me").status_code == 401
    # Logging out again is harmless.
    assert client.delete("/api/v1/session").status_code == 204


@pytest.mark.usefixtures("no_caller")
def test_the_cookie_signs_in_the_rest_tool_routes():
    alice, bob = browser(), browser()
    created = log_in(alice, new_number(), ["vegan"])
    log_in(bob, new_number())

    context = alice.get("/api/v1/customer-context").json()
    assert context["company_name"] == created["company_name"]
    assert [e["key"] for e in context["exclusions"]] == ["vegan"]

    # A quote belongs to the company that built it.
    quote = alice.post("/api/v1/quotes", json={"lines": [LINE]}).json()
    assert alice.get(f"/api/v1/quotes/{quote['quote_id']}/status").status_code == 200
    assert bob.get(f"/api/v1/quotes/{quote['quote_id']}/status").status_code == 404


def _call_tool(client: TestClient, token: str | None, name: str, arguments: dict):
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=headers,
    )


def _rpc_result(response) -> dict:
    """The JSON-RPC result, from a plain JSON or an SSE body."""
    text = response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        text = next(line[5:] for line in text.splitlines() if line.startswith("data:"))
    return json.loads(text)["result"]


@pytest.mark.usefixtures("no_caller")
async def test_mcp_tool_call_with_a_caller_token_acts_as_that_users_company(
    app_db, live_client: TestClient
):
    client = browser()
    created = log_in(client, new_number(), ["gluten_free"])
    user = await session_of(app_db, client)
    token = await caller_token(app_db, user.user_id)

    response = _call_tool(live_client, token, "get_customer_context", {})

    assert response.status_code == 200, response.text
    result = _rpc_result(response)
    assert not result["isError"], result
    context = result["structuredContent"]
    assert context["company_name"] == created["company_name"]
    assert context["phone_masked"] == created["phone_masked"]
    assert [e["key"] for e in context["exclusions"]] == ["gluten_free"]


@pytest.mark.usefixtures("no_caller")
async def test_mcp_rejects_expired_unknown_and_missing_tokens(app_db, live_client: TestClient):
    client = browser()
    log_in(client, new_number())
    user = await session_of(app_db, client)
    expired = await caller_token(app_db, user.user_id, ttl=timedelta(seconds=-1))

    for token in (expired, "not-a-token", None):
        response = _call_tool(live_client, token, "get_customer_context", {})
        assert response.status_code == 401, token
        # Points connectors at the OAuth metadata (#48); a bad token also says so.
        challenge = response.headers["www-authenticate"]
        assert challenge.startswith(
            'Bearer resource_metadata="http://localhost/.well-known/oauth-protected-resource/mcp"'
        )
        assert challenge.endswith('error="invalid_token"') == (token is not None)


@pytest.mark.usefixtures("no_caller")
async def test_a_session_cookie_does_not_sign_in_mcp(live_client: TestClient):
    client = browser()
    log_in(client, new_number())

    response = _call_tool(
        live_client.__class__(app, base_url="http://localhost", cookies=client.cookies),
        None,
        "get_customer_context",
        {},
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("no_caller")
async def test_a_bearer_token_does_not_sign_in_rest(app_db):
    client = browser()
    log_in(client, new_number())
    token = await caller_token(app_db, (await session_of(app_db, client)).user_id)
    headers = {"Authorization": f"Bearer {token}"}

    assert browser().get("/api/v1/customer-context", headers=headers).status_code == 401
    assert browser().get("/api/v1/me", headers=headers).status_code == 401


async def test_web_session_user_takes_the_cookie_and_nothing_else(app_db, dev_caller):
    # A stand-in for #46's inbox and #47's confirmation routes.
    private = FastAPI()

    @private.get("/private")
    async def private_route(caller: Annotated[Caller, Depends(web_session_user)]) -> dict:
        return {"user_id": str(caller.user_id), "channel": caller.channel}

    client = browser()
    log_in(client, new_number())
    user = await session_of(app_db, client)
    token = await caller_token(app_db, user.user_id)

    with_cookie = TestClient(private, cookies={SESSION_COOKIE: client.cookies[SESSION_COOKIE]})
    response = with_cookie.get("/private")
    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.user_id), "channel": "web"}

    bearer_only = TestClient(private).get("/private", headers={"Authorization": f"Bearer {token}"})
    assert bearer_only.status_code == 401
