"""The public dashboard API (#49, technical-plan.md §9.5): no login, everything redacted.

Only the stream exists so far. Its snapshot is EMPTY and nothing publishes to it until
#45 (`sessions`, `quotes`) and #41 (`status_events` and its NOTIFY trigger) land; see
`app/services/dashboard/overview.py`. The other endpoints of #49 come with them.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sse_starlette import EventSourceResponse

from app.schemas import Channel, StateGroup
from app.services.dashboard.overview import load_overview
from app.services.dashboard.stream import Broadcaster, get_broadcaster

router = APIRouter(prefix="/public", tags=["dashboard"])


@router.get("/stream", response_class=EventSourceResponse)
async def stream(
    broadcaster: Annotated[Broadcaster, Depends(get_broadcaster)],
    state: StateGroup | None = None,
    channel: Channel | None = None,
    since: datetime | None = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    """Server-sent events: `snapshot` (as `GET /orders`), then `order_updated`, `step` and
    `transcript`. A reconnect with `Last-Event-ID` gets the missed events first."""

    async def snapshot() -> dict:
        overview = await load_overview(state, channel, since)
        return overview.model_dump(mode="json")

    resume_from = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    # The broadcaster sends its own comment pings, so sse-starlette's are off.
    return EventSourceResponse(
        broadcaster.subscribe(snapshot, last_event_id=resume_from),
        ping=0,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
