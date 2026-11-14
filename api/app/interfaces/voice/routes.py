"""`/voice/ws`: the phone page's call socket (technical-plan.md §9.3).

Signed in with the `simo_session` cookie only, like the inbox: the same user as the phone
page. The socket is accepted first and then closed with a code the page understands
(`web/src/lib/demo/types.ts`): 4401 when there is no session, 4429 when this user already
has a call.
"""

import logging

from fastapi import APIRouter, WebSocket

from app import telemetry
from app.db import get_sessionmaker
from app.interfaces.deps import SESSION_COOKIE
from app.interfaces.voice.relay import CLOSE_NO_SESSION, Call
from app.services import accounts

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/voice/ws")
async def voice_socket(ws: WebSocket) -> None:
    await ws.accept()
    raw = ws.cookies.get(SESSION_COOKIE)
    user = None
    if raw:
        async with get_sessionmaker()() as db:
            user = await accounts.resolve_session(db, raw)
            await db.commit()
    if user is None or user.company_id is None:
        await ws.close(CLOSE_NO_SESSION, "No demo session")
        return
    await Call(ws, user.user_id, test_tags=telemetry.test_tags(ws.headers)).run()
