import sys
import types

import pytest

from app import observability
from app.settings import get_settings


@pytest.fixture
def connection_string(monkeypatch):
    def set_it(value: str) -> None:
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", value)
        get_settings.cache_clear()

    yield set_it
    monkeypatch.undo()
    get_settings.cache_clear()


def test_nothing_starts_without_a_connection_string(connection_string, monkeypatch):
    connection_string("")
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", None)  # import would fail

    assert observability.setup_observability() is False


def test_it_configures_the_exporter_and_keeps_tokens_out(connection_string, monkeypatch):
    connection_string("InstrumentationKey=abc;IngestionEndpoint=https://example.test/")
    calls = []
    fake = types.ModuleType("azure.monitor.opentelemetry")
    fake.configure_azure_monitor = lambda **kwargs: calls.append(kwargs)
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake)
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS", raising=False)

    assert observability.setup_observability() is True

    (call,) = calls
    assert (
        call["connection_string"]
        == "InstrumentationKey=abc;IngestionEndpoint=https://example.test/"
    )
    # Every span and log record gets the call's ids (#84).
    assert [type(p).__name__ for p in call["span_processors"]] == ["ContextSpanProcessor"]
    assert [type(p).__name__ for p in call["log_record_processors"]] == ["ContextLogProcessor"]
    import logging
    import os

    assert logging.getLogger("azure").level == logging.WARNING
    for client in ("httpx", "httpx2"):  # HTTP clients log full URLs
        assert logging.getLogger(client).level == logging.WARNING
    excluded = os.environ["OTEL_PYTHON_EXCLUDED_URLS"].split(",")
    assert "/confirmations/" in excluded and "/oauth/" in excluded
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS")
    monkeypatch.delenv("OTEL_SERVICE_NAME")


@pytest.mark.parametrize(
    ("path", "query", "skipped"),
    [
        ("/api/v1/confirmations/SECRETTOKEN123", "", True),
        ("/api/v1/confirmations/SECRETTOKEN123/confirm", "", True),
        ("/oauth/authorize", "code=abc&state=x", True),
        ("/api/v1/oauth/token", "", True),
        ("/api/v1/public/stream", "last=5", True),
        ("/api/v1/health", "", True),
        ("/api/v1/products", "q=maito", False),
        ("/.well-known/oauth-protected-resource/mcp", "", False),  # public metadata
    ],
)
def test_excluded_requests(path, query, skipped):
    scope = {"type": "http", "path": path, "query_string": query.encode()}
    assert observability.excluded(scope) is skipped


def test_the_app_passes_the_exclusion_to_fastapi_telemetry():
    from app.main import app

    assert app._telemetry["exclude"] is observability.excluded


def test_excluded_requests_leave_no_span():
    # FastAPI's own telemetry makes the request spans (not the OpenTelemetry FastAPI
    # instrumentation), so this checks the switch that is actually used.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI(telemetry={"exclude": observability.excluded, "tracer_provider": provider})

    @app.get("/api/v1/confirmations/{token}")
    def confirmation(token: str) -> dict:
        return {}

    @app.get("/api/v1/health")
    def health() -> dict:
        return {}

    @app.get("/api/v1/products")
    def products() -> dict:
        return {}

    client = TestClient(app)
    client.get("/api/v1/confirmations/SECRETTOKEN123")
    client.get("/api/v1/health")
    client.get("/api/v1/products")

    recorded = " ".join(
        f"{s.name} {s.attributes.get('url.path', '')} {s.attributes.get('http.target', '')}"
        for s in exporter.get_finished_spans()
    )
    assert "SECRETTOKEN123" not in recorded and "health" not in recorded
    assert "/api/v1/products" in recorded
