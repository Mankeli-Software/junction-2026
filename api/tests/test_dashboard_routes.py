"""`GET /api/v1/public/stream`, driven through the ASGI app (httpx buffers whole bodies).

No database here: the snapshot is an empty overview. The database-backed endpoints and the
listener are in `test_dashboard_api.py`.
"""

import asyncio
import json

import pytest

from app.interfaces.rest import dashboard as rest_dashboard
from app.main import app
from app.schemas import Channel, OverviewResponse, Totals
from app.services.dashboard.stream import Broadcaster, StreamEvent, get_broadcaster
from app.services.policy import get_rule_set


async def _empty_overview(state, channel, since) -> OverviewResponse:
    return OverviewResponse(
        business_now=get_rule_set().policy.business_time,
        totals=Totals(
            active=0,
            waiting=0,
            confirmed=0,
            attention=0,
            confirmed_cents=0,
            by_channel=dict.fromkeys(Channel, 0),
        ),
        companies=[],
    )


@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setattr(rest_dashboard, "current_overview", _empty_overview)
    hub = Broadcaster()
    app.dependency_overrides[get_broadcaster] = lambda: hub
    yield hub
    app.dependency_overrides.pop(get_broadcaster, None)


class Stream:
    """One open request to the app; `next_event()` reads one SSE message."""

    def __init__(self, path: str, query: str = "", headers: dict[str, str] | None = None):
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"test")]
            + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("test", 1),
            "server": ("test", 80),
        }
        self.messages: asyncio.Queue = asyncio.Queue()
        self.closed = asyncio.Event()
        self.buffer = b""

    async def __aenter__(self):
        async def receive():
            await self.closed.wait()
            return {"type": "http.disconnect"}

        self.task = asyncio.create_task(app(self.scope, receive, self.messages.put))
        async with asyncio.timeout(2):
            self.start = await self.messages.get()
        return self

    async def __aexit__(self, *exc):
        self.closed.set()
        async with asyncio.timeout(2):
            await self.task

    async def next_event(self) -> dict[str, str]:
        async with asyncio.timeout(2):
            while b"\r\n\r\n" not in self.buffer:
                message = await self.messages.get()
                self.buffer += message.get("body", b"")
        raw, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        fields = {}
        for line in raw.decode().split("\r\n"):
            key, _, value = line.partition(": ")
            fields[key] = value
        return fields


async def test_stream_sends_an_empty_snapshot_then_live_events(hub):
    async with Stream("/api/v1/public/stream", "state=active&channel=phone") as s:
        assert s.start["status"] == 200
        headers = dict(s.start["headers"])
        assert headers[b"content-type"].startswith(b"text/event-stream")

        first = await s.next_event()
        assert first["event"] == "snapshot"
        snapshot = json.loads(first["data"])
        assert snapshot["companies"] == []
        assert snapshot["totals"]["by_channel"] == {
            "phone": 0,
            "web_chat": 0,
            "webmcp": 0,
            "mcp": 0,
        }
        assert snapshot["business_now"] == "2026-11-12T09:00:00+02:00"

        hub.publish(StreamEvent("step", {"session_id": "s_1", "note": "to +358401234512"}, 7))
        event = await s.next_event()
        assert event["event"] == "step" and event["id"] == "7"
        assert json.loads(event["data"]) == {"session_id": "s_1", "note": "to +358 40 *** **12"}
    assert hub.subscriber_count == 0


async def test_stream_resumes_from_last_event_id(hub):
    for seq in (1, 2, 3):
        hub.publish(StreamEvent("step", {"seq": seq}, seq))
    async with Stream("/api/v1/public/stream", headers={"Last-Event-ID": "2"}) as s:
        assert [(await s.next_event())["id"] for _ in range(2)] == ["2", "3"]


async def test_stream_rejects_an_unknown_filter(hub):
    async with Stream("/api/v1/public/stream", "state=bogus") as s:
        assert s.start["status"] == 422


def test_stream_is_in_the_openapi_document():
    assert "/api/v1/public/stream" in app.openapi()["paths"]
