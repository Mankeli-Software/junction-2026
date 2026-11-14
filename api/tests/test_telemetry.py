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
        params={"q": "hernekeitto"},
        headers={"X-Simo-Test-Run": "perf-1", "X-Simo-Test-Case": "soup-1"},
    )

    assert response.status_code == 200
    (tool,) = _spans("tool search_recipes")
    attributes = tool.attributes
    assert attributes["simo.tool"] == "search_recipes"
    assert attributes["simo.test_run"] == "perf-1" and attributes["simo.test_case"] == "soup-1"
    assert attributes["simo.session_id"] and attributes["simo.channel"] == "web"
    assert attributes["simo.outcome"] == "empty"  # the fixture recipes have no soup
    assert '"hernekeitto"' in attributes["simo.arguments"]


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
