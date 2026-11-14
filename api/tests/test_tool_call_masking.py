"""Personal data a buyer types into a tool call is masked, not refused (#90).

Over REST and MCP, committed for real (`app_db`). Skipped without DATABASE_URL.
"""

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import engine
from app.interfaces.mcp.server import mcp
from app.interfaces.tool_calls import _masked
from app.main import app
from app.models import AuditEvent
from app.schemas import BuildQuoteRequest, EngineInput, SearchProductsRequest
from app.services.audit import load_rule_set_by_ref

pytestmark = pytest.mark.usefixtures("app_db", "dev_caller")

TYPED = "maito, soita +358 40 123 4567 tai jane.doe@example.com, linkki simo.mankeli.co/c/abc123"
MASKED = "maito, soita +358 40 *** **67 tai j***@example.com, linkki simo.mankeli.co/c/…"
LINE = {"line_id": "l1", "text": TYPED, "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


async def all_events(engine_: AsyncEngine) -> list[AuditEvent]:
    async with AsyncSession(engine_) as db:
        return list(await db.scalars(select(AuditEvent).order_by(AuditEvent.seq)))


def assert_nothing_typed_is_stored(events: list[AuditEvent]) -> None:
    stored = str([(e.payload, e.text_fi, e.text_en) for e in events])
    for secret in ("123 4567", "jane.doe", "abc123"):
        assert secret not in stored


async def test_a_rest_build_quote_with_a_phone_number_and_an_email_succeeds(app_db: AsyncEngine):
    response = TestClient(app).post("/api/v1/quotes", json={"lines": [LINE]})

    assert response.status_code == 200, response.text
    assert response.json()["lines"][0]["asked"]["text"] == MASKED
    events = await all_events(app_db)
    called = next(e for e in events if e.type == "tool_called")
    assert called.payload["arguments"]["lines"][0]["text"] == MASKED
    assert_nothing_typed_is_stored(events)

    # The engine saw the masked text too, so the quote replays exactly from its event.
    built = next(e for e in events if e.type == "quote_built")
    async with AsyncSession(app_db) as db:
        rules = await load_rule_set_by_ref(db, built.payload["rules_ref"])
    replayed = EngineInput.model_validate({**built.payload["engine_input"], "rules": rules})
    assert engine.decide(replayed).model_dump(mode="json") == built.payload["engine_output"]


async def test_an_mcp_tool_call_with_personal_data_succeeds(app_db: AsyncEngine):
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("search_products", {"q": TYPED})

    assert not result.isError, result.content
    called = next(e for e in await all_events(app_db) if e.type == "tool_called")
    assert called.payload["arguments"]["q"] == MASKED
    assert_nothing_typed_is_stored(await all_events(app_db))


def test_a_request_without_personal_data_is_passed_on_as_it_is():
    request = BuildQuoteRequest.model_validate({"lines": [{**LINE, "text": "maito"}]})
    assert _masked(request) is request
    assert _masked(None) is None
    masked = _masked(SearchProductsRequest(q=TYPED))
    assert isinstance(masked, SearchProductsRequest) and masked.q == MASKED
