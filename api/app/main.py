"""FastAPI entry point: the REST API under /api/v1, the MCP server at /mcp and its OAuth
routes (`/.well-known/*`, `/oauth/*`)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import get_engine
from app.interfaces.auth.routes import auth_routes
from app.interfaces.mcp.server import mcp, mcp_app
from app.interfaces.rest import accounts as rest_accounts
from app.interfaces.rest import confirmations as rest_confirmations
from app.interfaces.rest import dashboard as rest_dashboard
from app.interfaces.rest import inbox as rest_inbox
from app.interfaces.rest import oauth as rest_oauth
from app.interfaces.rest import tools as rest_tools


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


class McpSlashMiddleware:
    """Serves /mcp like /mcp/, so clients never see the mount's trailing-slash redirect."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


app = FastAPI(
    title="S.I.MO ordering API",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    lifespan=lifespan,
)
app.add_middleware(McpSlashMiddleware)
app.include_router(rest_tools.router, prefix="/api/v1")
app.include_router(rest_dashboard.router, prefix="/api/v1")
app.include_router(rest_accounts.router, prefix="/api/v1")
app.include_router(rest_inbox.router, prefix="/api/v1")
app.include_router(rest_oauth.router, prefix="/api/v1")
app.include_router(rest_confirmations.router, prefix="/api/v1")
rest_tools.add_error_handlers(app)
rest_confirmations.add_error_handlers(app)
rest_confirmations.redact_access_log()
app.router.routes.extend(auth_routes())
app.mount("/mcp", mcp_app())


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {"status": "ok", "database": database}
