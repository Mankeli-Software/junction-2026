"""The MCP server: the eight agent tools of vision §8 over Streamable HTTP, mounted at /mcp.

Each tool's arguments are the fields of its request model in `app.schemas` and its result
is the response model, sent as structured content. The REST twins use the same models, so
the two surfaces can't drift. Tools only get the caller, call one service function and map
errors. Nothing else is registered: no confirm, cancel, audit or inbox tool (vision §8).
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, create_model
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.interfaces.deps import resolve_caller
from app.interfaces.mcp import descriptions
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
    StrictModel,
    UpdateQuoteRequest,
)
from app.services import catalog, customers, quotes, recipes
from app.services.caller import Caller
from app.services.errors import ServiceError
from app.settings import get_settings

# Where RequireCaller leaves the caller in the request scope's state for the tools.
CALLER_STATE_KEY = "simo_caller"


async def _caller(ctx: Context) -> Caller:
    """The caller the mount check resolved; in-process clients (tests) resolve here."""
    request = ctx.request_context.request
    caller = request.scope.get("state", {}).get(CALLER_STATE_KEY) if request else None
    if caller is None:
        caller = await resolve_caller(request, "mcp")
    if caller is None:
        raise ToolError("not signed in")
    return caller


def _tool(
    name: str,
    description: str,
    service: Callable[..., BaseModel | Awaitable[BaseModel]],
    request_model: type[StrictModel] | None,
    response_model: type[BaseModel],
) -> Tool:
    """A tool whose arguments are exactly the request model's fields.

    The SDK builds the argument model from the function signature, so the tool is made from
    a generic function and its argument model is then swapped for one built on the request
    model. Unknown arguments are rejected, as in the REST twin.
    """

    async def run(ctx: Context, **arguments: Any) -> BaseModel:
        caller = await _caller(ctx)
        try:
            if request_model is None:
                result = service(caller)
            else:
                result = service(caller, request_model(**arguments))
            if inspect.isawaitable(result):
                result = await result
            return result
        except ServiceError as error:
            raise ToolError(str(error)) from error

    run.__annotations__["return"] = response_model
    tool = Tool.from_function(run, name=name, description=description, structured_output=True)

    arg_model = create_model(
        f"{name}Arguments", __base__=(request_model or StrictModel, ArgModelBase)
    )
    return tool.model_copy(
        update={
            "parameters": arg_model.model_json_schema(by_alias=True),
            "fn_metadata": tool.fn_metadata.model_copy(update={"arg_model": arg_model}),
        }
    )


TOOLS = [
    _tool(
        "search_products",
        descriptions.SEARCH_PRODUCTS,
        catalog.search_products,
        SearchProductsRequest,
        SearchProductsResponse,
    ),
    _tool(
        "get_customer_context",
        descriptions.GET_CUSTOMER_CONTEXT,
        customers.get_customer_context,
        None,
        CustomerContext,
    ),
    _tool(
        "search_recipes",
        descriptions.SEARCH_RECIPES,
        recipes.search_recipes,
        SearchRecipesRequest,
        SearchRecipesResponse,
    ),
    _tool("get_recipe", descriptions.GET_RECIPE, recipes.get_recipe, GetRecipeRequest, Recipe),
    _tool(
        "build_quote",
        descriptions.BUILD_QUOTE,
        quotes.build_quote,
        BuildQuoteRequest,
        QuoteResponse,
    ),
    _tool(
        "update_quote",
        descriptions.UPDATE_QUOTE,
        quotes.update_quote,
        UpdateQuoteRequest,
        QuoteResponse,
    ),
    _tool(
        "request_confirmation",
        descriptions.REQUEST_CONFIRMATION,
        quotes.request_confirmation,
        RequestConfirmationRequest,
        ConfirmationRequestResponse,
    ),
    _tool(
        "get_order_status",
        descriptions.GET_ORDER_STATUS,
        quotes.get_order_status,
        GetOrderStatusRequest,
        OrderStatusResponse,
    ),
]


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection that lets our own host names through.

    The SDK's default for a localhost bind only accepts `Host: localhost`, which would
    reject requests coming through Caddy for the public name.
    """
    hosts = get_settings().mcp_allowed_host_list
    origins = [f"{scheme}://{host}" for host in hosts for scheme in ("https", "http")]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


mcp = FastMCP(
    "simo",
    tools=TOOLS,
    stateless_http=True,
    streamable_http_path="/",
    transport_security=_transport_security(),
)


class RequireCaller:
    """Resolves the bearer token on the mount, before the MCP transport.

    Answers 401 when nobody is signed in; otherwise leaves the caller in the scope's state,
    where the tools pick it up, so a request looks the token up once.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            caller = await resolve_caller(HTTPConnection(scope), "mcp")
            if caller is None:
                response = JSONResponse(
                    {"detail": "Not signed in"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
            scope.setdefault("state", {})[CALLER_STATE_KEY] = caller
        await self.app(scope, receive, send)


def mcp_app() -> ASGIApp:
    """The ASGI app to mount at /mcp. Run `mcp.session_manager.run()` in the lifespan."""
    return RequireCaller(mcp.streamable_http_app())
