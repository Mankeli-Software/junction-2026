"""From `status_events` to the public stream (#49, technical-plan.md §8.6).

One `PgListener("status_events", ...)` per process (started in the app's lifespan) wakes
the feed with a row id. The feed then reads every `status_events` row after the last one it
handled, so a lost or reordered notification only delays an event, and after a reconnect
`on_connect` catches up the same way. For each row it publishes, with `id` = the row id:

- `step`: the audit event as a `Step`,
- `transcript`: for `buyer_said` and `agent_said`,
- `order_updated`: the session's card with fresh totals (once per session per batch, with
  the id of the session's last row in it).

The broadcaster redacts everything again before it goes out.
"""

import asyncio
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_sessionmaker
from app.models import AuditEvent as AuditEventRow
from app.models import StatusEvent
from app.schemas import StepEvent, TranscriptEvent

from .listener import PgListener
from .orders import order_index_of, step_of, transcript_line_of
from .overview import load_order_updated
from .stream import Broadcaster, StreamEvent

log = logging.getLogger(__name__)

CHANNEL = "status_events"
BATCH = 500


class DashboardFeed:
    def __init__(
        self,
        broadcaster: Broadcaster,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.broadcaster = broadcaster
        self._sessionmaker = sessionmaker
        self.last_id: int | None = None  # the newest status_events id handled
        self._lock = asyncio.Lock()
        self.ready = asyncio.Event()  # set once the feed knows where to start

    def _session(self) -> AsyncSession:
        return (self._sessionmaker or get_sessionmaker())()

    async def on_connect(self) -> None:
        """First connect: start after the newest row (the snapshot covers the past).
        Reconnect: publish what was missed while the connection was down."""
        if self.last_id is None:
            async with self._session() as db:
                self.last_id = await db.scalar(select(func.max(StatusEvent.id))) or 0
            self.ready.set()
            return
        await self.catch_up()

    async def on_notify(self, payload: str) -> None:
        try:
            status_id = int(payload)
        except ValueError:
            log.warning("status_events: ignoring a notification that is not an id: %r", payload)
            return
        if self.last_id is not None and status_id <= self.last_id:
            return
        await self.catch_up()

    async def catch_up(self) -> None:
        async with self._lock:
            while await self._publish_batch():
                pass

    async def _publish_batch(self) -> bool:
        """Publish up to BATCH rows after `last_id`. True when there may be more."""
        async with self._session() as db:
            rows = (
                await db.execute(
                    select(StatusEvent.id, AuditEventRow)
                    .join(AuditEventRow, AuditEventRow.seq == StatusEvent.audit_seq)
                    .where(StatusEvent.id > (self.last_id or 0))
                    .order_by(StatusEvent.id)
                    .limit(BATCH)
                )
            ).all()
            if not rows:
                return False
            last_of_session: dict[uuid.UUID, int] = {}
            for status_id, event in rows:
                if event.session_id is not None:
                    last_of_session[event.session_id] = status_id
            for status_id, event in rows:
                try:
                    await self._publish_row(db, status_id, event, last_of_session)
                except Exception:
                    log.exception("status_events: could not publish row %s", status_id)
                self.last_id = status_id
            return len(rows) == BATCH

    async def _publish_row(
        self,
        db: AsyncSession,
        status_id: int,
        event: AuditEventRow,
        last_of_session: dict[uuid.UUID, int],
    ) -> None:
        if event.session_id is None:
            return  # a system event (rule_set_loaded): not part of any order
        session_id = str(event.session_id)
        step = step_of(event, await order_index_of(db, event))
        self._publish("step", StepEvent(session_id=session_id, step=step), status_id)
        line = transcript_line_of(event)
        if line is not None:
            self._publish(
                "transcript", TranscriptEvent(session_id=session_id, line=line), status_id
            )
        if last_of_session.get(event.session_id) == status_id:
            update = await load_order_updated(db, event.session_id)
            if update is not None:
                self._publish("order_updated", update, status_id)

    def _publish(self, kind, model, status_id: int) -> None:
        self.broadcaster.publish(StreamEvent(kind, model.model_dump(mode="json"), status_id))


def start_feed(
    broadcaster: Broadcaster,
    *,
    dsn: str | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> tuple[PgListener, DashboardFeed]:
    """Start the process's listener; stop it with `await listener.stop()`."""
    feed = DashboardFeed(broadcaster, sessionmaker)
    listener = PgListener(CHANNEL, feed.on_notify, dsn=dsn, on_connect=feed.on_connect)
    listener.start()
    return listener, feed
