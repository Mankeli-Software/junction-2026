"""The LISTEN listener. The NOTIFY tests need Postgres and run only with DATABASE_URL.

They use a channel of their own and no tables, so they can use the development database.
"""

import asyncio
import os
import uuid

import psycopg
import pytest

from app.services.dashboard.listener import PgListener, libpq_url


def test_libpq_url_drops_the_sqlalchemy_driver():
    assert libpq_url("postgresql+psycopg://u:p@h:5432/db?sslmode=require") == (
        "postgresql://u:p@h:5432/db?sslmode=require"
    )
    assert libpq_url("postgresql://u@h/db") == "postgresql://u@h/db"


class _FakeConn:
    def __init__(self, payloads):
        self.payloads = payloads
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, query):
        self.executed.append(query)

    async def notifies(self):
        for payload in self.payloads:
            yield type("Notify", (), {"payload": payload})()
        raise psycopg.OperationalError("server closed the connection")


async def test_reconnects_with_back_off_and_keeps_going_after_a_bad_callback():
    attempts = []
    sixth_attempt = asyncio.Event()
    conns = [_FakeConn(["1", "boom", "2"]), _FakeConn(["3"])]

    async def connect(dsn, autocommit):
        attempts.append(dsn)
        if len(attempts) == 6:
            sixth_attempt.set()
        if len(attempts) in (1, 2, 4):
            raise psycopg.OperationalError("connection refused")
        if not conns:
            await asyncio.Event().wait()  # stay down until cancelled
        return conns.pop(0)

    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    got = []
    connected = []

    def callback(payload):
        if payload == "boom":
            raise ValueError(payload)
        got.append(payload)

    listener = PgListener(
        "status_events",
        callback,
        dsn="postgresql+psycopg://u@h/db",
        on_connect=lambda: connected.append(True),
        min_backoff=1,
        max_backoff=4,
        connect=connect,
        sleep=sleep,
    )
    task = listener.start()
    async with asyncio.timeout(1):
        await sixth_attempt.wait()
    await listener.stop()
    assert task.done()

    assert attempts[0] == "postgresql://u@h/db"
    assert got == ["1", "2", "3"]
    assert listener.connections == 2 and connected == [True, True]
    # Refused, refused, up (reset), lost, refused, up (reset), lost.
    assert sleeps == [1, 2, 1, 2, 1]
    assert not listener.listening.is_set()


@pytest.fixture
def database_url():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    return libpq_url(os.environ["DATABASE_URL"])


async def _notify(dsn: str, channel: str, payload: str) -> None:
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute("SELECT pg_notify(%s, %s)", (channel, payload))


async def test_receives_a_real_notify_and_reconnects_after_the_connection_drops(database_url):
    channel = f"dashboard_test_{uuid.uuid4().hex[:8]}"
    received: asyncio.Queue[str] = asyncio.Queue()

    async def callback(payload: str) -> None:
        await received.put(payload)

    reconnected = asyncio.Event()

    def on_connect() -> None:
        if listener.connections == 2:
            reconnected.set()

    listener = PgListener(
        channel, callback, dsn=database_url, on_connect=on_connect, min_backoff=0.05
    )
    listener.start()
    try:
        async with asyncio.timeout(5):
            await listener.listening.wait()
            await _notify(database_url, channel, "1201")
            assert await received.get() == "1201"

            # Kill the listener's backend, as a restart or network drop would.
            async with await psycopg.AsyncConnection.connect(
                database_url, autocommit=True
            ) as admin:
                cur = await admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE query ILIKE %s AND pid <> pg_backend_pid()",
                    (f'LISTEN "{channel}"%',),
                )
                assert (await cur.fetchone()) == (True,)

            await reconnected.wait()
            await _notify(database_url, channel, "1202")
            assert await received.get() == "1202"
    finally:
        await listener.stop()
