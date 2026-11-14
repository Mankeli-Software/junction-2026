"""Runs one agent tool call for the MCP tools and their REST twins (#45).

Every tool call is one database transaction, which holds:

1. `tool_called` (tool name, full arguments),
2. whatever the service writes (session, quote, audit events),
3. `tool_returned` (the full response, or the error the caller gets).

If the service raises a `ServiceError`, its writes are rolled back to a savepoint, the
error is recorded as `tool_returned`, the transaction commits and the error is raised
again for the interface to map. Any other exception rolls back the whole call.

Tool events are public on the dashboard (technical-plan.md §9.5), and audit events hold
masked identities only (§8.5). A buyer may still type a phone number, an email or a
confirmation link into a line, so the request is masked first, with the dashboard's own
`redact()` (#90): the service, the engine, the stored quote, every event and the response
all see the same masked text, and a quote replays exactly from its events. The audit
writer's refusal stays as the safety net.
"""

import inspect
import logging
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import telemetry
from app.db import get_sessionmaker
from app.interfaces.deps import DEV_CALLER
from app.models import Quote
from app.schemas import Localized
from app.services import audit, dev_caller, sessions
from app.services.caller import Caller
from app.services.dashboard.redact import redact
from app.services.errors import ServiceError
from app.settings import get_settings

# A service is either `fn(caller[, request])`, or async `fn(db, caller[, request])` when it
# needs the database.
Service = Callable[..., Any]


async def run_tool(
    name: str, caller: Caller, service: Service, request: BaseModel | None
) -> BaseModel:
    """Run the tool inside its own span and correlation context (#84): every span and log
    line under it carries the tool, the channel, the company and, once known, the session."""
    request = _masked(request)
    arguments = request.model_dump(mode="json") if request is not None else {}
    timer = telemetry.Timer()
    with (
        telemetry.bound(
            tool=name,
            channel=caller.channel,
            client_name=caller.client_name,
            company_id=caller.company_id,
            user_id=caller.user_id,
        ),
        telemetry.span(f"tool {name}", arguments=telemetry.summary(arguments)),
    ):
        try:
            result = await _run(name, caller, service, request, arguments)
        except ServiceError as error:
            _observe(name, "error", timer, error=str(error))
            raise
        except Exception as error:
            _observe(name, "error", timer, error=f"{type(error).__name__}: {error}")
            raise
        outcome, counts = _outcome(result.model_dump(mode="json"))
        _observe(name, outcome, timer, result=telemetry.summary(result), **counts)
        return result


async def _run(
    name: str, caller: Caller, service: Service, request: BaseModel | None, arguments: dict
) -> BaseModel:
    error: ServiceError | None = None
    async with get_sessionmaker()() as db, db.begin():
        await ensure_caller_rows(db, caller)
        quote_id = arguments.get("quote_id")
        session = await sessions.session_for_tool(db, caller, quote_id)
        # Kept apart: a savepoint rolled back on a ServiceError expires the session row when
        # the service touched it, and reloading it here would need IO outside the loop.
        session_id = session.id
        named_quote = await _known_quote(db, session_id, quote_id)
        with telemetry.bound(session_id=session_id, quote_id=named_quote):
            await audit.record(
                db,
                type="tool_called",
                actor="agent",
                session_id=session_id,
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
            telemetry.annotate(quote_id=returned_quote)
            await audit.record(
                db,
                type="tool_returned",
                actor="service",
                session_id=session_id,
                quote_id=returned_quote,
                payload=payload,
                text=text,
            )
    if error is not None:
        raise error
    return result


def _masked(request: BaseModel | None) -> BaseModel | None:
    """The request with phone numbers, emails and confirmation links masked in its text."""
    if request is None:
        return None
    data = request.model_dump(mode="json")
    masked = redact(data)
    return request if masked == data else type(request).model_validate(masked)


def _outcome(response: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """A short outcome code and the counts that explain it, for spans, logs and metrics."""
    counts = {
        key: len(value)
        for key in ("results", "lines", "flags", "rejections", "clarifications", "ingredients")
        if isinstance(value := response.get(key), list)
    }
    if decision := response.get("decision"):
        return str(decision), counts
    if "results" in counts and counts["results"] == 0:
        return "empty", counts
    return "ok", counts


def _observe(name: str, outcome: str, timer: telemetry.Timer, **attrs: Any) -> None:
    """Close the tool's span with its outcome, write its log line and record its metrics."""
    telemetry.annotate(outcome=outcome, duration_ms=timer.ms, **attrs)
    if outcome == "error":
        telemetry.failed(str(attrs.get("error", "tool error")))
    level = logging.WARNING if outcome in ("error", "empty", "rejected") else logging.INFO
    telemetry.event(
        f"tool {name}: {outcome}", level, outcome=outcome, duration_ms=timer.ms, **attrs
    )
    metric = telemetry.metric_attrs(tool=name, outcome=outcome)
    telemetry.tool_duration.record(timer.ms, metric)
    telemetry.tool_calls.add(1, metric)


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


async def ensure_caller_rows(db: AsyncSession, caller: Caller) -> None:
    """The demo customer's rows, when the caller is the dev caller; for routes outside
    `run_tool` that write rows owned by the caller."""
    if _is_dev_caller(caller):
        await dev_caller.ensure_rows(db, caller)


def _is_dev_caller(caller: Caller) -> bool:
    # resolve_caller hands out the demo customer with DEV_FAKE_CALLER=true, and on /mcp also
    # with MCP_AUTH_REQUIRED=false (#48).
    settings = get_settings()
    demo_allowed = settings.dev_fake_caller or not settings.mcp_auth_required
    return demo_allowed and caller.user_id == DEV_CALLER.user_id
