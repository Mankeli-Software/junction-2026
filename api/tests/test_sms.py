"""Real SMS through Twilio behind the flag (#46), with Twilio replaced by a fake transport:
these tests never reach the real API. Needs DATABASE_URL.

The app's own sessions commit for real here (`app_db`), because the SMS goes out only
after the commit.
"""

import base64
import json
import logging
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import parse_qsl

import httpx
import pytest
from sqlalchemy import select

from app.agent import PROMPT_VERSION
from app.db import get_sessionmaker
from app.models import AuditEvent, OrderSession, SmsMessage
from app.schemas import BuildQuoteRequest, LineRequest, RequestConfirmationRequest
from app.schemas.dashboard import SessionState
from app.services import accounts, quotes, sms, twilio, voice_calls
from app.services.caller import Caller, Channel
from app.services.phone import mask_phone
from app.settings import get_settings
from tests.phones import new_number

pytestmark = pytest.mark.usefixtures("app_db")

LINE = LineRequest(line_id="l1", text="maito", quantity=20, unit="l", needed_by="2026-11-16")
PUBLIC = "https://simo.example.test"
CALLBACK = f"{PUBLIC}/api/v1/twilio/status"
ACCOUNT_SID = "AC00000000000000000000000000000000"
AUTH_TOKEN = "test-auth-token"
FROM = "+15005550006"  # Twilio's test number


@dataclass
class FakeTwilio:
    """Stands in for api.twilio.com. Each request is kept, with the status of its row at
    the moment it arrived (read on a connection of its own)."""

    response: Callable[[int], httpx.Response] = field(
        default=lambda n: httpx.Response(201, json={"sid": f"SM{n:032d}", "status": "queued"})
    )
    requests: list[dict[str, str]] = field(default_factory=list)
    auth: list[str] = field(default_factory=list)
    row_status_during_send: list[str | None] = field(default_factory=list)

    async def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.twilio.com"
        assert request.url.path == f"/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"
        form = dict(parse_qsl(request.content.decode()))
        self.requests.append(form)
        self.auth.append(request.headers["authorization"])
        async with get_sessionmaker()() as db:
            self.row_status_during_send.append(
                await db.scalar(
                    select(SmsMessage.status).where(
                        SmsMessage.path == "twilio", SmsMessage.body == form["Body"]
                    )
                )
            )
        return self.response(len(self.requests))


@pytest.fixture
def fake_twilio(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTwilio]:
    fake = FakeTwilio()
    monkeypatch.setattr(twilio, "transport", httpx.MockTransport(fake.handler))
    yield fake


@pytest.fixture
def twilio_on(monkeypatch: pytest.MonkeyPatch, fake_twilio: FakeTwilio) -> Iterator[str]:
    """Twilio enabled with fake credentials, and one allowlisted number, which it yields."""
    number = new_number()
    for name, value in {
        "SMS_TWILIO_ENABLED": "true",
        "SMS_ALLOWLIST": f"+15005550001, {number}",
        "TWILIO_ACCOUNT_SID": ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
        "TWILIO_FROM_NUMBER": FROM,
        "PUBLIC_BASE_URL": PUBLIC,
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield number
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_real_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any test here that reaches Twilio without the fake fails."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected Twilio request to {request.url.host}")

    monkeypatch.setattr(twilio, "transport", httpx.MockTransport(refuse))


async def sign_in(phone: str, channel: Channel = "web") -> Caller:
    async with get_sessionmaker()() as db:
        account = await accounts.create_demo_account(db, phone, [], "en")
        await db.commit()
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=[],
        lang="en",
        channel=channel,
    )


async def start_call(phone: str) -> voice_calls.CallStart:
    caller = await sign_in(phone)
    async with get_sessionmaker()() as db:
        start = await voice_calls.start_call(db, caller.user_id, prompt_version=PROMPT_VERSION)
        await db.commit()
    assert start is not None
    return start


async def confirm(caller: Caller):
    """A ready quote sent for confirmation, committed. (response, quote id)"""
    async with get_sessionmaker()() as db:
        quote = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[LINE]))
        response = await quotes.request_confirmation(
            db, caller, RequestConfirmationRequest(quote_id=quote.quote_id)
        )
        await db.commit()
    return response, quote.quote_id


async def end_call(start: voice_calls.CallStart) -> voice_calls.CallEnd:
    async with get_sessionmaker()() as db:
        end = await voice_calls.end_call(
            db, start.caller.user_id, start.session_id, ended_by="visitor", duration_s=60
        )
        await db.commit()
    return end


async def rows(caller: Caller) -> dict[str, SmsMessage]:
    async with get_sessionmaker()() as db:
        messages = await db.scalars(select(SmsMessage).where(SmsMessage.user_id == caller.user_id))
        return {m.path: m for m in messages}


async def audit_events(*types: str) -> list[AuditEvent]:
    async with get_sessionmaker()() as db:
        return list(
            await db.scalars(
                select(AuditEvent).where(AuditEvent.type.in_(types)).order_by(AuditEvent.seq)
            )
        )


async def session_state(session_id: uuid.UUID) -> str:
    async with get_sessionmaker()() as db:
        return (await db.get_one(OrderSession, session_id)).state


async def quote_session_id(quote_id: str) -> uuid.UUID:
    from app.models import Quote

    async with get_sessionmaker()() as db:
        return (await db.get_one(Quote, uuid.UUID(quote_id))).session_id


# --- Who gets an SMS --------------------------------------------------------------------


async def test_with_the_flag_off_the_link_goes_to_the_inbox_only(fake_twilio):
    caller = await sign_in(new_number())
    response, _ = await confirm(caller)
    await sms.wait_for_sending()

    assert response.delivery_status == "off" and response.inbox is True
    assert set(await rows(caller)) == {"inbox"}
    assert fake_twilio.requests == []


async def test_a_number_not_on_the_allowlist_gets_no_sms(twilio_on, fake_twilio):
    caller = await sign_in(new_number())
    response, _ = await confirm(caller)
    await sms.wait_for_sending()

    assert response.delivery_status == "off"
    assert set(await rows(caller)) == {"inbox"}
    assert fake_twilio.requests == []


async def test_an_allowlisted_number_gets_the_sms_after_the_commit(twilio_on, fake_twilio, caplog):
    caplog.set_level(logging.DEBUG)
    caller = await sign_in(twilio_on)
    response, quote_id = await confirm(caller)
    await sms.wait_for_sending()

    assert response.delivery_status == "sent" and response.inbox is True
    by_path = await rows(caller)
    assert by_path["inbox"].status == "delivered"  # the inbox message always stays
    sent = by_path["twilio"]
    assert sent.status == "queued" and sent.twilio_sid == f"SM{1:032d}"
    assert sent.body == by_path["inbox"].body

    [request] = fake_twilio.requests
    assert request == {
        "To": twilio_on,
        "From": FROM,
        "Body": sent.body,
        "StatusCallback": CALLBACK,
    }
    assert sent.link in request["Body"]
    expected_auth = base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode()
    assert fake_twilio.auth == [f"Basic {expected_auth}"]
    # Claimed and committed before the request; no transaction is open across it (#86).
    assert fake_twilio.row_status_during_send == ["sending"]

    [event] = await audit_events("sms_sent")
    assert event.payload == {
        "quote_id": quote_id,
        "path": "twilio",
        "sent_to_masked": mask_phone(twilio_on),
        "status": "queued",
    }
    assert event.session_id == await quote_session_id(quote_id)
    assert_no_secrets(caplog.text, sent.link, twilio_on)
    assert_no_secrets(json.dumps([e.payload for e in await audit_events("sms_sent")]), sent.link)


async def test_a_rolled_back_request_sends_nothing(twilio_on, fake_twilio):
    caller = await sign_in(twilio_on)
    async with get_sessionmaker()() as db:
        quote = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[LINE]))
        await quotes.request_confirmation(
            db, caller, RequestConfirmationRequest(quote_id=quote.quote_id)
        )
        await db.rollback()
    await sms.wait_for_sending()

    assert fake_twilio.requests == []


# --- The phone channel ------------------------------------------------------------------


async def test_on_a_call_the_sms_waits_for_the_hang_up(twilio_on, fake_twilio):
    start = await start_call(twilio_on)
    response, quote_id = await confirm(start.caller)
    await sms.wait_for_sending()

    assert response.delivery_status == "held"
    assert {path: m.status for path, m in (await rows(start.caller)).items()} == {
        "inbox": "held",
        "twilio": "held",
    }
    assert fake_twilio.requests == []

    end = await end_call(start)
    assert end.released_quote_ids == [quote_id]
    assert await voice_calls.sms_delivery(end) == "sent"

    assert len(fake_twilio.requests) == 1
    assert {path: m.status for path, m in (await rows(start.caller)).items()} == {
        "inbox": "delivered",
        "twilio": "queued",
    }
    # Ending again sends nothing more.
    await end_call(start)
    await sms.wait_for_sending()
    assert len(fake_twilio.requests) == 1


async def test_a_call_with_twilio_off_reports_off(fake_twilio):
    start = await start_call(new_number())
    await confirm(start.caller)
    end = await end_call(start)

    assert await voice_calls.sms_delivery(end) == "off"
    assert fake_twilio.requests == []


# --- Twilio refusing --------------------------------------------------------------------


def refusal(n: int) -> httpx.Response:
    # Twilio's message repeats the number, so it must never reach a log.
    return httpx.Response(
        400,
        json={"code": 21211, "message": "The 'To' number is not valid.", "status": 400},
    )


async def test_twilio_refusing_the_sms_is_failed_and_the_inbox_still_has_it(
    twilio_on, fake_twilio, caplog
):
    caplog.set_level(logging.DEBUG)
    fake_twilio.response = refusal
    start = await start_call(twilio_on)
    _, quote_id = await confirm(start.caller)
    end = await end_call(start)

    assert await voice_calls.sms_delivery(end) == "failed"
    by_path = await rows(start.caller)
    assert by_path["inbox"].status == "delivered"
    assert by_path["twilio"].status == "failed" and by_path["twilio"].error_code == "21211"
    [event] = await audit_events("sms_failed")
    assert event.payload["error_code"] == "21211"
    assert event.payload["sent_to_masked"] == mask_phone(twilio_on)
    assert await session_state(start.session_id) == SessionState.sms_failed
    assert_no_secrets(caplog.text, by_path["twilio"].link, twilio_on)


async def test_twilio_out_of_reach_is_failed(twilio_on, fake_twilio):
    def down(n: int) -> httpx.Response:
        raise httpx.ConnectError("no route")

    fake_twilio.response = down
    caller = await sign_in(twilio_on)
    response, _ = await confirm(caller)
    await sms.wait_for_sending()

    # Sent after the commit, so the tool's answer can't know yet; the dashboard does.
    assert response.delivery_status == "sent"
    sent = (await rows(caller))["twilio"]
    assert sent.status == "failed" and sent.error_code == "network: ConnectError"
    assert len(await audit_events("sms_failed")) == 1


# --- The limit --------------------------------------------------------------------------


async def test_at_most_three_sms_per_number_per_hour(twilio_on, fake_twilio, caplog):
    caplog.set_level(logging.WARNING)
    callers = [await sign_in(twilio_on) for _ in range(4)]  # four browsers, one number
    statuses = [(await confirm(caller))[0].delivery_status for caller in callers]
    await sms.wait_for_sending()

    assert statuses == ["sent", "sent", "sent", "off"]
    assert len(fake_twilio.requests) == 3
    assert set(await rows(callers[3])) == {"inbox"}
    assert "SMS limit reached for " + mask_phone(twilio_on) in caplog.text
    assert twilio_on not in caplog.text


def assert_no_secrets(text: str, link: str, number: str | None = None) -> None:
    assert link not in text
    assert "/c/" not in text
    if number is not None:
        assert number not in text
