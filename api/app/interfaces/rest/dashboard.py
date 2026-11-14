"""The public dashboard API (#49, technical-plan.md §9.5): no login, everything redacted.

Every response goes through `redact()` (`app.services.dashboard.redact`) after loading and
before serialising; the stream's broadcaster redacts each event again. An unknown or
malformed session id gives 404.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.db import get_session, get_sessionmaker
from app.schemas import (
    STATE_GROUPS,
    AuditEvent,
    Channel,
    OrderSummary,
    OverviewResponse,
    SessionState,
    StateGroup,
    Step,
    TranscriptLine,
    VerifyResult,
)
from app.services.dashboard import orders
from app.services.dashboard.overview import load_overview
from app.services.dashboard.redact import redact
from app.services.dashboard.stream import Broadcaster, StreamEvent, get_broadcaster

router = APIRouter(prefix="/public", tags=["dashboard"])

Db = Annotated[AsyncSession, Depends(get_session)]

PUBLIC_HEADERS = {"Cache-Control": "no-cache"}


def public_json(data: Any, headers: dict[str, str] | None = None) -> JSONResponse:
    """The data, JSON-ready and redacted."""
    return JSONResponse(redact(data), headers={**PUBLIC_HEADERS, **(headers or {})})


@router.get("/orders", response_model=OverviewResponse)
async def get_orders(
    db: Db,
    state: StateGroup | None = None,
    channel: Channel | None = None,
    since: datetime | None = None,
) -> JSONResponse:
    """Totals since `EVENT_START`, then at most 200 cards that match the filters, grouped by
    company, newest activity first."""
    return public_json(await load_overview(db, state, channel, since))


@router.get("/orders/{session_id}", response_model=OrderSummary)
async def get_order(session_id: str, db: Db) -> JSONResponse:
    return public_json(await orders.load_summary(db, session_id))


@router.get("/orders/{session_id}/steps", response_model=list[Step])
async def get_steps(session_id: str, db: Db) -> JSONResponse:
    return public_json([s.model_dump(mode="json") for s in await orders.load_steps(db, session_id)])


@router.get("/orders/{session_id}/transcript", response_model=list[TranscriptLine])
async def get_transcript(session_id: str, db: Db) -> JSONResponse:
    lines = await orders.load_transcript(db, session_id)
    return public_json([line.model_dump(mode="json") for line in lines])


@router.get("/orders/{session_id}/events", response_model=list[AuditEvent])
async def get_events(session_id: str, db: Db, download: bool = False) -> JSONResponse:
    """The session's full events; `?download=1` sends them as a file."""
    events = [e.model_dump(mode="json") for e in await orders.load_events(db, session_id)]
    headers = None
    if download:
        name = f"simo-order-{orders.parse_session_id(session_id)}-events.json"
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    return public_json(events, headers)


@router.get("/audit/verify", response_model=VerifyResult)
async def get_verify(db: Db, session_id: str | None = None) -> JSONResponse:
    """#41's chain check: one session's events, or the whole chain without `session_id`."""
    return public_json(await orders.verify(db, session_id))


async def current_overview(
    state: StateGroup | None, channel: Channel | None, since: datetime | None
) -> OverviewResponse:
    async with get_sessionmaker()() as db:
        return await load_overview(db, state, channel, since)


class OrderFilter:
    """Which `order_updated` events one subscriber gets: the cards that match its filters,
    plus one last update for a card it was shown that no longer matches, so the page can
    drop it."""

    def __init__(self, state: StateGroup | None, channel: Channel | None):
        self.state = state
        self.channel = channel
        self.shown: set[str] = set()

    def remember(self, overview: OverviewResponse) -> None:
        for company in overview.companies:
            self.shown.update(card.session_id for card in company.orders)

    def __call__(self, event: StreamEvent) -> bool:
        if event.event != "order_updated":
            return True
        card = event.data["order"]
        session_id = card["session_id"]
        matches = (self.state is None or _group(card["state"]) == self.state) and (
            self.channel is None or card["channel"] == self.channel
        )
        if matches:
            self.shown.add(session_id)
            return True
        if session_id in self.shown:
            self.shown.discard(session_id)
            return True
        return False


def _group(state: str) -> StateGroup | None:
    return STATE_GROUPS.get(SessionState(state))


@router.get("/stream", response_class=EventSourceResponse)
async def stream(
    broadcaster: Annotated[Broadcaster, Depends(get_broadcaster)],
    state: StateGroup | None = None,
    channel: Channel | None = None,
    since: datetime | None = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    """Server-sent events: `snapshot` (as `GET /orders`, with the same filters), then
    `order_updated` (filtered), `step` and `transcript`, each with `id` = the
    `status_events` id. A reconnect with `Last-Event-ID` gets the missed events first."""
    accept = OrderFilter(state, channel)

    async def snapshot() -> dict:
        overview = await current_overview(state, channel, since)
        accept.remember(overview)
        return overview.model_dump(mode="json")

    resume_from = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    # The broadcaster sends its own comment pings, so sse-starlette's are off.
    return EventSourceResponse(
        broadcaster.subscribe(snapshot, last_event_id=resume_from, accept=accept),
        ping=0,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
