"""Sessions: one conversation each (#45 decision 2, `docs/specs/dashboard.md` §4).

- **Phone**: one session per call. The relay (#52) starts it with `start_call_session()`
  when the call connects; the call's tool calls then find it as the caller's latest open
  phone session.
- **MCP, WebMCP and chat**: a tool call reuses the caller's latest open session on the same
  channel and client if its last activity was under 10 minutes ago, otherwise it starts a
  new one (technical-plan.md §9.5).
- Tools that name a quote (`update_quote`, `request_confirmation`, `get_order_status`) use
  the quote's own session.

The functions take the caller's `AsyncSession` and only flush: the caller commits.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderSession, Quote
from app.schemas import Localized, SessionState
from app.services import audit
from app.services.caller import Caller

IDLE_TIMEOUT = timedelta(minutes=10)


async def current_session(
    db: AsyncSession, caller: Caller, *, now: datetime | None = None
) -> OrderSession:
    """The caller's session for a tool call that names no quote. Bumps its last activity."""
    now = now or datetime.now(UTC)
    session = await db.scalar(
        select(OrderSession)
        .where(
            OrderSession.user_id == caller.user_id,
            OrderSession.channel == caller.channel,
            OrderSession.client_name.is_not_distinct_from(caller.client_name),
            OrderSession.ended_at.is_(None),
            OrderSession.last_activity_at > now - IDLE_TIMEOUT,
        )
        .order_by(OrderSession.last_activity_at.desc())
        .limit(1)
        .with_for_update()
    )
    if session is None:
        return await _start(db, caller, now=now)
    touch(session, now)
    await db.flush()
    return session


async def start_call_session(
    db: AsyncSession,
    caller: Caller,
    *,
    call_id: str,
    prompt_version: str | None = None,
    now: datetime | None = None,
) -> OrderSession:
    """A new session for one phone call, for the voice relay (#52).

    The call's tool calls find it through `current_session()` as long as the relay's caller
    token has the `phone` channel. The relay ends it (`ended_at`, `ended_by`) at hang-up.
    """
    return await _start(
        db, caller, now=now or datetime.now(UTC), call_id=call_id, prompt_version=prompt_version
    )


async def quote_session(
    db: AsyncSession, quote: Quote, *, now: datetime | None = None
) -> OrderSession:
    """The quote's own session, locked and with its last activity bumped."""
    session = await db.get_one(OrderSession, quote.session_id, with_for_update=True)
    touch(session, now or datetime.now(UTC))
    await db.flush()
    return session


async def session_for_tool(
    db: AsyncSession, caller: Caller, quote_id: str | None, *, now: datetime | None = None
) -> OrderSession:
    """The session a tool call belongs to: the named quote's, if it is the caller's company's,
    otherwise the caller's current one."""
    quote_uuid = parse_uuid(quote_id)
    if quote_uuid is not None:
        quote = await db.scalar(
            select(Quote).where(Quote.id == quote_uuid, Quote.company_id == caller.company_id)
        )
        if quote is not None:
            return await quote_session(db, quote, now=now)
    return await current_session(db, caller, now=now)


def touch(session: OrderSession, now: datetime) -> None:
    session.last_activity_at = max(session.last_activity_at, now)


def set_state(session: OrderSession, state: SessionState, now: datetime) -> None:
    if session.state != state:
        session.state = state
        session.state_since = now


def parse_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _start(
    db: AsyncSession,
    caller: Caller,
    *,
    now: datetime,
    call_id: str | None = None,
    prompt_version: str | None = None,
) -> OrderSession:
    session = OrderSession(
        user_id=caller.user_id,
        company_id=caller.company_id,
        channel=caller.channel,
        client_name=caller.client_name,
        call_id=call_id,
        state=SessionState.in_conversation,
        state_since=now,
        started_at=now,
        last_activity_at=now,
        prompt_version=prompt_version,
    )
    db.add(session)
    await db.flush()
    await audit.record(
        db,
        type="session_started",
        actor="service",
        session_id=session.id,
        quote_id=None,
        payload={
            "channel": caller.channel,
            "client_name": caller.client_name,
            "call_id": call_id,
            "prompt_version": prompt_version,
        },
        text=Localized(fi="Keskustelu alkoi", en="Conversation started"),
    )
    return session
