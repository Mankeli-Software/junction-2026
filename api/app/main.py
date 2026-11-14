"""FastAPI entry point: the REST API under /api/v1, the MCP server at /mcp, its OAuth
routes (`/.well-known/*`, `/oauth/*`), the quote signing key (`/.well-known/jwks.json`)
and the phone call's voice socket at /voice/ws."""

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
from app.interfaces.rest import jwks as rest_jwks
from app.interfaces.rest import oauth as rest_oauth
from app.interfaces.rest import recipe_drafts as rest_recipe_drafts
from app.interfaces.rest import tools as rest_tools
from app.interfaces.voice import routes as voice_routes
from app.observability import excluded as excluded_from_telemetry
from app.observability import setup_observability
from app.services.dashboard.feed import start_feed
from app.services.dashboard.stream import get_broadcaster
from app.services.signing import signing_key
from app.telemetry import TestTagsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    signing_key()  # fail at startup, not at the first quote, when the key is missing or bad
    # One LISTEN status_events connection for the public dashboard stream (#49).
    listener, _ = start_feed(get_broadcaster())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        await listener.stop()


class McpSlashMiddleware:
    """Serves /mcp like /mcp/, so clients never see the mount's trailing-slash redirect."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


setup_observability()  # before the app exists, so the FastAPI instrumentation applies

app = FastAPI(
    title="S.I.MO ordering API",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    lifespan=lifespan,
    # FastAPI's own telemetry makes the request spans; keep tokens and polling out (#46).
    telemetry={"exclude": excluded_from_telemetry},
)
app.add_middleware(McpSlashMiddleware)
# Performance test runs tag their requests (X-Simo-Test-Run, #84).
app.add_middleware(TestTagsMiddleware)
app.include_router(rest_tools.router, prefix="/api/v1")
app.include_router(rest_recipe_drafts.router, prefix="/api/v1")
app.include_router(rest_dashboard.router, prefix="/api/v1")
app.include_router(rest_accounts.router, prefix="/api/v1")
app.include_router(rest_inbox.router, prefix="/api/v1")
app.include_router(rest_oauth.router, prefix="/api/v1")
app.include_router(rest_confirmations.router, prefix="/api/v1")
app.include_router(rest_jwks.router)
app.include_router(voice_routes.router)
rest_dashboard.event_stream_openapi(app, "/api/v1/public/stream")
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
