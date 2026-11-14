"""Demo accounts, connector accounts and web sessions (#44, #48, `technical-plan.md` §9.2).

Typing a phone number logs the browser in; connector accounts log in with an email and a
password. The routes parse, call one service function, commit and set or clear the
`simo_session` cookie.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.interfaces.deps import SESSION_COOKIE, current_caller, session_user
from app.schemas import (
    DemoAccountRequest,
    DemoAccountResponse,
    LoginRequest,
    LoginResponse,
    Me,
    PhoneRequest,
    SignupRequest,
)
from app.services import accounts
from app.services.accounts import (
    EmailTaken,
    InvalidEmail,
    LoginFailed,
    PhoneAlreadySet,
    SessionUser,
    TooManyLogins,
    WeakPassword,
)
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


def _invalid(field: str, message: str, value: object) -> RequestValidationError:
    """A 422 in FastAPI's usual shape, for checks the request model can't make."""
    return RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": message, "input": value}]
    )


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
        raise _invalid("phone_e164", f"Invalid phone number: {error}", body.phone_e164) from error
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


# --- Connector accounts (#48) ---

# Neutral on purpose: never says whether the email or the password was wrong.
LOGIN_FAILED = "Wrong email or password"
EMAIL_TAKEN = "This email can't be used to sign up. Try logging in instead."


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=Me)
async def signup(body: SignupRequest, request: Request, response: Response, db: Db) -> Me:
    """Open sign-up for the connectors: email, password (10 characters or more) and number.

    Logs the browser in. The number's company is found or created as for a demo account.
    """
    try:
        result = await accounts.signup(
            db, body.email, body.password, body.phone_e164, request.cookies.get(SESSION_COOKIE)
        )
    except InvalidEmail as error:
        raise _invalid("email", "Invalid email address", body.email) from error
    except WeakPassword as error:
        raise _invalid("password", f"Password needs {error}", "***") from error
    except InvalidPhoneNumber as error:
        raise _invalid("phone_e164", f"Invalid phone number: {error}", body.phone_e164) from error
    except EmailTaken as error:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from error
    account = await accounts.me(db, result.user_id)
    await db.commit()
    assert account is not None
    _set_session_cookie(response, result.session_token, result.session_expires_at)
    return Me(**account.__dict__)


@router.post("/session", response_model=LoginResponse)
async def log_in(body: LoginRequest, request: Request, response: Response, db: Db) -> LoginResponse:
    """Log in with email and password. 401 for a wrong email or password alike; 429 after
    10 failed tries for the email within 10 minutes.

    `phone_required` tells the login page to ask a hand-out account for its number.
    """
    try:
        result = await accounts.login(
            db, body.email, body.password, request.cookies.get(SESSION_COOKIE)
        )
    except LoginFailed as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED) from error
    except TooManyLogins as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many tries. Try again in a few minutes."
        ) from error
    await db.commit()
    _set_session_cookie(response, result.session_token, result.session_expires_at)
    return LoginResponse(phone_required=result.phone_required)


@router.post("/me/phone", response_model=Me)
async def set_phone(
    body: PhoneRequest, session: Annotated[SessionUser, Depends(session_user)], db: Db
) -> Me:
    """Set the number of a hand-out account on its first login. Only while it has none: 409
    after that."""
    try:
        account = await accounts.set_phone(db, session.user_id, body.phone_e164)
    except InvalidPhoneNumber as error:
        raise _invalid("phone_e164", f"Invalid phone number: {error}", body.phone_e164) from error
    except PhoneAlreadySet as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "The phone number is already set") from error
    await db.commit()
    return Me(**account.__dict__)
