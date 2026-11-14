"""REST twins of the agent tools (technical-plan.md §9.1), with the same models as the tools.

Routes only parse, get the caller, call one service function through `run_tool` (which
writes the `tool_called` and `tool_returned` audit events) and map errors.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.interfaces.deps import current_caller
from app.interfaces.tool_calls import run_tool
from app.schemas import (
    BuildQuoteRequest,
    ConfirmationRequestResponse,
    ConfirmRecipeBody,
    ConfirmRecipeRequest,
    CustomerContext,
    GetOrderStatusRequest,
    GetRecipeRequest,
    OrderStatusResponse,
    ProposeRecipeRequest,
    QuoteResponse,
    Recipe,
    RecipeDraft,
    RequestConfirmationRequest,
    SearchProductsRequest,
    SearchProductsResponse,
    SearchRecipesRequest,
    SearchRecipesResponse,
    UpdateQuoteRequest,
)
from app.services import catalog, customers, quotes, recipe_drafts, recipes
from app.services.caller import Caller
from app.services.errors import InvalidRequestError, NotFoundError, StateError

router = APIRouter(tags=["tools"])

CurrentCaller = Annotated[Caller, Depends(current_caller)]


def _build[M: BaseModel](model: type[M], **data: object) -> M:
    """Build a request model from path and query values, with a 422 on bad values."""
    try:
        return model(**data)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


@router.get("/products", response_model=SearchProductsResponse)
async def search_products(
    caller: CurrentCaller, request: Annotated[SearchProductsRequest, Query()]
) -> BaseModel:
    return await run_tool("search_products", caller, catalog.search_products, request)


@router.get("/customer-context", response_model=CustomerContext)
async def get_customer_context(caller: CurrentCaller) -> BaseModel:
    return await run_tool("get_customer_context", caller, customers.get_customer_context, None)


@router.get("/recipes", response_model=SearchRecipesResponse)
async def search_recipes(
    caller: CurrentCaller, request: Annotated[SearchRecipesRequest, Query()]
) -> BaseModel:
    return await run_tool("search_recipes", caller, recipes.search_recipes, request)


@router.get("/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe(caller: CurrentCaller, recipe_id: str, portions: int) -> BaseModel:
    request = _build(GetRecipeRequest, recipe_id=recipe_id, portions=portions)
    return await run_tool("get_recipe", caller, recipes.get_recipe, request)


@router.post("/recipe-drafts", response_model=RecipeDraft)
async def propose_recipe(caller: CurrentCaller, request: ProposeRecipeRequest) -> BaseModel:
    return await run_tool("propose_recipe", caller, recipe_drafts.propose, request)


@router.post("/recipe-drafts/{draft_id}/confirm", response_model=RecipeDraft)
async def confirm_recipe(
    caller: CurrentCaller, draft_id: str, body: ConfirmRecipeBody | None = None
) -> BaseModel:
    """The body holds the buyer's corrections; leave it out when nothing changed."""
    edits = body.model_dump(exclude_unset=True) if body is not None else {}
    request = _build(ConfirmRecipeRequest, draft_id=draft_id, **edits)
    return await run_tool("confirm_recipe", caller, recipe_drafts.confirm, request)


@router.post("/quotes", response_model=QuoteResponse)
async def build_quote(caller: CurrentCaller, request: BuildQuoteRequest) -> BaseModel:
    return await run_tool("build_quote", caller, quotes.build_quote, request)


@router.get("/quotes/current", response_model=QuoteResponse)
async def current_quote(
    caller: CurrentCaller, db: Annotated[AsyncSession, Depends(get_session)]
) -> QuoteResponse:
    """The caller's newest quote, for the webshop chat panel (§9.6). Not an agent tool."""
    return await quotes.current_quote(db, caller)


@router.get("/quotes/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    caller: CurrentCaller, db: Annotated[AsyncSession, Depends(get_session)], quote_id: str
) -> QuoteResponse:
    """One of the caller's company's quotes, for the webshop chat panel (§9.6)."""
    return await quotes.get_quote(db, caller, quote_id)


@router.post("/quotes/{quote_id}/update", response_model=QuoteResponse)
async def update_quote(caller: CurrentCaller, quote_id: str, body: BuildQuoteRequest) -> BaseModel:
    """The body is the full new line list, as in `build_quote`. Returns a new quote."""
    request = _build(UpdateQuoteRequest, quote_id=quote_id, lines=body.lines)
    return await run_tool("update_quote", caller, quotes.update_quote, request)


@router.post("/quotes/{quote_id}/confirmation-request", response_model=ConfirmationRequestResponse)
async def request_confirmation(caller: CurrentCaller, quote_id: str) -> BaseModel:
    request = _build(RequestConfirmationRequest, quote_id=quote_id)
    return await run_tool("request_confirmation", caller, quotes.request_confirmation, request)


@router.get("/quotes/{quote_id}/status", response_model=OrderStatusResponse)
async def get_order_status(caller: CurrentCaller, quote_id: str) -> BaseModel:
    request = _build(GetOrderStatusRequest, quote_id=quote_id)
    return await run_tool("get_order_status", caller, quotes.get_order_status, request)


async def _not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=404)


async def _conflict(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=409)


async def _invalid(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=422)


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(InvalidRequestError, _invalid)
    app.add_exception_handler(StateError, _conflict)
