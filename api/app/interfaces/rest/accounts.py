"""Demo accounts and web sessions (#44, `technical-plan.md` §9.2).

Typing a phone number logs the browser in. The routes parse, call one service function,
commit and set or clear the `simo_session` cookie.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.interfaces.deps import SESSION_COOKIE, current_caller
from app.schemas import DemoAccountRequest, DemoAccountResponse, Me
from app.services import accounts
from app.services.caller import Caller
from app.services.phone import InvalidPhoneNumber
from app.settings import get_settings

router = APIRouter(tags=["accounts"])

Db = Annotated[AsyncSession, Depends(get_session)]


def _cookie_options() -> dict[str, object]:
    return {
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": get_settings().env != "dev",
    }


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(SESSION_COOKIE, token, expires=expires_at, **_cookie_options())


@router.post(
    "/demo/accounts", status_code=status.HTTP_201_CREATED, response_model=DemoAccountResponse
)
async def create_demo_account(
    body: DemoAccountRequest, request: Request, response: Response, db: Db
) -> DemoAccountResponse:
    """Log this browser in as a user of the number's company, creating it if it's new.

    The same browser typing the same number again stays the same user.
    """
    try:
        account = await accounts.create_demo_account(
            db, body.phone_e164, body.exclusions, body.lang, request.cookies.get(SESSION_COOKIE)
        )
    except InvalidPhoneNumber as error:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "phone_e164"),
                    "msg": f"Invalid phone number: {error}",
                    "input": body.phone_e164,
                }
            ]
        ) from error
    await db.commit()
    _set_session_cookie(response, account.session_token, account.session_expires_at)
    return DemoAccountResponse(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=account.exclusions,
        usual_items=account.usual_items,
        new_company=account.new_company,
        new_user=account.new_user,
    )


@router.get("/me", response_model=Me)
async def get_me(caller: Annotated[Caller, Depends(current_caller)]) -> Me:
    """This browser's session, or the dev caller when DEV_FAKE_CALLER is on, else 401.

    A bearer token doesn't count here: REST reads only the cookie.
    """
    return Me(
        user_id=caller.user_id,
        company_id=caller.company_id,
        company_name=caller.company_name,
        phone_masked=caller.phone_masked,
        exclusions=caller.exclusions,
        lang=caller.lang,
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(request: Request, db: Db) -> Response:
    """Log out: revoke this browser's session and clear the cookie. Safe to repeat."""
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        await accounts.revoke_session(db, raw)
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, **_cookie_options())
    return response
