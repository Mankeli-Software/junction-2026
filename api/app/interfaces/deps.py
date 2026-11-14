"""Caller identity for the REST routes and the MCP tools.

Until real accounts land, the only caller is the fixed demo customer, and only when
DEV_FAKE_CALLER is on. #44 replaces the body of `resolve_caller()` with the token and
session lookup; the routes and tools don't change.
"""

from fastapi import HTTPException, Request, status
from starlette.requests import HTTPConnection

from app.schemas import Exclusion
from app.services.caller import Caller, Channel
from app.settings import get_settings

DEV_CALLER = Caller(
    user_id="dev-user",
    company_id="dev-hassu-hauki",
    company_name="Hassu Hauki Oy",
    phone_masked="+358 40 *** **12",
    exclusions=[Exclusion.milk_free],
    lang="fi",
    channel="web",
)


def resolve_caller(connection: HTTPConnection | None, channel: Channel) -> Caller | None:
    """The caller behind a request, or None when nobody is signed in.

    `connection` is None for in-process MCP clients (tests). `channel` is fixed per surface
    until #44 reads it from the token or session.
    """
    if get_settings().dev_fake_caller:
        return DEV_CALLER.model_copy(update={"channel": channel})
    return None


def current_caller(request: Request) -> Caller:
    """FastAPI dependency for the REST routes: the caller, or 401."""
    caller = resolve_caller(request, "web")
    if caller is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return caller
