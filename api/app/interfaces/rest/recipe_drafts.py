"""Recipe draft routes that are not agent tools (#80, docs/plans/80-recipe-photo.md §6.1).

The webshop chat's "Recipe I read" card reads a draft, starts over (discard) and makes
"Edit as new draft" (copy) here. `propose_recipe` and `confirm_recipe` are agent tools, so
their REST twins are in `tools.py`. Each route is one transaction.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.interfaces.deps import current_caller
from app.interfaces.tool_calls import ensure_caller_rows
from app.schemas import RecipeDraft
from app.services import recipe_drafts
from app.services.caller import Caller

router = APIRouter(prefix="/recipe-drafts", tags=["recipe drafts"])

CurrentCaller = Annotated[Caller, Depends(current_caller)]


async def _run(
    caller: Caller, action: Callable[[AsyncSession], Awaitable[RecipeDraft]]
) -> RecipeDraft:
    async with get_sessionmaker()() as db, db.begin():
        await ensure_caller_rows(db, caller)
        return await action(db)


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
