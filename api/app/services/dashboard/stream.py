"""Fan-out for the public dashboard stream (#49, technical-plan.md §8.6).

One `Broadcaster` per process. The `PgListener` (or anything else) calls `publish()`; each
browser connected to `/api/v1/public/stream` reads `subscribe()`, which starts with a
`snapshot` and then sends live events. A reconnect with `Last-Event-ID` gets the events it
missed from a small in-memory buffer instead, when the buffer still has them.
"""

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sse_starlette import ServerSentEvent

from app.schemas import StreamEventType

from .redact import redact

log = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 15.0
QUEUE_SIZE = 1000
HISTORY_SIZE = 1000


@dataclass(frozen=True)
class StreamEvent:
    """One event for the stream. `id` is the `status_events` seq, when there is one."""

    event: StreamEventType
    data: Any  # JSON-ready data; `publish()` redacts it
    id: int | None = None

    def to_sse(self) -> ServerSentEvent:
        return ServerSentEvent(
            data=json.dumps(self.data, ensure_ascii=False, separators=(",", ":")),
            event=self.event,
            id=None if self.id is None else str(self.id),
        )


PING = ServerSentEvent(comment="ping")

# Put in a dropped subscriber's queue so its reader wakes up and ends.
_DROPPED = object()

SnapshotFn = Callable[[], Awaitable[Any]]


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue


class Broadcaster:
    def __init__(self, *, queue_size: int = QUEUE_SIZE, history_size: int = HISTORY_SIZE):
        self._queue_size = queue_size
        self._subscribers: set[_Subscriber] = set()
        self._history: deque[StreamEvent] = deque(maxlen=history_size)
        # Events with an id at or below this one may be missing from the history: they were
        # evicted, or they came before the first one this process saw.
        self._floor: int | None = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def last_id(self) -> int | None:
        return self._history[-1].id if self._history else None

    def publish(self, event: StreamEvent) -> None:
        """Redact the event and hand it to every subscriber. Never blocks.

        A subscriber whose queue is full is dropped; its browser reconnects and gets a
        snapshot (or the missed events, if the history still has them).
        """
        event = StreamEvent(event.event, redact(event.data), event.id)
        if event.id is not None:
            if self._floor is None:
                self._floor = event.id - 1
            if len(self._history) == self._history.maxlen:
                self._floor = self._history[0].id
            self._history.append(event)
        for subscriber in list(self._subscribers):
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                self._drop(subscriber)

    def _drop(self, subscriber: _Subscriber) -> None:
        log.warning("Dropping a dashboard stream subscriber whose queue is full")
        self._subscribers.discard(subscriber)
        while not subscriber.queue.empty():
            subscriber.queue.get_nowait()
        subscriber.queue.put_nowait(_DROPPED)

    def missed_since(self, last_event_id: int) -> list[StreamEvent] | None:
        """The buffered events after `last_event_id`, or None if some may be missing."""
        if self._floor is None or last_event_id < self._floor:
            return None
        if last_event_id > self._history[-1].id:
            return None  # an id from before a restart, or from another database
        return [e for e in self._history if e.id > last_event_id]

    async def subscribe(
        self,
        snapshot: SnapshotFn,
        *,
        last_event_id: int | None = None,
        ping_interval: float = PING_INTERVAL_SECONDS,
    ) -> AsyncIterator[ServerSentEvent]:
        """The events for one browser: a snapshot or the missed events, then live ones.

        A comment ping goes out after `ping_interval` seconds without an event, so Caddy
        and browsers keep the connection open. Ends when the subscriber is dropped.
        """
        # Subscribe before reading anything, so nothing published meanwhile is lost.
        subscriber = _Subscriber(queue=asyncio.Queue(maxsize=self._queue_size))
        self._subscribers.add(subscriber)
        try:
            sent_up_to: int | None = None
            missed = None if last_event_id is None else self.missed_since(last_event_id)
            if missed is None:
                snapshot_id = self.last_id
                data = redact(await snapshot())
                yield StreamEvent("snapshot", data, snapshot_id).to_sse()
            else:
                for event in missed:
                    yield event.to_sse()
                sent_up_to = missed[-1].id if missed else last_event_id

            while True:
                try:
                    item = await asyncio.wait_for(subscriber.queue.get(), ping_interval)
                except TimeoutError:
                    yield PING
                    continue
                if item is _DROPPED:
                    return
                if sent_up_to is not None and item.id is not None and item.id <= sent_up_to:
                    continue  # already sent from the history
                yield item.to_sse()
        finally:
            self._subscribers.discard(subscriber)
