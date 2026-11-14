"""Correlation, tool spans and test-run tags for Application Insights (#84).

Spans go to an in-memory exporter on an SDK tracer provider, so these check what would be
exported, not just what was configured. The provider is set once for the test process.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import telemetry
from app.interfaces.tool_calls import _outcome, run_tool
from app.main import app
from app.services.errors import ServiceError
from tests.conftest import write_audit
from tests.phones import new_number

SPANS = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def tracer_provider():
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(telemetry.ContextSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(SPANS))
    yield


@pytest.fixture(autouse=True)
def clear_spans():
    SPANS.clear()


def _spans(name_start: str) -> list:
    return [s for s in SPANS.get_finished_spans() if s.name.startswith(name_start)]


def test_bound_attributes_reach_every_span_inside():
    with telemetry.bound(session_id="s-1", test_run="run-7"):
        with telemetry.span("outer"):
            with telemetry.span("inner"):
                pass
    (inner,) = _spans("inner")
    assert inner.attributes["simo.session_id"] == "s-1"
    assert inner.attributes["simo.test_run"] == "run-7"
    with telemetry.span("after"):
        pass
    assert "simo.session_id" not in _spans("after")[0].attributes


def test_log_records_carry_the_bound_attributes():
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(telemetry.ContextLogProcessor())
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    logger = logging.getLogger("test.telemetry.logs")
    handler = LoggingHandler(logger_provider=provider)
    logger.addHandler(handler)
    try:
        with telemetry.bound(session_id="s-2", call_id="c-9"):
            logger.warning("something happened")
    finally:
        logger.removeHandler(handler)
    (record,) = exporter.get_finished_logs()
    attributes = record.log_record.attributes
    assert attributes["simo.session_id"] == "s-2" and attributes["simo.call_id"] == "c-9"


@pytest.mark.parametrize(
    ("response", "outcome"),
    [
        ({"results": []}, "empty"),
        ({"results": [{"id": 1}]}, "ok"),
        ({"decision": "ready", "lines": [{}], "flags": []}, "ready"),
        ({"decision": "rejected", "lines": [], "rejections": [{}]}, "rejected"),
        ({"company_name": "X Oy"}, "ok"),
    ],
)
def test_tool_outcome(response, outcome):
    assert _outcome(response)[0] == outcome


@pytest.mark.usefixtures("app_db", "dev_caller")
def test_a_rest_tool_call_is_one_span_with_its_session_outcome_and_test_run():
    client = TestClient(app)

    response = client.get(
        "/api/v1/recipes",
        params={"q": "qxzqxz"},
        headers={"X-Simo-Test-Run": "perf-1", "X-Simo-Test-Case": "soup-1"},
    )

    assert response.status_code == 200
    (tool,) = _spans("tool search_recipes")
    attributes = tool.attributes
    assert attributes["simo.tool"] == "search_recipes"
    assert attributes["simo.test_run"] == "perf-1" and attributes["simo.test_case"] == "soup-1"
    assert attributes["simo.session_id"] and attributes["simo.channel"] == "web"
    assert attributes["simo.outcome"] == "empty"  # no recipe matches the word (#34)
    assert '"qxzqxz"' in attributes["simo.arguments"]


@pytest.mark.usefixtures("app_db", "dev_caller")
async def test_a_tool_error_marks_its_span_failed():
    from app.interfaces.deps import DEV_CALLER

    async def failing(db, caller):
        raise ServiceError("no such quote")

    with pytest.raises(ServiceError):
        await run_tool("get_order_status", DEV_CALLER, failing, None)

    (tool,) = _spans("tool get_order_status")
    assert tool.status.status_code == trace.StatusCode.ERROR
    assert tool.attributes["simo.outcome"] == "error"
    assert "no such quote" in tool.attributes["simo.error"]


async def test_quote_rejection_events_are_complete_and_redacted(caplog, monkeypatch):
    from app.interfaces.deps import DEV_CALLER
    from app.schemas.common import Decision, Localized, QuoteStatus
    from app.schemas.quote import Rejection
    from app.schemas.tools import QuoteResponse
    from app.services.dashboard.redact import redact

    long_line_id = "line-" + "x" * 512
    line_ids = [
        "jane.doe@example.com",
        "+358 40 123 4567",
        "https://simo.mankeli.co/c/secret",
        long_line_id,
    ]
    line_ids.extend(f"line-{index}" for index in range(66))
    rejections = [
        Rejection(
            line_id=line_id,
            reason_code="INPUT_INVALID" if index % 2 == 0 else "NO_CANDIDATES",
            text=Localized(
                fi="Contact jane.doe@example.com at +358 40 123 4567 /c/secret",
                en="Contact jane.doe@example.com at +358 40 123 4567 /c/secret",
            ),
            next_step=Localized(fi="Ask again", en="Ask again"),
        )
        for index, line_id in enumerate(line_ids)
    ]
    response = QuoteResponse(
        decision=Decision.rejected,
        lines=[],
        groups=[],
        flags=[],
        clarification=None,
        rejections=rejections,
        not_ordered=[],
        total_cents=0,
        delivery=None,
        speak=Localized(fi="Korjaa tilaus", en="Fix the order"),
        rules_ref="test",
        quote_id="quote-123",
        version=1,
        parent_quote_id=None,
        status=QuoteStatus.rejected,
        expires_at=None,
        quote_hash=None,
    )

    async def fake_run(name, caller, service, request, arguments):
        return response

    monkeypatch.setattr("app.interfaces.tool_calls._run", fake_run)
    caplog.set_level(logging.INFO, logger="simo.events")

    await run_tool("update_quote", DEV_CALLER, lambda *_: response, None)

    events = [record for record in caplog.records if record.getMessage() == "quote line rejected"]
    assert len(events) == len(rejections)
    by_line_id = {record.__dict__["simo.line_id"]: record for record in events}
    assert by_line_id["line-65"].__dict__["simo.reason_code"] == "NO_CANDIDATES"
    assert "j***@example.com" in by_line_id
    assert redact("+358 40 123 4567") in by_line_id
    assert "https://simo.mankeli.co/c/…" in by_line_id
    assert long_line_id[:200] in by_line_id
    assert long_line_id not in by_line_id

    exported = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "jane.doe@example.com" not in exported
    assert "+358 40 123 4567" not in exported
    assert "/c/secret" not in exported
    assert long_line_id not in exported
    assert "Ask again" not in exported
    assert "Contact" not in exported


async def test_every_audit_event_is_mirrored_as_a_log_line(db, caplog):
    from app.schemas import Localized
    from app.services import audit

    caplog.set_level(logging.INFO, logger="simo.events")
    await audit.record(
        db,
        type="agent_said",
        actor="agent",
        payload={"text": "Tilaan maitoa.", "transcript": True},
        text=Localized(fi="Tilaan maitoa.", en="Tilaan maitoa."),
    )
    (event,) = await write_audit(db)  # at commit in the app (#86)

    (line,) = [r for r in caplog.records if r.getMessage() == "audit agent_said"]
    assert line.__dict__["simo.seq"] == str(event.seq)
    assert line.__dict__["simo.text"] == "Tilaan maitoa."
    assert "simo.payload" not in line.__dict__


@pytest.mark.usefixtures("app_db", "no_caller")
def test_a_confirmation_flow_exports_no_token_and_no_full_phone_number(caplog):
    # Part G of #84: run the whole flow with spans going to the in-memory exporter and every
    # log line captured, then search them all for the secrets.

    from app.observability import quiet_http_clients

    quiet_http_clients()  # as setup_observability() does on the VM
    caplog.set_level(logging.DEBUG)
    phone = new_number()
    client = TestClient(app)
    created = client.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": "en"}
    )
    assert created.status_code == 201, created.text
    line = {
        "line_id": "l1",
        "text": "maito",
        "quantity": 20,
        "unit": "l",
        "needed_by": "2026-11-16",
    }
    quote = client.post("/api/v1/quotes", json={"lines": [line]}).json()
    sent = client.post(f"/api/v1/quotes/{quote['quote_id']}/confirmation-request")
    assert sent.status_code == 200, sent.text
    [message] = client.get("/api/v1/private/inbox").json()
    token = message["link"].split("/c/", 1)[1]
    assert client.get(f"/api/v1/confirmations/{token}").status_code == 200

    exported = " ".join(
        f"{s.name} {dict(s.attributes)}" for s in SPANS.get_finished_spans()
    ) + " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert token not in exported
    assert phone not in exported and phone[1:] not in exported
    assert "tool request_confirmation" in exported  # the flow was really traced
