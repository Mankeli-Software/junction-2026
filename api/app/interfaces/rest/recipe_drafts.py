"""Recipe draft routes that are not agent tools (#80, docs/plans/80-recipe-photo.md §6.1).

The webshop chat uploads a recipe photo here (`/read`, web session only: an agent never
uploads through us), and its "Recipe I read" card reads a draft, starts over (discard) and
makes "Edit as new draft" (copy). `propose_recipe` and `confirm_recipe` are agent tools, so
their REST twins are in `tools.py`. Each route is one transaction.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.interfaces.deps import current_caller, web_session_user
from app.interfaces.tool_calls import ensure_caller_rows
from app.schemas import RecipeDraft
from app.services import recipe_drafts, recipe_reading
from app.services.caller import Caller

router = APIRouter(prefix="/recipe-drafts", tags=["recipe drafts"])

CurrentCaller = Annotated[Caller, Depends(current_caller)]
WebUser = Annotated[Caller, Depends(web_session_user)]

READ_CHUNK = 1024 * 1024


async def _run(
    caller: Caller, action: Callable[[AsyncSession], Awaitable[RecipeDraft]]
) -> RecipeDraft:
    async with get_sessionmaker()() as db, db.begin():
        await ensure_caller_rows(db, caller)
        return await action(db)


@router.post(
    "/read",
    response_model=RecipeDraft,
    responses={
        413: {"description": "The photo is over RECIPE_PHOTO_MAX_MB"},
        415: {"description": "Not a JPEG, PNG, WebP or HEIC photo"},
        422: {"description": "No recipe found in the photo"},
        502: {"description": "The reading failed"},
        503: {"description": "Photo reading is not set up (no vision model)"},
        504: {"description": "The reading took too long"},
    },
)
async def read_recipe_photo(
    caller: WebUser, photo: UploadFile, portions: Annotated[int | None, Form(ge=1, le=1000)] = None
) -> RecipeDraft:
    """Read a recipe photo into a new draft for the buyer to check and confirm. The photo
    is never stored; the draft keeps the SHA-256 of the normalised image."""
    data = bytearray()
    while chunk := await photo.read(READ_CHUNK):
        data += chunk
        try:
            recipe_reading.check_size(len(data))
        except recipe_reading.ReadingError as error:
            raise HTTPException(error.status, str(error)) from error
    try:
        reading = await recipe_reading.read_photo(bytes(data), caller.lang, portions)
    except recipe_reading.ReadingError as error:
        raise HTTPException(error.status, str(error)) from error
    finally:
        data.clear()
    return await _run(
        caller,
        lambda db: recipe_drafts.propose(
            db, caller, reading.request, image_sha256=reading.image_sha256
        ),
    )


@router.get("/{draft_id}", response_model=RecipeDraft)
async def get_recipe_draft(caller: CurrentCaller, draft_id: str) -> RecipeDraft:
    return await _run(caller, lambda db: recipe_drafts.get(db, caller, draft_id))


@router.post("/{draft_id}/discard", response_model=RecipeDraft)
async def discard_recipe_draft(caller: CurrentCaller, draft_id: str) -> RecipeDraft:
    """The card's "Start over". A confirmed draft can't be discarded (409)."""
    return await _run(caller, lambda db: recipe_drafts.discard(db, caller, draft_id))


@router.post("/{draft_id}/copy", response_model=RecipeDraft)
async def copy_recipe_draft(caller: CurrentCaller, draft_id: str) -> RecipeDraft:
    """The card's "Edit as new draft": a new draft with the same content, to confirm."""
    return await _run(caller, lambda db: recipe_drafts.copy_as_new(db, caller, draft_id))
