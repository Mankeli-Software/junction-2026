"""Logs, traces and exceptions to Azure Application Insights through OpenTelemetry.

Off unless `APPLICATIONINSIGHTS_CONNECTION_STRING` is set (Key Vault secret
`applicationinsights-connection-string` on the VM), so laptops and tests send nothing.
Call `setup_observability()` before the FastAPI app is created: the instrumentation patches
the FastAPI class.
"""

import logging
import os
import re
from collections.abc import MutableMapping
from typing import Any

from app.settings import get_settings

# Requests that are never recorded (regular expressions searched in the path and query):
# - the confirmation token is the link's whole authorisation and sits in the path, and the
#   OAuth routes carry one-time codes in their query strings (#46: never in a log line);
# - the public stream stays open for as long as a dashboard is, and health is polled.
EXCLUDED = ("/confirmations/", "/oauth/", "/api/v1/public/stream", "/api/v1/health")
EXCLUDED_URLS = ",".join(EXCLUDED)
_EXCLUDED = re.compile("|".join(EXCLUDED))


def excluded(scope: MutableMapping[str, Any]) -> bool:
    """FastAPI's own telemetry (`FastAPI(telemetry={"exclude": excluded})`) skips these.

    FastAPI 0.162 creates the request spans itself and ignores OTEL_PYTHON_EXCLUDED_URLS,
    which only the OpenTelemetry FastAPI instrumentation reads; that instrumentation never
    wraps our app, because main.py imports FastAPI before the distro swaps the class.
    """
    query = scope.get("query_string", b"").decode("latin-1")
    return bool(_EXCLUDED.search(f"{scope.get('path', '')}?{query}"))


def setup_observability() -> bool:
    """Start the exporter; True when it is on."""
    settings = get_settings()
    if not settings.applicationinsights_connection_string:
        return False
    os.environ.setdefault("OTEL_PYTHON_EXCLUDED_URLS", EXCLUDED_URLS)
    os.environ.setdefault("OTEL_SERVICE_NAME", "simo-api")
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=settings.applicationinsights_connection_string)
    # The root logger defaults to WARNING, which would drop our own INFO lines.
    logging.getLogger().setLevel(logging.INFO)
    # The exporter logs every upload it makes, which would be logged and uploaded in turn.
    logging.getLogger("azure").setLevel(logging.WARNING)
    # httpx logs every request's full URL at INFO, so a token in a URL would be exported.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return True
