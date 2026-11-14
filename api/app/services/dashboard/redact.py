"""The one redaction step for every public dashboard response and stream event (#49).

Events are already written with masked numbers (technical-plan.md §8.5), so this is the
second line of defence: whatever reaches the dashboard goes through `redact()` last.
"""

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.services.phone import mask_phone

# Compared in lower case, so `Authorization` and `Cookie` headers go too.
SECRET_KEYS = frozenset({"token", "token_hash", "link", "cookie", "authorization", "access_token"})

# The path of the confirmation page, whose last part is the token (`/c/<token>`).
CONFIRMATION_PATH = re.compile(r"/c/[^\s/?#\"'<>…]+")
REDACTED_CONFIRMATION_PATH = "/c/…"

# A `+` and 7 to 15 digits, with single spaces or dashes allowed between them so a
# formatted number is caught too. Masked numbers (`+358 40 *** **12`) have too few
# digits in a row to match.
PHONE = re.compile(r"(?<![\w+])\+[1-9](?:[ -]?\d){6,14}(?![\d\w])")

# Local part and domain. A masked local part (`j***`) has a `*` before the `@`, so it
# does not match again.
EMAIL = re.compile(
    r"(?<![\w.%+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})"
)


def redact(obj: Any) -> Any:
    """Return a copy of `obj` that is safe to show on the public dashboard.

    Dicts, lists and tuples are walked to any depth: the keys in `SECRET_KEYS` are
    dropped, and every string has its confirmation URLs, phone numbers and emails masked.
    A pydantic model is dumped to JSON-ready data first. Other values pass through.
    """
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, Mapping):
        return {
            key: redact(value)
            for key, value in obj.items()
            if not (isinstance(key, str) and key.lower() in SECRET_KEYS)
        }
    if isinstance(obj, list | tuple):
        return [redact(item) for item in obj]
    return obj


def redact_text(text: str) -> str:
    text = CONFIRMATION_PATH.sub(REDACTED_CONFIRMATION_PATH, text)
    text = PHONE.sub(lambda m: _mask_phone_match(m.group()), text)
    return EMAIL.sub(lambda m: mask_email_parts(m.group(1), m.group(2)), text)


def mask_email(email: str) -> str:
    """`jane.doe@example.com` -> `j***@example.com`."""
    local, _, domain = email.rpartition("@")
    return mask_email_parts(local, domain)


def mask_email_parts(local: str, domain: str) -> str:
    return f"{local[:1]}***@{domain}"


def _mask_phone_match(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    try:
        return mask_phone(f"+{digits}")
    except Exception:
        # Not a number phonenumbers can read: still never show the digits.
        return f"+*** *** **{digits[-2:]}"
