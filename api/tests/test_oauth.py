"""The connector OAuth flow for /mcp end to end over HTTP (#48). Needs DATABASE_URL.

Plays both sides: the connector (register, authorize with PKCE, token, refresh, /mcp) and
the browser (log in through the login form's POST, then Allow on the consent step).
"""

import base64
import hashlib
import json
import random
import secrets
import uuid
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.deps import SESSION_COOKIE, web_session_user
from app.main import app
from app.services.accounts import create_unclaimed_account
from app.services.caller import Caller
from app.settings import get_settings

pytestmark = pytest.mark.usefixtures("app_db", "no_caller")

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
PASSWORD = "correct horse battery"
# PUBLIC_BASE_URL, which the metadata routes read once when the app is built.
ORIGIN = get_settings().public_base_url


def new_number() -> str:
    return f"+35840{random.randrange(10**6, 10**7)}"


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def register(client: TestClient, **extra) -> dict:
    body = {
        "redirect_uris": [CLAUDE_CALLBACK],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": "Claude",
        **extra,
    }
    response = client.post("/oauth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def authorize(client: TestClient, client_id: str, challenge: str, redirect_uri=CLAUDE_CALLBACK):
    """The connector sends the browser to /oauth/authorize; returns the consent request id."""
    response = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st4te",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{ORIGIN}/connect"
    return parse_qs(location.query)["request"][0]


def signed_up_browser() -> tuple[TestClient, str]:
    email = f"chef.{uuid.uuid4().hex[:10]}@example.com"
    TestClient(app).post(
        "/api/v1/signup", json={"email": email, "password": PASSWORD, "phone_e164": new_number()}
    )
    return TestClient(app), email


def allow(browser: TestClient, request_id: str, decision: bool = True) -> dict[str, str]:
    """The consent step; returns the query of the redirect back to the connector."""
    response = browser.post(f"/api/v1/oauth/requests/{request_id}", json={"allow": decision})
    assert response.status_code == 200, response.text
    target = urlsplit(response.json()["redirect_to"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == CLAUDE_CALLBACK
    return {k: v[0] for k, v in parse_qs(target.query).items()}


def token(client: TestClient, **form) -> TestClient:
    return client.post("/oauth/token", data=form)


def code_for(connector: TestClient, client_id: str, challenge: str) -> str:
    browser, email = signed_up_browser()
    browser.post("/api/v1/session", json={"email": email, "password": PASSWORD})
    return allow(browser, authorize(connector, client_id, challenge))["code"]


def call_tool(client: TestClient, access_token: str):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_customer_context", "arguments": {}},
        },
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {access_token}",
        },
    )


def rpc_result(response) -> dict:
    text = response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        text = next(line[5:] for line in text.splitlines() if line.startswith("data:"))
    return json.loads(text)["result"]


def test_metadata_points_from_mcp_to_the_authorization_server():
    client = TestClient(app, base_url="http://localhost")
    challenge = client.post("/mcp", json={}).headers["www-authenticate"]
    url = challenge.split('resource_metadata="')[1].split('"')[0]
    assert url == f"{ORIGIN}/.well-known/oauth-protected-resource/mcp"

    resource = client.get(urlsplit(url).path).json()
    assert resource["resource"] == f"{ORIGIN}/mcp"
    assert client.get("/.well-known/oauth-protected-resource").json() == resource

    issuer = resource["authorization_servers"][0]
    server = client.get("/.well-known/oauth-authorization-server").json()
    assert server["issuer"] == issuer
    assert server["authorization_endpoint"] == f"{ORIGIN}/oauth/authorize"
    assert server["token_endpoint"] == f"{ORIGIN}/oauth/token"
    assert server["registration_endpoint"] == f"{ORIGIN}/oauth/register"
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert "none" in server["token_endpoint_auth_methods_supported"]


def test_full_flow_with_pkce_login_tool_call_and_refresh(live_client: TestClient):
    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector)["client_id"]
    verifier, challenge = pkce()
    request_id = authorize(connector, client_id, challenge)

    # The browser has no session: the consent page gets 401 and goes to /login?next=...
    browser, email = signed_up_browser()
    assert browser.get(f"/api/v1/oauth/requests/{request_id}").status_code == 401
    # The login form's POST, then back to the consent step.
    assert (
        browser.post("/api/v1/session", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    view = browser.get(f"/api/v1/oauth/requests/{request_id}").json()
    assert view["client_name"] == "Claude"
    assert view["company_name"].endswith("Oy")
    assert view["redirect_host"] == "claude.ai"
    me = browser.get("/api/v1/me").json()
    assert view["company_name"] == me["company_name"]

    back = allow(browser, request_id)
    assert back["state"] == "st4te"
    code = back["code"]
    # The request is used up.
    assert browser.get(f"/api/v1/oauth/requests/{request_id}").status_code == 404

    # A wrong verifier fails and doesn't use the code up.
    wrong = token(
        connector,
        grant_type="authorization_code",
        code=code,
        redirect_uri=CLAUDE_CALLBACK,
        client_id=client_id,
        code_verifier=pkce()[0],
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_grant"

    exchange = dict(
        grant_type="authorization_code",
        code=code,
        redirect_uri=CLAUDE_CALLBACK,
        client_id=client_id,
        code_verifier=verifier,
    )
    issued = token(connector, **exchange)
    assert issued.status_code == 200, issued.text
    tokens = issued.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] == 3600
    assert tokens["refresh_token"]

    # Reusing the code fails.
    reuse = token(connector, **exchange)
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"

    # The token works on /mcp, as the account's company.
    response = call_tool(live_client, tokens["access_token"])
    assert response.status_code == 200, response.text
    result = rpc_result(response)
    assert not result["isError"], result
    assert result["structuredContent"]["company_name"] == me["company_name"]

    # Refresh rotates: a new pair, and the old refresh token is spent.
    refresh = dict(
        grant_type="refresh_token", refresh_token=tokens["refresh_token"], client_id=client_id
    )
    rotated = token(connector, **refresh)
    assert rotated.status_code == 200, rotated.text
    fresh = rotated.json()
    assert fresh["access_token"] != tokens["access_token"]
    assert fresh["refresh_token"] != tokens["refresh_token"]
    assert call_tool(live_client, fresh["access_token"]).status_code == 200
    spent = token(connector, **refresh)
    assert spent.status_code == 400
    assert spent.json()["error"] == "invalid_grant"


def test_cancel_sends_access_denied():
    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector)["client_id"]
    request_id = authorize(connector, client_id, pkce()[1])
    browser, email = signed_up_browser()
    browser.post("/api/v1/session", json={"email": email, "password": PASSWORD})

    back = allow(browser, request_id, decision=False)

    assert back["error"] == "access_denied"
    assert back["state"] == "st4te"
    assert "code" not in back


async def test_handout_account_consent_needs_the_phone_first(app_db):
    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector)["client_id"]
    request_id = authorize(connector, client_id, pkce()[1])
    email = f"judge{uuid.uuid4().hex[:6]}@simo.mankeli.co"
    async with AsyncSession(app_db) as db:
        await create_unclaimed_account(db, email, PASSWORD)
        await db.commit()
    browser = TestClient(app)
    browser.post("/api/v1/session", json={"email": email, "password": PASSWORD})

    assert browser.get(f"/api/v1/oauth/requests/{request_id}").status_code == 409
    assert browser.post(f"/api/v1/oauth/requests/{request_id}", json={"allow": True}).json() == {
        "detail": "phone_required"
    }

    browser.post("/api/v1/me/phone", json={"phone_e164": new_number()})
    assert "code" in allow(browser, request_id)


def test_unknown_redirect_uri_and_unknown_request_are_refused():
    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector)["client_id"]
    response = connector.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://evil.example/callback",
            "code_challenge": pkce()[1],
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400

    browser, email = signed_up_browser()
    browser.post("/api/v1/session", json={"email": email, "password": PASSWORD})
    assert browser.get("/api/v1/oauth/requests/nope").status_code == 404
    assert browser.post("/api/v1/oauth/requests/nope", json={"allow": True}).status_code == 404


def test_registration_refuses_plain_http_redirects():
    response = TestClient(app).post(
        "/oauth/register",
        json={"redirect_uris": ["http://example.com/cb"], "token_endpoint_auth_method": "none"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_loopback_redirect_matches_on_any_port():
    # Claude Code registers http://localhost/callback and uses an ephemeral port.
    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector, redirect_uris=["http://localhost/callback"])["client_id"]
    challenge = pkce()[1]
    authorize(connector, client_id, challenge, redirect_uri="http://localhost:3118/callback")

    response = connector.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://localhost:3118/other",
            "code_challenge": challenge,
        },
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_a_confidential_client_must_send_its_secret():
    connector = TestClient(app, base_url="http://localhost")
    registered = register(connector, token_endpoint_auth_method="client_secret_post")
    client_id, secret = registered["client_id"], registered["client_secret"]
    verifier, challenge = pkce()
    code = code_for(connector, client_id, challenge)
    exchange = dict(
        grant_type="authorization_code",
        code=code,
        redirect_uri=CLAUDE_CALLBACK,
        client_id=client_id,
        code_verifier=verifier,
    )

    assert token(connector, **exchange, client_secret="wrong").status_code == 401
    assert token(connector, **exchange).status_code == 401
    assert token(connector, **exchange, client_secret=secret).status_code == 200


def test_a_connector_token_is_refused_by_cookie_only_endpoints():
    # A stand-in for #46's inbox and #47's confirmation routes (web_session_user).
    private = FastAPI()

    @private.get("/private")
    async def private_route(caller: Annotated[Caller, Depends(web_session_user)]) -> dict:
        return {"user_id": str(caller.user_id)}

    connector = TestClient(app, base_url="http://localhost")
    client_id = register(connector)["client_id"]
    verifier, challenge = pkce()
    code = code_for(connector, client_id, challenge)
    access = token(
        connector,
        grant_type="authorization_code",
        code=code,
        redirect_uri=CLAUDE_CALLBACK,
        client_id=client_id,
        code_verifier=verifier,
    ).json()["access_token"]

    bearer = {"Authorization": f"Bearer {access}"}
    assert TestClient(private).get("/private", headers=bearer).status_code == 401
    # Nor on the REST twins or the consent step, which read only the cookie.
    assert connector.get("/api/v1/me", headers=bearer).status_code == 401
    assert SESSION_COOKIE not in connector.cookies
