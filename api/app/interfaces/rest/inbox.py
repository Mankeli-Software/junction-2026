"""The simulated phone inbox (#46, technical-plan.md §9.2): private, per user.

The link in a message is what authorises a confirmation, so these routes take the
`simo_session` cookie only (`web_session_user()`), never a bearer token or the dev caller,
and show only that user's messages. They are not agent tools.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.db import get_session, get_sessionmaker
from app.interfaces.deps import web_session_user
from app.services import confirmations
from app.services.caller import Caller
from app.services.confirmations import InboxMessage

router = APIRouter(prefix="/private", tags=["inbox"])

WebUser = Annotated[Caller, Depends(web_session_user)]

PRIVATE_HEADERS = {"Cache-Control": "no-store"}


@router.get("/inbox", response_model=list[InboxMessage])
async def get_inbox(
    user: WebUser, response: Response, db: Annotated[AsyncSession, Depends(get_session)]
) -> list[InboxMessage]:
    """This browser's messages, oldest first. Held messages appear when the call ends."""
    response.headers.update(PRIVATE_HEADERS)
    return await confirmations.inbox(db, user.user_id)


@router.get("/inbox/stream", response_class=EventSourceResponse)
async def inbox_stream(user: WebUser) -> EventSourceResponse:
    """Server-sent events: `snapshot` (the inbox so far, as `GET /inbox`), then one
    `inbox_message` per new message, with the message as JSON."""

    async def snapshot() -> list[dict]:
        async with get_sessionmaker()() as db:
            messages = await confirmations.inbox(db, user.user_id)
        return [m.model_dump(mode="json") for m in messages]

    # The broadcaster sends its own comment pings, so sse-starlette's are off.
    return EventSourceResponse(
        confirmations.inbox_events(user.user_id, snapshot),
        ping=0,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
