"""Twilio's Messages API and its request signatures (#46, technical-plan.md §8.2, §9.7).

Plain `httpx`, no Twilio SDK. Only `app.services.sms` sends, and only after the database
transaction has committed (#86).

Nothing here logs or raises with the message body (it holds the confirmation link), the
recipient's number or the credentials: a `TwilioError` carries only the HTTP status and
Twilio's error code, never Twilio's own message, which repeats the number.
"""

import base64
import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from app.settings import Settings, get_settings

API_BASE = "https://api.twilio.com/2010-04-01"
TIMEOUT = httpx.Timeout(5.0)

# Tests put a fake transport here (`httpx.MockTransport`), so they never reach Twilio.
transport: httpx.AsyncBaseTransport | None = None

# Twilio's message statuses (its status callback and the create response) as ours on the
# `sms_messages` row. Statuses not listed (receiving, received) never come for a message
# we send, and are ignored.
STATUSES = {
    "accepted": "queued",
    "scheduled": "queued",
    "queued": "queued",
    "sending": "queued",
    "sent": "sent",
    "delivered": "delivered",
    "read": "delivered",
    "undelivered": "failed",
    "failed": "failed",
    "canceled": "failed",
}


@dataclass(frozen=True)
class SentMessage:
    sid: str
    status: str  # ours, from STATUSES


class TwilioError(Exception):
    """Twilio refused the message, or could not be reached (`http_status` None)."""

    def __init__(self, http_status: int | None, code: str | None) -> None:
        self.http_status = http_status
        self.code = code
        super().__init__(f"HTTP {http_status}, code {code}")


async def send_sms(
    *, to: str, body: str, status_callback: str, settings: Settings | None = None
) -> SentMessage:
    """Create the message. Raises TwilioError when Twilio refuses it or can't be reached."""
    settings = settings or get_settings()
    url = f"{API_BASE}/Accounts/{settings.twilio_account_sid}/Messages.json"
    data = {
        "To": to,
        "From": settings.twilio_from_number,
        "Body": body,
        "StatusCallback": status_callback,
    }
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=TIMEOUT,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        ) as client:
            response = await client.post(url, data=data)
    except httpx.HTTPError as error:
        # The request (with the body) hangs off the error, so it isn't chained.
        raise TwilioError(None, f"network: {type(error).__name__}") from None
    if response.status_code >= 400:
        raise TwilioError(response.status_code, _error_code(response))
    try:
        payload = response.json()
        sid = str(payload["sid"])
    except (ValueError, KeyError, TypeError):
        raise TwilioError(response.status_code, "unreadable response") from None
    return SentMessage(sid=sid, status=STATUSES.get(str(payload.get("status")), "queued"))


def _error_code(response: httpx.Response) -> str | None:
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        return None
    return None if code is None else str(code)


def signature(auth_token: str, url: str, params: Iterable[tuple[str, str]]) -> str:
    """Twilio's `X-Twilio-Signature` for a form POST: base64 of HMAC-SHA1, keyed with the
    auth token, over the full URL followed by each parameter's name and value, sorted by
    name (and by value for a repeated name)."""
    data = url + "".join(name + value for name, value in sorted(params))
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def valid_signature(
    auth_token: str, url: str, params: Iterable[tuple[str, str]], received: str
) -> bool:
    """Whether `received` is Twilio's signature for this request, compared in constant time.
    False without an auth token, so nothing is accepted while Twilio isn't set up."""
    if not auth_token or not received:
        return False
    expected = signature(auth_token, url, params)
    return hmac.compare_digest(expected.encode(), received.encode())
