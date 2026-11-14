"""Caller identity for the REST routes and the MCP tools (#44, `technical-plan.md` §9.2).

`resolve_caller()` tries, in order:

1. REST: the `simo_session` cookie, a web session, so the caller's channel is `web`.
2. MCP: `Authorization: Bearer <token>`, an access token (the relay's and chat's caller
   tokens, later #48's OAuth tokens), with the token's channel and client name.
3. `DEV_FAKE_CALLER=true` (tests and local dev only): the fixed demo customer. On `/mcp`
   only, `MCP_AUTH_REQUIRED=false` does the same, for trying a connector with auth off
   (#48); it defaults to true.

Each surface reads only its own credential: a bearer token never works on REST and a
cookie never works on `/mcp`. `web_session_user()` is stricter still: the cookie only, no
dev caller, for the confirmation and inbox endpoints (#46, #47), so no agent token can
confirm an order or read a link (vision §8).
"""

import uuid
from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.db import get_sessionmaker
from app.schemas import Exclusion
from app.services import accounts, tokens
from app.services.caller import Caller, Channel
from app.settings import get_settings

SESSION_COOKIE = "simo_session"

Surface = Literal["rest", "mcp"]

DEV_CALLER = Caller(
    user_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
    company_id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
    company_name="Hassu Hauki Oy",
    phone_masked="+358 40 *** **12",
    exclusions=[Exclusion.lactose_free],
    lang="fi",
    channel="web",
)

_DEV_CHANNEL: dict[Surface, Channel] = {"rest": "web", "mcp": "connector"}


def bearer_token(connection: HTTPConnection) -> str | None:
    scheme, _, token = connection.headers.get("authorization", "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


async def resolve_caller(connection: HTTPConnection | None, surface: Surface) -> Caller | None:
    """The caller behind a request, or None when nobody is signed in.

    `connection` is None for in-process MCP clients (tests), which only get the dev caller.
    Uses its own short database session, so it works on the `/mcp` mount too.
    """
    if connection is not None:
        if surface == "rest":
            raw = connection.cookies.get(SESSION_COOKIE)
            if raw:
                async with get_sessionmaker()() as db:
                    caller = await _caller_from_session(db, raw)
                    await db.commit()  # keeps the last_seen_at bump
                if caller is not None:
                    return caller
        else:
            raw = bearer_token(connection)
            if raw:
                async with get_sessionmaker()() as db:
                    caller = await _caller_from_token(db, raw)
                if caller is not None:
                    return caller
    settings = get_settings()
    if settings.dev_fake_caller or (surface == "mcp" and not settings.mcp_auth_required):
        return DEV_CALLER.model_copy(update={"channel": _DEV_CHANNEL[surface]})
    return None


async def current_caller(request: Request) -> Caller:
    """FastAPI dependency for the REST routes: the caller, or 401."""
    caller = await resolve_caller(request, "rest")
    if caller is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return caller


async def web_session_user(request: Request) -> Caller:
    """FastAPI dependency for what only a person in a browser may do: the cookie or 401.

    Ignores bearer tokens and DEV_FAKE_CALLER. For #46's inbox and #47's confirmation.
    """
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        async with get_sessionmaker()() as db:
            caller = await _caller_from_session(db, raw)
            await db.commit()
        if caller is not None:
            return caller
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


async def session_user(request: Request) -> accounts.SessionUser:
    """FastAPI dependency: this browser's session, cookie only, or 401.

    Unlike `web_session_user()` it also accepts a hand-out account that has no number yet,
    for the routes that finish such an account or need only the user (#48).
    """
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        async with get_sessionmaker()() as db:
            session = await accounts.resolve_session(db, raw)
            await db.commit()
        if session is not None:
            return session
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


async def _caller_from_session(db: AsyncSession, raw: str) -> Caller | None:
    session = await accounts.resolve_session(db, raw)
    if session is None:
        return None
    return await _caller(db, session.user_id, "web")


async def _caller_from_token(db: AsyncSession, raw: str) -> Caller | None:
    token = await tokens.resolve_access_token(db, raw)
    if token is None:
        return None
    return await _caller(db, token.user_id, token.channel, token.client_name)


async def _caller(
    db: AsyncSession, user_id: uuid.UUID, channel: Channel, client_name: str | None = None
) -> Caller | None:
    account = await accounts.me(db, user_id)
    if account is None:
        return None
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=account.exclusions,
        lang=account.lang,
        channel=channel,
        client_name=client_name,
    )
