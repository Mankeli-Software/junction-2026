"""REST twins of the agent tools (technical-plan.md §9.1), with the same models as the tools.

Routes only parse, get the caller, call one service function and map errors.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.interfaces.deps import current_caller
from app.schemas import (
    BuildQuoteRequest,
    ConfirmationRequestResponse,
    CustomerContext,
    GetOrderStatusRequest,
    GetRecipeRequest,
    OrderStatusResponse,
    QuoteResponse,
    Recipe,
    RequestConfirmationRequest,
    SearchProductsRequest,
    SearchProductsResponse,
    SearchRecipesRequest,
    SearchRecipesResponse,
    UpdateQuoteRequest,
)
from app.services import catalog, customers, quotes, recipes
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError

router = APIRouter(tags=["tools"])

CurrentCaller = Annotated[Caller, Depends(current_caller)]


def _build[M: BaseModel](model: type[M], **data: object) -> M:
    """Build a request model from path and query values, with a 422 on bad values."""
    try:
        return model(**data)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


@router.get("/products", response_model=SearchProductsResponse)
def search_products(
    caller: CurrentCaller, request: Annotated[SearchProductsRequest, Query()]
) -> SearchProductsResponse:
    return catalog.search_products(caller, request)


@router.get("/customer-context", response_model=CustomerContext)
def get_customer_context(caller: CurrentCaller) -> CustomerContext:
    return customers.get_customer_context(caller)


@router.get("/recipes", response_model=SearchRecipesResponse)
def search_recipes(
    caller: CurrentCaller, request: Annotated[SearchRecipesRequest, Query()]
) -> SearchRecipesResponse:
    return recipes.search_recipes(caller, request)


@router.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(caller: CurrentCaller, recipe_id: str, portions: int) -> Recipe:
    return recipes.get_recipe(
        caller, _build(GetRecipeRequest, recipe_id=recipe_id, portions=portions)
    )


@router.post("/quotes", response_model=QuoteResponse)
def build_quote(caller: CurrentCaller, request: BuildQuoteRequest) -> QuoteResponse:
    return quotes.build_quote(caller, request)


@router.post("/quotes/{quote_id}/update", response_model=QuoteResponse)
def update_quote(caller: CurrentCaller, quote_id: str, body: BuildQuoteRequest) -> QuoteResponse:
    """The body is the full new line list, as in `build_quote`. Returns a new quote."""
    return quotes.update_quote(
        caller, _build(UpdateQuoteRequest, quote_id=quote_id, lines=body.lines)
    )


@router.post("/quotes/{quote_id}/confirmation-request", response_model=ConfirmationRequestResponse)
def request_confirmation(caller: CurrentCaller, quote_id: str) -> ConfirmationRequestResponse:
    return quotes.request_confirmation(
        caller, _build(RequestConfirmationRequest, quote_id=quote_id)
    )


@router.get("/quotes/{quote_id}/status", response_model=OrderStatusResponse)
def get_order_status(caller: CurrentCaller, quote_id: str) -> OrderStatusResponse:
    return quotes.get_order_status(caller, _build(GetOrderStatusRequest, quote_id=quote_id))


async def _not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=404)


async def _conflict(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=409)


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(StateError, _conflict)
