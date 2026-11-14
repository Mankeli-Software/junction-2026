"""Locks: the audit lock is taken only at commit, briefly (#86), and the confirmation page
and the agent's tools take rows in one order, so they never deadlock (#87). On a real
Postgres.

Tool calls commit for real here (`app_db`), as they do in the app. Skipped without
DATABASE_URL.
"""

import asyncio
import time

import pytest
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.adapters import valio
from app.interfaces.deps import DEV_CALLER
from app.interfaces.tool_calls import run_tool
from app.models import AuditEvent
from app.schemas import AuditEventType
from app.services import audit
from app.services.errors import ServiceError
from tests.test_confirmation_page import LINES, STOCK_FLAG, Page, ordered

SLOW_S = 2.0

WEB = DEV_CALLER
CONNECTOR = DEV_CALLER.model_copy(update={"channel": "connector"})  # a session of its own


class Done(BaseModel):
    ok: bool = True


async def quick(db: AsyncSession, caller) -> Done:
    return Done()


@pytest.mark.usefixtures("dev_caller")
async def test_a_slow_tool_call_does_not_block_another_session(app_db: AsyncEngine):
    # Both sessions and the demo rows exist first, so the two calls share no row locks.
    await run_tool("get_order_status", WEB, quick, None)
    await run_tool("get_order_status", CONNECTOR, quick, None)

    started = asyncio.Event()

    async def slow(db: AsyncSession, caller) -> Done:  # a live Valio call, say
        started.set()
        await asyncio.sleep(SLOW_S)
        return Done()

    slow_call = asyncio.create_task(run_tool("build_quote", WEB, slow, None))
    await asyncio.wait_for(started.wait(), timeout=5)
    began = time.monotonic()
    await run_tool("get_order_status", CONNECTOR, quick, None)
    waited = time.monotonic() - began
    await slow_call

    assert waited < SLOW_S / 2, f"the quick call waited {waited:.2f} s behind the slow one"

    async with AsyncSession(app_db) as db:
        assert (await audit.check_chain(db)).ok
        # The pointers follow the chain, which follows commit order: the quick call's
        # events come before the slow call's, though the slow call started first.
        rows = (
            await db.execute(
                text(
                    "SELECT s.audit_seq, a.type, a.payload->>'tool' AS tool FROM status_events s "
                    "JOIN audit_events a ON a.seq = s.audit_seq ORDER BY s.id"
                )
            )
        ).all()
        assert [r.audit_seq for r in rows] == sorted(r.audit_seq for r in rows)
        assert [(r.type, r.tool) for r in rows[-4:]] == [
            ("tool_called", "get_order_status"),
            ("tool_returned", "get_order_status"),
            ("tool_called", "build_quote"),
            ("tool_returned", "build_quote"),
        ]


@pytest.mark.usefixtures("dev_caller")
async def test_a_failed_service_leaves_none_of_its_events(app_db: AsyncEngine):
    async def failing(db: AsyncSession, caller) -> Done:
        await audit.record(db, type=AuditEventType.buyer_said, actor="buyer", payload={"text": "x"})
        raise ServiceError("no such quote")

    with pytest.raises(ServiceError):
        await run_tool("get_order_status", WEB, failing, None)

    async with AsyncSession(app_db) as db:
        types = list(await db.scalars(select(AuditEvent.type).order_by(AuditEvent.seq)))
        assert types == ["session_started", "tool_called", "tool_returned"]
        assert (await audit.check_chain(db)).ok


# --- The confirmation page against the agent (#87) ---------------------------------------


def slow_first_valio_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first Valio lookup sleeps, like a live call on the VM, holding its row locks."""
    real = valio.get_offers
    calls = 0

    async def slow(ids, needed_by):
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(1.5)
        return await real(ids, needed_by)

    monkeypatch.setattr(valio, "get_offers", slow)


async def race(first, second):
    """Run `first`, then `second` while `first` sleeps in Valio. Requests run in threads,
    as TestClient's are blocking."""
    one = asyncio.create_task(asyncio.to_thread(first))
    await asyncio.sleep(0.5)
    two = asyncio.create_task(asyncio.to_thread(second))
    return await one, await two


def confirmable() -> tuple[object, dict, Page, dict]:
    browser, quote, token = ordered()
    page = Page(token)
    view = page.view()
    assert page.ack(view["quote"]["quote_hash"], STOCK_FLAG).status_code == 204
    return browser, quote, page, page.view()


@pytest.mark.usefixtures("no_caller")
async def test_confirm_and_update_quote_on_the_same_quote_dont_deadlock(app_db, monkeypatch):
    browser, quote, page, view = confirmable()
    slow_first_valio_call(monkeypatch)  # Confirm's availability re-check

    confirmed, updated = await race(
        lambda: page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]}),
        lambda: browser.post(f"/api/v1/quotes/{quote['quote_id']}/update", json={"lines": LINES}),
    )

    assert confirmed.status_code == 200, confirmed.text
    # The agent waited for Confirm and then found the quote confirmed.
    assert updated.status_code == 409, updated.text


@pytest.mark.usefixtures("no_caller")
async def test_update_quote_then_confirm_on_the_same_quote_dont_deadlock(app_db, monkeypatch):
    browser, quote, page, view = confirmable()
    slow_first_valio_call(monkeypatch)  # update_quote's offers for the new quote

    updated, confirmed = await race(
        lambda: browser.post(f"/api/v1/quotes/{quote['quote_id']}/update", json={"lines": LINES}),
        lambda: page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]}),
    )

    assert updated.status_code == 200, updated.text
    # Confirm waited for the update and then refused the quote it had replaced.
    assert confirmed.status_code == 409, confirmed.text


@pytest.mark.usefixtures("no_caller")
async def test_confirm_and_get_order_status_dont_deadlock(app_db, monkeypatch):
    browser, quote, page, view = confirmable()
    slow_first_valio_call(monkeypatch)

    confirmed, status = await race(
        lambda: page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]}),
        lambda: browser.get(f"/api/v1/quotes/{quote['quote_id']}/status"),
    )

    assert confirmed.status_code == 200, confirmed.text
    assert status.status_code == 200, status.text
