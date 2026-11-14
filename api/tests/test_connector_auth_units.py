"""Connector auth pieces that need no database (#48): passwords, the failed-login limit,
loopback redirect matching and the auth-off switch for /mcp."""

import pytest
from fastapi.testclient import TestClient
from mcp.shared.auth import InvalidRedirectUriError
from pydantic import AnyUrl

from app.main import app
from app.services.oauth import ConnectorClient
from app.services.passwords import FailedLogins, hash_password, verify_password
from app.settings import get_settings


def test_passwords_hash_with_argon2_and_verify():
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("not a hash", "anything")


def test_failed_logins_slide_over_the_window():
    limits = FailedLogins(limit=3, window=600)
    for t in (0, 1, 2):
        assert not limits.blocked("a@x.fi", now=t)
        limits.record_failure("a@x.fi", now=t)
    assert limits.blocked("a@x.fi", now=3)
    assert not limits.blocked("b@x.fi", now=3)
    assert not limits.blocked("a@x.fi", now=600.5)  # the first try aged out
    limits.clear("a@x.fi")
    assert not limits.blocked("a@x.fi", now=4)


def _client(*uris: str) -> ConnectorClient:
    return ConnectorClient(client_id="c", redirect_uris=[AnyUrl(u) for u in uris])


def test_loopback_redirects_match_on_any_port_and_nothing_else_does():
    client = _client("http://localhost/callback", "http://127.0.0.1/callback")
    for uri in ("http://localhost:3118/callback", "http://127.0.0.1:50000/callback"):
        assert str(client.validate_redirect_uri(AnyUrl(uri))) == uri
    for uri in ("http://localhost:3118/other", "https://localhost:3118/callback"):
        with pytest.raises(InvalidRedirectUriError):
            client.validate_redirect_uri(AnyUrl(uri))

    claude = _client("https://claude.ai/api/mcp/auth_callback")
    with pytest.raises(InvalidRedirectUriError):
        claude.validate_redirect_uri(AnyUrl("https://claude.ai:8443/api/mcp/auth_callback"))


@pytest.fixture
def mcp_auth_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_FAKE_CALLER", "false")
    monkeypatch.setenv("MCP_AUTH_REQUIRED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# app_db: every tool call writes its audit events (#45).
@pytest.mark.usefixtures("app_db", "mcp_auth_off")
def test_auth_off_opens_mcp_only(live_client: TestClient):
    response = live_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_customer_context", "arguments": {}},
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 200, response.text
    assert "Hassu Hauki Oy" in response.text
    # REST still needs a session.
    assert TestClient(app).get("/api/v1/me").status_code == 401


def test_auth_is_required_by_default():
    assert type(get_settings()).model_fields["mcp_auth_required"].default is True
