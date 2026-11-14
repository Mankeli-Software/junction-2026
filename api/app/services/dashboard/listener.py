"""`LISTEN` on a Postgres channel for the dashboard stream (#49, technical-plan.md §8.6).

The listener holds its own connection, outside SQLAlchemy's pool, straight to Postgres on
port 5432: PgBouncer in transaction mode drops notifications (§10.1). It reconnects with
back-off when the connection drops. Notifications sent while it was down are lost, so
`on_connect` runs after every (re)connect for the caller to catch up from the table.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
from psycopg import sql

from app.settings import get_settings

log = logging.getLogger(__name__)

Callback = Callable[[str], Awaitable[None] | None]
Hook = Callable[[], Awaitable[None] | None]


def libpq_url(url: str) -> str:
    """`postgresql+psycopg://...` (SQLAlchemy's form) -> `postgresql://...` for psycopg."""
    scheme, sep, rest = url.partition("://")
    return f"{scheme.split('+', 1)[0]}{sep}{rest}"


async def _call(fn: Callable[..., Any], *args: Any) -> None:
    result = fn(*args)
    if inspect.isawaitable(result):
        await result


class PgListener:
    """Runs `LISTEN <channel>` and hands each notification's payload to `callback`.

    A failing callback is logged and does not stop the listener.
    """

    def __init__(
        self,
        channel: str,
        callback: Callback,
        *,
        dsn: str | None = None,
        on_connect: Hook | None = None,
        min_backoff: float = 0.5,
        max_backoff: float = 30.0,
        connect: Callable[..., Awaitable[Any]] = psycopg.AsyncConnection.connect,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.channel = channel
        self.callback = callback
        self.dsn = libpq_url(dsn or get_settings().database_url)
        self.on_connect = on_connect
        self.min_backoff = min_backoff
        self.max_backoff = max_backoff
        self._connect = connect
        self._sleep = sleep
        self._task: asyncio.Task | None = None
        self.connections = 0  # successful (re)connects, for health checks and tests
        self.listening = asyncio.Event()  # set while LISTEN is active

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name=f"pg-listen-{self.channel}")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run(self) -> None:
        """Listen until cancelled, reconnecting with back-off."""
        backoff = self.min_backoff
        while True:
            try:
                conn = await self._connect(self.dsn, autocommit=True)
            except (psycopg.OperationalError, OSError) as error:
                log.warning(
                    "LISTEN %s: connect failed (%s), retry in %.1fs", self.channel, error, backoff
                )
                await self._sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)
                continue
            try:
                async with conn:
                    await conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self.channel)))
                    self.connections += 1
                    self.listening.set()
                    backoff = self.min_backoff
                    if self.on_connect is not None:
                        await self._safely(self.on_connect)
                    async for notify in conn.notifies():
                        await self._safely(self.callback, notify.payload)
            except (psycopg.OperationalError, OSError) as error:
                log.warning("LISTEN %s: connection lost (%s), reconnecting", self.channel, error)
            finally:
                self.listening.clear()
            await self._sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)

    async def _safely(self, fn: Callable[..., Any], *args: Any) -> None:
        try:
            await _call(fn, *args)
        except Exception:
            log.exception("LISTEN %s: handler failed", self.channel)
