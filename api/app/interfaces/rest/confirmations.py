"""The confirmation page's endpoints (#47, technical-plan.md §9.4). Web only.

The token in the path is the authorisation for the page: whoever holds the link can open
it and act on it, with no login (`docs/specs/confirmation-page.md` §2). The page's server
(SvelteKit) calls these, so no cookie is needed. They are never agent tools, never
registered as WebMCP tools, and never take an MCP token or the dev caller.

Every action is one transaction. A refused action still commits what it wrote: a requote
at confirm replaces the quote and then answers 409. A refusal answers
`{"detail": {"text": {"fi", "en"}, "line_id"}}`, which the page shows.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.schemas import (
    AcknowledgeRequest,
    CancelRequest,
    ConfirmationErrorDetail,
    ConfirmationView,
    ConfirmRequest,
    ConfirmResponse,
    EditRequest,
)
from app.services import confirmation_page
from app.services.confirmation_page import ConfirmationRefused

router = APIRouter(prefix="/confirmations", tags=["confirmation page"])

# The view holds the order and the quote hash: never cached on the way.
NO_STORE = {"Cache-Control": "no-store"}

REFUSALS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Unknown link"},
    409: {"model": ConfirmationErrorDetail, "description": "Stale quote, closed, or requoted"},
    410: {"model": ConfirmationErrorDetail, "description": "Expired (production only)"},
    422: {"model": ConfirmationErrorDetail, "description": "Not possible, or a flag unchecked"},
}


async def _run[T](action: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async with get_sessionmaker()() as db:
        try:
            result = await action(db)
        except ConfirmationRefused:
            await db.commit()
            raise
        await db.commit()
        return result


@router.get("/{token}", response_model=ConfirmationView, responses={404: REFUSALS[404]})
async def get_confirmation(token: str, response: Response) -> ConfirmationView:
    """The page's view. Never uses the token up; stays readable as the receipt."""
    response.headers.update(NO_STORE)
    view = await _run(lambda db: confirmation_page.get_view(db, token))
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown confirmation link")
    return view


@router.post("/{token}/acknowledgements", status_code=204, responses=REFUSALS)
async def acknowledge(token: str, body: AcknowledgeRequest) -> None:
    await _run(lambda db: confirmation_page.acknowledge(db, token, body))


@router.post("/{token}/edits", status_code=204, responses=REFUSALS)
async def edit(token: str, body: Annotated[EditRequest, Body()]) -> None:
    await _run(lambda db: confirmation_page.edit(db, token, body))


@router.post("/{token}/confirm", response_model=ConfirmResponse, responses=REFUSALS)
async def confirm(token: str, body: ConfirmRequest) -> ConfirmResponse:
    return await _run(lambda db: confirmation_page.confirm(db, token, body))


@router.post("/{token}/cancel", status_code=204, responses=REFUSALS)
async def cancel(token: str, body: CancelRequest) -> None:
    await _run(lambda db: confirmation_page.cancel(db, token, body))


async def _refused(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ConfirmationRefused)
    return JSONResponse(
        {"detail": error.detail().model_dump(mode="json")},
        status_code=error.status,
        headers=NO_STORE,
    )


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ConfirmationRefused, _refused)
