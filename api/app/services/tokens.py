"""Opaque tokens: web session cookies and bearer access tokens for `/mcp` (#44).

A raw token is `secrets.token_urlsafe(32)` (32 random bytes). Only its SHA-256 is stored,
so a database leak gives no usable token.

Like the other services, these functions take the request's `AsyncSession` and only
flush: the caller commits.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessToken, User

# Covers the 10-minute call limit with room to spare.
CALLER_TOKEN_TTL = timedelta(minutes=15)

TokenChannel = Literal["phone", "web_chat", "connector"]


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


@dataclass(frozen=True)
class TokenCaller:
    """Who a valid bearer token acts for. #43's `current_caller()` turns this into a Caller."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    channel: TokenChannel
    client_name: str
    client_id: str | None
    scopes: tuple[str, ...]
    expires_at: datetime


async def issue_caller_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    channel: TokenChannel,
    client_name: str,
    ttl: timedelta = CALLER_TOKEN_TTL,
    *,
    client_id: str | None = None,
    scopes: tuple[str, ...] = (),
    now: datetime | None = None,
) -> str:
    """Store a new access token for the user and return the raw token.

    An internal function, not an endpoint: the voice relay calls it at call start with
    `channel="phone"`, `client_name="S.I.MO phone"`, and the chat panel with
    `channel="web_chat"`.
    """
    now = now or datetime.now(UTC)
    raw = new_token()
    db.add(
        AccessToken(
            token_hash=hash_token(raw),
            user_id=user_id,
            channel=channel,
            client_id=client_id,
            client_name=client_name,
            scopes=list(scopes),
            expires_at=now + ttl,
        )
    )
    await db.flush()
    return raw


async def resolve_access_token(
    db: AsyncSession, raw_token: str, *, now: datetime | None = None
) -> TokenCaller | None:
    """The caller for a bearer token, or None if it is unknown or expired, or its user is a
    hand-out account that has no number and so no company yet (#48)."""
    now = now or datetime.now(UTC)
    row = (
        await db.execute(
            select(AccessToken, User.company_id)
            .join(User, User.id == AccessToken.user_id)
            .where(AccessToken.token_hash == hash_token(raw_token), AccessToken.expires_at > now)
        )
    ).one_or_none()
    if row is None:
        return None
    token, company_id = row
    if company_id is None:
        return None
    return TokenCaller(
        user_id=token.user_id,
        company_id=company_id,
        channel=token.channel,
        client_name=token.client_name,
        client_id=token.client_id,
        scopes=tuple(token.scopes),
        expires_at=token.expires_at,
    )
