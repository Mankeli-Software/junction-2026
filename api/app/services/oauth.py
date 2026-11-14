"""The OAuth authorization server behind `/mcp`, on Postgres (#48, `technical-plan.md` §7.3).

The MCP SDK's handlers (`mcp.server.auth`) parse and check the HTTP side: registration,
authorize, PKCE, redirect URIs, expiry. These functions store and look up what they need.
`app.interfaces.auth.provider` adapts them to the SDK's provider interface.

- Clients register themselves (RFC 7591). A secret, if the client asks for one, is kept
  only as its SHA-256.
- Authorize stores the request and sends the browser to the consent page
  (`/connect?request=<id>`), which logs in first if needed. Allow turns the request into a
  code, valid for 5 minutes and usable once.
- A code or a refresh token buys an access token (1 hour, in `access_tokens` with
  channel `connector`, so `/mcp`'s existing check takes it) and a refresh token
  (30 days). A refresh token works once: using it issues a new one.

Like the other services, the functions take an `AsyncSession` and only flush.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OAuthClient, OAuthCode, OAuthRefreshToken, OAuthRequest, User

from .tokens import hash_token, issue_caller_token, new_token

REQUEST_TTL = timedelta(minutes=15)  # time to log in or sign up and press Allow
CODE_TTL = timedelta(minutes=5)
ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)

# The name on the dashboard card and the consent page when the client gives none.
DEFAULT_CLIENT_NAME = "Connector"
MAX_CLIENT_NAME = 60

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]", "::1"})


class ConnectorClient(OAuthClientInformationFull):
    """A registered client as the SDK sees it.

    `client_secret` holds the secret's hash here; `app.interfaces.auth.provider` checks
    the secret a request presents against it. Loopback redirect URIs match on any port,
    as RFC 8252 §7.3 asks and Claude Code needs.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None and _is_loopback(str(redirect_uri)):
            for registered in self.redirect_uris or []:
                if _without_port(str(registered)) == _without_port(str(redirect_uri)):
                    return redirect_uri
        return super().validate_redirect_uri(redirect_uri)


class ConnectorCode(AuthorizationCode):
    user_id: uuid.UUID


class ConnectorRefreshToken(RefreshToken):
    user_id: uuid.UUID


def _is_loopback(uri: str) -> bool:
    parts = urlsplit(uri)
    return parts.scheme == "http" and (parts.hostname or "") in LOOPBACK_HOSTS


def _without_port(uri: str) -> tuple[str, str, str, str]:
    parts = urlsplit(uri)
    return (parts.scheme, parts.hostname or "", parts.path or "/", parts.query)


def _client_name(name: str | None) -> str:
    name = " ".join((name or "").split())
    return name[:MAX_CLIENT_NAME] or DEFAULT_CLIENT_NAME


def redirect_host(uri: str) -> str:
    return urlsplit(uri).netloc


async def register_client(db: AsyncSession, info: OAuthClientInformationFull) -> None:
    """Store a new client. Redirect URIs must be https, or http on a loopback address."""
    assert info.client_id is not None
    for uri in info.redirect_uris or []:
        if urlsplit(str(uri)).scheme != "https" and not _is_loopback(str(uri)):
            raise RegistrationError(
                "invalid_redirect_uri", "Redirect URIs must use https, or http on localhost"
            )
    db.add(
        OAuthClient(
            client_id=info.client_id,
            client_secret_hash=hash_token(info.client_secret) if info.client_secret else None,
            client_name=info.client_name,
            redirect_uris=[str(u) for u in info.redirect_uris or []],
            registration=info.model_dump(mode="json", exclude={"client_secret"}),
        )
    )
    await db.flush()


async def get_client(db: AsyncSession, client_id: str) -> ConnectorClient | None:
    row = await db.get(OAuthClient, client_id)
    if row is None:
        return None
    return ConnectorClient.model_validate(
        {**row.registration, "client_id": row.client_id, "client_secret": row.client_secret_hash}
    )


async def create_request(
    db: AsyncSession,
    client: OAuthClientInformationFull,
    params: AuthorizationParams,
    *,
    now: datetime | None = None,
) -> str:
    """Store an authorize request until the browser decides; returns its random id."""
    now = now or datetime.now(UTC)
    assert client.client_id is not None
    request_id = secrets.token_urlsafe(24)
    db.add(
        OAuthRequest(
            id=request_id,
            client_id=client.client_id,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            scopes=params.scopes or [],
            state=params.state,
            resource=params.resource,
            expires_at=now + REQUEST_TTL,
        )
    )
    await db.flush()
    return request_id


async def pending_request(
    db: AsyncSession, request_id: str, *, now: datetime | None = None
) -> tuple[OAuthRequest, str] | None:
    """A live authorize request and its client's display name, or None."""
    now = now or datetime.now(UTC)
    row = (
        await db.execute(
            select(OAuthRequest, OAuthClient.client_name)
            .join(OAuthClient, OAuthClient.client_id == OAuthRequest.client_id)
            .where(OAuthRequest.id == request_id, OAuthRequest.expires_at > now)
        )
    ).one_or_none()
    if row is None:
        return None
    request, name = row
    return request, _client_name(name)


async def decide(
    db: AsyncSession,
    request_id: str,
    user_id: uuid.UUID,
    allow: bool,
    *,
    now: datetime | None = None,
) -> str | None:
    """Allow or Cancel a pending request. Returns the client redirect, or None if the
    request is gone. Allow issues a code for `user_id`; either way the request is used up."""
    now = now or datetime.now(UTC)
    request = await db.scalar(
        delete(OAuthRequest)
        .where(OAuthRequest.id == request_id, OAuthRequest.expires_at > now)
        .returning(OAuthRequest)
    )
    if request is None:
        return None
    if not allow:
        return construct_redirect_uri(
            request.redirect_uri,
            error="access_denied",
            error_description="The user cancelled",
            state=request.state,
        )
    code = new_token()
    db.add(
        OAuthCode(
            code_hash=hash_token(code),
            client_id=request.client_id,
            user_id=user_id,
            redirect_uri=request.redirect_uri,
            redirect_uri_provided_explicitly=request.redirect_uri_provided_explicitly,
            code_challenge=request.code_challenge,
            scopes=request.scopes,
            resource=request.resource,
            expires_at=now + CODE_TTL,
        )
    )
    await db.flush()
    return construct_redirect_uri(request.redirect_uri, code=code, state=request.state)


async def load_code(db: AsyncSession, client_id: str, code: str) -> ConnectorCode | None:
    """An unused code of this client. The SDK checks expiry, redirect URI and PKCE."""
    row = await db.get(OAuthCode, hash_token(code))
    if row is None or row.client_id != client_id or row.used_at is not None:
        return None
    return ConnectorCode(
        code=code,
        scopes=row.scopes,
        expires_at=row.expires_at.timestamp(),
        client_id=row.client_id,
        code_challenge=row.code_challenge,
        redirect_uri=AnyUrl(row.redirect_uri),
        redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
        resource=row.resource,
        subject=str(row.user_id),
        user_id=row.user_id,
    )


async def redeem_code(
    db: AsyncSession,
    client: OAuthClientInformationFull,
    code: ConnectorCode,
    *,
    now: datetime | None = None,
) -> OAuthToken:
    """Use the code up (atomically, so two exchanges can't both win) and issue tokens."""
    now = now or datetime.now(UTC)
    used = await db.scalar(
        update(OAuthCode)
        .where(OAuthCode.code_hash == hash_token(code.code), OAuthCode.used_at.is_(None))
        .values(used_at=now)
        .returning(OAuthCode.code_hash)
    )
    if used is None:
        raise TokenError("invalid_grant", "authorization code was already used")
    return await _issue(db, client, code.user_id, code.scopes, code.resource, now)


async def load_refresh_token(
    db: AsyncSession, client_id: str, token: str, *, now: datetime | None = None
) -> ConnectorRefreshToken | None:
    now = now or datetime.now(UTC)
    row = await db.get(OAuthRefreshToken, hash_token(token))
    if row is None or row.client_id != client_id or row.used_at is not None:
        return None
    if row.expires_at <= now:
        return None
    return ConnectorRefreshToken(
        token=token,
        client_id=row.client_id,
        scopes=row.scopes,
        expires_at=int(row.expires_at.timestamp()),
        resource=row.resource,
        subject=str(row.user_id),
        user_id=row.user_id,
    )


async def rotate_refresh_token(
    db: AsyncSession,
    client: OAuthClientInformationFull,
    token: ConnectorRefreshToken,
    scopes: list[str],
    *,
    now: datetime | None = None,
) -> OAuthToken:
    """Use the refresh token up and issue a new access and refresh token."""
    now = now or datetime.now(UTC)
    used = await db.scalar(
        update(OAuthRefreshToken)
        .where(
            OAuthRefreshToken.token_hash == hash_token(token.token),
            OAuthRefreshToken.used_at.is_(None),
        )
        .values(used_at=now)
        .returning(OAuthRefreshToken.token_hash)
    )
    if used is None:
        raise TokenError("invalid_grant", "refresh token was already used")
    return await _issue(db, client, token.user_id, scopes, token.resource, now)


async def revoke_refresh_token(
    db: AsyncSession, token: str, *, now: datetime | None = None
) -> None:
    now = now or datetime.now(UTC)
    await db.execute(
        update(OAuthRefreshToken)
        .where(OAuthRefreshToken.token_hash == hash_token(token))
        .values(used_at=now)
    )


async def _issue(
    db: AsyncSession,
    client: OAuthClientInformationFull,
    user_id: uuid.UUID,
    scopes: list[str],
    resource: str | None,
    now: datetime,
) -> OAuthToken:
    assert client.client_id is not None
    user = await db.get(User, user_id)
    if user is None or user.company_id is None:
        raise TokenError("invalid_grant", "the account can't be used")
    access = await issue_caller_token(
        db,
        user_id,
        "connector",
        _client_name(client.client_name),
        ACCESS_TOKEN_TTL,
        client_id=client.client_id,
        scopes=tuple(scopes),
        now=now,
    )
    refresh = new_token()
    db.add(
        OAuthRefreshToken(
            token_hash=hash_token(refresh),
            client_id=client.client_id,
            user_id=user_id,
            scopes=scopes,
            resource=resource,
            expires_at=now + REFRESH_TOKEN_TTL,
        )
    )
    await db.flush()
    return OAuthToken(
        access_token=access,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        scope=" ".join(scopes) or None,
        refresh_token=refresh,
    )
