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

    assert calls == [
        {"connection_string": "InstrumentationKey=abc;IngestionEndpoint=https://example.test/"}
    ]
    import logging
    import os

    assert logging.getLogger("azure").level == logging.WARNING
    excluded = os.environ["OTEL_PYTHON_EXCLUDED_URLS"].split(",")
    assert "/confirmations/" in excluded and "/oauth/" in excluded
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS")
    monkeypatch.delenv("OTEL_SERVICE_NAME")
