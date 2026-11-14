"""The dashboard stream's fan-out, without a database."""

import asyncio
import json

import pytest

from app.services.dashboard.stream import Broadcaster, StreamEvent

EMPTY = {"business_now": "2026-11-12T09:00:00+02:00", "totals": {}, "companies": []}


async def snapshot():
    return EMPTY


def step(seq: int, **data) -> StreamEvent:
    return StreamEvent("step", {"session_id": "s_1", "step": {"seq": seq, **data}}, seq)


async def take(stream, n: int):
    async with asyncio.timeout(1):
        return [await anext(stream) for _ in range(n)]


def parsed(sse):
    return sse.event, (None if sse.id is None else int(sse.id)), json.loads(sse.data)


async def test_sends_a_snapshot_then_live_events():
    hub = Broadcaster()
    stream = hub.subscribe(snapshot)
    [first] = await take(stream, 1)
    assert parsed(first) == ("snapshot", None, EMPTY)
    assert hub.subscriber_count == 1

    hub.publish(step(1))
    hub.publish(StreamEvent("transcript", {"session_id": "s_1", "line": {"text": "hei"}}))
    events = [parsed(e) for e in await take(stream, 2)]
    assert events == [
        ("step", 1, {"session_id": "s_1", "step": {"seq": 1}}),
        ("transcript", None, {"session_id": "s_1", "line": {"text": "hei"}}),
    ]
    await stream.aclose()
    assert hub.subscriber_count == 0


async def test_every_subscriber_gets_every_event():
    hub = Broadcaster()
    streams = [hub.subscribe(snapshot) for _ in range(3)]
    for s in streams:
        await take(s, 1)
    hub.publish(step(7))
    for s in streams:
        [event] = await take(s, 1)
        assert parsed(event)[1] == 7
        await s.aclose()


async def test_snapshot_carries_the_latest_id_so_a_reconnect_resumes_from_it():
    hub = Broadcaster()
    hub.publish(step(4))
    stream = hub.subscribe(snapshot)
    [first] = await take(stream, 1)
    assert first.event == "snapshot" and first.id == "4"
    await stream.aclose()


async def test_redacts_published_events_and_the_snapshot():
    hub = Broadcaster()

    async def leaky_snapshot():
        return {"identity": "+358401234512", "token": "t"}

    stream = hub.subscribe(leaky_snapshot)
    [first] = await take(stream, 1)
    assert json.loads(first.data) == {"identity": "+358 40 *** **12"}

    hub.publish(StreamEvent("step", {"link": "https://x/c/abc", "text": "see /c/abc"}, 1))
    [event] = await take(stream, 1)
    assert json.loads(event.data) == {"text": "see /c/…"}
    await stream.aclose()


async def test_reconnect_with_last_event_id_gets_the_missed_events_then_live_ones():
    hub = Broadcaster()
    for seq in range(1, 6):
        hub.publish(step(seq))

    async def no_snapshot():
        raise AssertionError("a resumable reconnect must not need a snapshot")

    stream = hub.subscribe(no_snapshot, last_event_id=2)
    assert [parsed(e)[1] for e in await take(stream, 3)] == [3, 4, 5]
    hub.publish(step(6))
    assert [parsed(e)[1] for e in await take(stream, 1)] == [6]
    await stream.aclose()


async def test_reconnect_that_is_up_to_date_waits_for_live_events():
    hub = Broadcaster()
    hub.publish(step(1))
    stream = hub.subscribe(snapshot, last_event_id=1, ping_interval=60)
    pending = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.01)
    assert not pending.done()
    hub.publish(step(2))
    assert parsed(await asyncio.wait_for(pending, 1))[1] == 2
    await stream.aclose()


@pytest.mark.parametrize("last_event_id", [0, 2, 99])
async def test_reconnect_gets_a_snapshot_when_the_history_may_have_a_gap(last_event_id):
    hub = Broadcaster(history_size=3)
    for seq in range(3, 9):  # this process started at seq 3; 6, 7 and 8 are kept
        hub.publish(step(seq))
    stream = hub.subscribe(snapshot, last_event_id=last_event_id)
    [first] = await take(stream, 1)
    assert first.event == "snapshot"
    assert first.id == "8"
    await stream.aclose()


async def test_reconnect_just_inside_the_history_resumes():
    hub = Broadcaster(history_size=3)
    for seq in range(3, 9):
        hub.publish(step(seq))  # kept: 6, 7, 8; evicted up to 5
    stream = hub.subscribe(snapshot, last_event_id=5)
    assert [parsed(e)[1] for e in await take(stream, 3)] == [6, 7, 8]
    await stream.aclose()


async def test_reconnect_to_a_fresh_process_gets_a_snapshot():
    hub = Broadcaster()
    stream = hub.subscribe(snapshot, last_event_id=41)
    [first] = await take(stream, 1)
    assert first.event == "snapshot"
    await stream.aclose()


async def test_an_event_published_while_the_snapshot_loads_is_not_lost():
    hub = Broadcaster()
    gate = asyncio.Event()

    async def slow_snapshot():
        await gate.wait()
        return EMPTY

    stream = hub.subscribe(slow_snapshot)
    first = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.01)
    hub.publish(step(1))
    gate.set()
    assert (await asyncio.wait_for(first, 1)).event == "snapshot"
    assert [parsed(e)[1] for e in await take(stream, 1)] == [1]
    await stream.aclose()


async def test_pings_when_nothing_happens():
    hub = Broadcaster()
    stream = hub.subscribe(snapshot, ping_interval=0.01)
    await take(stream, 1)
    pings = await take(stream, 2)
    assert all(p.comment == "ping" and p.event is None for p in pings)
    assert pings[0].encode() == b": ping\r\n\r\n"
    await stream.aclose()


async def test_a_subscriber_with_a_full_queue_is_dropped_and_others_keep_going():
    hub = Broadcaster(queue_size=3)
    slow = hub.subscribe(snapshot)
    fast = hub.subscribe(snapshot)
    await take(slow, 1)
    await take(fast, 1)

    for seq in range(1, 4):
        hub.publish(step(seq))
        await take(fast, 1)
    assert hub.subscriber_count == 2
    hub.publish(step(4))  # slow's queue already holds 3
    assert hub.subscriber_count == 1
    assert [parsed(e)[1] for e in await take(fast, 1)] == [4]

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(slow), 1)
    await fast.aclose()


async def test_publish_without_subscribers_only_fills_the_history():
    hub = Broadcaster(history_size=2)
    hub.publish(step(1))
    hub.publish(StreamEvent("transcript", {"line": {}}))  # no id: not kept
    hub.publish(step(2))
    hub.publish(step(3))
    assert hub.last_id == 3
    assert [e.id for e in hub.missed_since(1)] == [2, 3]
    assert hub.missed_since(0) is None
