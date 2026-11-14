"""Logs, traces and exceptions to Azure Application Insights through OpenTelemetry.

Off unless `APPLICATIONINSIGHTS_CONNECTION_STRING` is set (Key Vault secret
`applicationinsights-connection-string` on the VM), so laptops and tests send nothing.
Call `setup_observability()` before the FastAPI app is created: the instrumentation patches
the FastAPI class.
"""

import logging
import os

from app.settings import get_settings

# Requests that are never recorded (a regular expression searched in the URL):
# - the confirmation token is the link's whole authorisation and sits in the path, and the
#   OAuth routes carry one-time codes in their query strings (#46: never in a log line);
# - the public stream stays open for as long as a dashboard is, and health is polled.
EXCLUDED_URLS = r"/confirmations/,/oauth/,/api/v1/public/stream,/api/v1/health"


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
    return True
