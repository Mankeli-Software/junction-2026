"""The consent step of the connector login (#48): "Allow <client> to order for <company>?"

`/oauth/authorize` sends the browser to the SvelteKit page `/connect?request=<id>`, which
calls these. No session: 401, and the page sends the browser to `/login?next=...`. A
hand-out account without a number: 409, and the login page asks for it first.

Only a browser session counts (the cookie, never a bearer token or the dev caller). The
cookie is SameSite=Lax and the decision is a JSON POST, which another site can't send
with the cookie, so a page elsewhere can't press Allow for the visitor.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.interfaces.deps import session_user
from app.schemas import ConnectDecision, ConnectRedirect, ConnectRequestView
from app.services import accounts, oauth
from app.services.accounts import SessionUser

router = APIRouter(prefix="/oauth", tags=["oauth"])

Db = Annotated[AsyncSession, Depends(get_session)]
Session = Annotated[SessionUser, Depends(session_user)]

PHONE_REQUIRED = "phone_required"
GONE = "This sign-in request has expired. Start again from your assistant."


def _claimed(session: SessionUser) -> None:
    if session.phone_e164 is None:
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_REQUIRED)


@router.get("/requests/{request_id}", response_model=ConnectRequestView)
async def get_request(request_id: str, session: Session, db: Db) -> ConnectRequestView:
    """What the consent page shows. 404 when the request is unknown or expired."""
    _claimed(session)
    found = await oauth.pending_request(db, request_id)
    account = await accounts.me(db, session.user_id)
    if found is None or account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    request, client_name = found
    return ConnectRequestView(
        client_name=client_name,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        redirect_host=oauth.redirect_host(request.redirect_uri),
    )


@router.post("/requests/{request_id}", response_model=ConnectRedirect)
async def decide(
    request_id: str, body: ConnectDecision, session: Session, db: Db
) -> ConnectRedirect:
    """Allow issues a code for this user; Cancel sends `access_denied`. Either way the
    browser goes to `redirect_to`, back to the client."""
    _claimed(session)
    redirect = await oauth.decide(db, request_id, session.user_id, body.allow)
    if redirect is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    await db.commit()
    return ConnectRedirect(redirect_to=redirect)
