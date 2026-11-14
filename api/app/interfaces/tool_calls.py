"""Runs one agent tool call for the MCP tools and their REST twins (#45).

Every tool call is one database transaction, which holds:

1. `tool_called` (tool name, full arguments),
2. whatever the service writes (session, quote, audit events),
3. `tool_returned` (the full response, or the error the caller gets).

If the service raises a `ServiceError`, its writes are rolled back to a savepoint, the
error is recorded as `tool_returned`, the transaction commits and the error is raised
again for the interface to map. Any other exception rolls back the whole call.

Tool events are public on the dashboard (technical-plan.md §9.5). No tool argument or
response carries a token, a link or a full phone number (vision §8), so they are stored as
they are.
"""

import inspect
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.interfaces.deps import DEV_CALLER
from app.models import Quote
from app.schemas import Localized
from app.services import audit, dev_caller, sessions
from app.services.caller import Caller
from app.services.errors import ServiceError
from app.settings import get_settings

# A service is either `fn(caller[, request])`, or async `fn(db, caller[, request])` when it
# needs the database.
Service = Callable[..., Any]


async def run_tool(
    name: str, caller: Caller, service: Service, request: BaseModel | None
) -> BaseModel:
    arguments = request.model_dump(mode="json") if request is not None else {}
    error: ServiceError | None = None
    async with get_sessionmaker()() as db, db.begin():
        if _is_dev_caller(caller):
            await dev_caller.ensure_rows(db, caller)
        quote_id = arguments.get("quote_id")
        session = await sessions.session_for_tool(db, caller, quote_id)
        named_quote = await _known_quote(db, session.id, quote_id)
        await audit.record(
            db,
            type="tool_called",
            actor="agent",
            session_id=session.id,
            quote_id=named_quote,
            payload={"tool": name, "arguments": arguments},
            text=Localized(fi=f"Agentti kutsui: {name}", en=f"The agent called {name}"),
        )
        try:
            async with db.begin_nested():
                result = await _call(service, db, caller, request)
        except ServiceError as raised:
            error = raised
            payload = {"tool": name, "error": str(raised)}
            text = Localized(fi=f"{name}: virhe: {raised}", en=f"{name} failed: {raised}")
            returned_quote = named_quote
        else:
            response = result.model_dump(mode="json")
            payload = {"tool": name, "response": response}
            text = Localized(fi=f"{name} vastasi", en=f"{name} returned")
            returned_quote = sessions.parse_uuid(response.get("quote_id")) or named_quote
        await audit.record(
            db,
            type="tool_returned",
            actor="service",
            session_id=session.id,
            quote_id=returned_quote,
            payload=payload,
            text=text,
        )
    if error is not None:
        raise error
    return result


async def _call(
    service: Service, db: AsyncSession, caller: Caller, request: BaseModel | None
) -> BaseModel:
    args = (caller,) if request is None else (caller, request)
    if inspect.iscoroutinefunction(service):
        return await service(db, *args)
    return service(*args)


async def _known_quote(
    db: AsyncSession, session_id: uuid.UUID, quote_id: str | None
) -> uuid.UUID | None:
    """The named quote's id when it belongs to this session, else None."""
    quote_uuid = sessions.parse_uuid(quote_id)
    if quote_uuid is None:
        return None
    found = await db.get(Quote, quote_uuid)
    return quote_uuid if found is not None and found.session_id == session_id else None


def _is_dev_caller(caller: Caller) -> bool:
    # resolve_caller hands out the demo customer with DEV_FAKE_CALLER=true, and on /mcp also
    # with MCP_AUTH_REQUIRED=false (#48).
    settings = get_settings()
    demo_allowed = settings.dev_fake_caller or not settings.mcp_auth_required
    return demo_allowed and caller.user_id == DEV_CALLER.user_id
