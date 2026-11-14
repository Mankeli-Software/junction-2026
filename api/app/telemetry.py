"""Correlation, spans, events and metrics for Application Insights (#84).

Every span and every log record carries the ids of the call it belongs to, as `simo.*`
attributes: session, call, quote, channel, client, company, tool and, for performance tests,
the test run and test case (`X-Simo-Test-Run`, `X-Simo-Test-Case`). They live in a context
variable, set with `bound(...)` where a call, request or tool call starts; the processors
below copy them onto each span when it starts and onto each log record when it is emitted.

Without a connection string nothing is exported (`observability.py`), and these helpers
are cheap no-ops against OpenTelemetry's default providers.
"""

import json
import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import metrics, propagate, trace
from opentelemetry.sdk._logs import LogRecordProcessor, ReadWriteLogRecord
from opentelemetry.sdk.trace import Span, SpanProcessor
from opentelemetry.trace import Status, StatusCode

PREFIX = "simo."
# Headers a performance test sets on its MCP or REST requests (#84).
TEST_RUN_HEADER = "x-simo-test-run"
TEST_CASE_HEADER = "x-simo-test-case"
# Long values (arguments, results, transcripts) are cut to this many characters.
MAX_VALUE = 4000

_EMPTY: Mapping[str, str] = MappingProxyType({})
_context: ContextVar[Mapping[str, str]] = ContextVar("simo_telemetry", default=_EMPTY)
_tracer = trace.get_tracer("simo")
_meter = metrics.get_meter("simo")
events = logging.getLogger("simo.events")


def _clean(attrs: Mapping[str, Any]) -> dict[str, str]:
    out = {}
    for key, value in attrs.items():
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        out[key if key.startswith(PREFIX) else PREFIX + key] = text[:MAX_VALUE]
    return out


def current() -> Mapping[str, str]:
    return _context.get()


@contextmanager
def bound(**attrs: Any) -> Iterator[None]:
    """Add correlation attributes for everything inside: spans started and log records
    emitted from here on, and the current span."""
    added = _clean(attrs)
    token = _context.set({**_context.get(), **added})
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(added)
    try:
        yield
    finally:
        _context.reset(token)


def annotate(**attrs: Any) -> None:
    """Set attributes on the current span only (results learned on the way)."""
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(_clean(attrs))


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[trace.Span]:
    """A span for one step; an exception marks it failed and is recorded on it."""
    with _tracer.start_as_current_span(
        name, attributes=_clean(attrs), record_exception=True, set_status_on_exception=True
    ) as current_span:
        yield current_span


def failed(description: str) -> None:
    """Mark the current span failed without an exception (a tool error answered with 200)."""
    span_ = trace.get_current_span()
    if span_.is_recording():
        span_.set_status(Status(StatusCode.ERROR, description[:200]))


def event(name: str, level: int = logging.INFO, **attrs: Any) -> None:
    """One structured log line: `name` is the message, the attributes become customDimensions."""
    events.log(level, name, extra=_clean(attrs))


def summary(value: Any) -> str:
    """A compact JSON text of a request or response, cut to MAX_VALUE."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)[:MAX_VALUE]


def test_tags(headers: Mapping[str, str]) -> dict[str, str]:
    """The performance-test tags in a request's headers, if any."""
    tags = {}
    if run := headers.get(TEST_RUN_HEADER):
        tags["test_run"] = run[:100]
    if case := headers.get(TEST_CASE_HEADER):
        tags["test_case"] = case[:200]
    return tags


@contextmanager
def from_request(headers: Mapping[str, str]) -> Iterator[None]:
    """Join the caller's trace (W3C traceparent) and take its test tags. For MCP tools,
    whose handlers may run outside the HTTP request's task and context."""
    token = otel_context.attach(propagate.extract(dict(headers)))
    try:
        with bound(**test_tags(headers)):
            yield
    finally:
        otel_context.detach(token)


class TestTagsMiddleware:
    """Binds a performance test's run and case headers for the whole HTTP request (REST)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        with bound(**test_tags(headers)):
            await self.app(scope, receive, send)


class Timer:
    """Milliseconds since creation."""

    def __init__(self) -> None:
        self.start = time.perf_counter()

    @property
    def ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000, 1)


# --- Processors (registered in observability.setup_observability) ----------------------


class ContextSpanProcessor(SpanProcessor):
    """Copies the correlation attributes onto every span when it starts."""

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        attrs = _context.get()
        if attrs:
            span.set_attributes(dict(attrs))


class ContextLogProcessor(LogRecordProcessor):
    """Copies the correlation attributes onto every log record when it is emitted."""

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        attrs = _context.get()
        if attrs and log_record.log_record.attributes is not None:
            for key, value in attrs.items():
                log_record.log_record.attributes.setdefault(key, value)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# --- Metrics (F) ---------------------------------------------------------------------------
# Attributes on metrics stay low-cardinality: tool, outcome, channel, test run; never ids.

tool_duration = _meter.create_histogram(
    "simo.tool.duration", unit="ms", description="Tool call duration, by tool and outcome"
)
tool_calls = _meter.create_counter("simo.tool.calls", description="Tool calls by tool and outcome")
search_duration = _meter.create_histogram(
    "simo.search.duration", unit="ms", description="Product search duration"
)
valio_duration = _meter.create_histogram(
    "simo.valio.duration", unit="ms", description="Valio price and availability call duration"
)
engine_duration = _meter.create_histogram(
    "simo.engine.duration", unit="ms", description="Engine decide duration"
)
quote_duration = _meter.create_histogram(
    "simo.quote.duration", unit="ms", description="build_quote and update_quote total duration"
)
quote_decisions = _meter.create_counter(
    "simo.quote.decisions", description="Quote decisions (ready, needs_clarification, rejected)"
)
turn_latency = _meter.create_histogram(
    "simo.voice.turn_latency",
    unit="ms",
    description="From the end of the caller's speech to S.I.MO's first audio",
)
snapshot_misses = _meter.create_counter(
    "simo.valio.snapshot_misses", description="Valio lookups without a recorded response"
)
live_embeddings = _meter.create_counter(
    "simo.search.live_embeddings", description="Query vectors embedded live (not cached)"
)


def metric_attrs(**attrs: Any) -> dict[str, str]:
    """Low-cardinality metric attributes, with the test run when one is set."""
    out = {k: str(v) for k, v in attrs.items() if v is not None}
    if run := _context.get().get(PREFIX + "test_run"):
        out["test_run"] = run
    return out
