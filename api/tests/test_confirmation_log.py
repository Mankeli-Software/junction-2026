"""The confirmation token stays out of the access log (#46, #47). No database needed."""

import logging

import app.main  # noqa: F401  (installs the filter)
from app.interfaces.rest.confirmations import TokenRedactingFilter


def access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "POST", path, "1.1", 200),
        None,
    )


def test_the_access_log_never_shows_the_token():
    record = access_record("/api/v1/confirmations/abcDEF_123-x/confirm?x=1")
    TokenRedactingFilter().filter(record)
    assert record.getMessage() == (
        '127.0.0.1:1 - "POST /api/v1/confirmations/…/confirm?x=1 HTTP/1.1" 200'
    )


def test_other_paths_are_logged_as_they_are():
    record = access_record("/api/v1/quotes/q1/status")
    TokenRedactingFilter().filter(record)
    assert "/api/v1/quotes/q1/status" in record.getMessage()


def test_the_app_installs_the_filter():
    filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, TokenRedactingFilter) for f in filters)
