"""The confirmation request and the simulated inbox at the service level (#46).

Needs DATABASE_URL. Each test runs in a transaction that is rolled back.
"""

import asyncio
import json
import logging
import random
import re
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.deps import DEV_CALLER
from app.models import Confirmation, SmsMessage
from app.schemas import BuildQuoteRequest, LineRequest, QuoteResponse
from app.services import accounts, confirmations, quotes
from app.services.caller import Caller, Channel
from app.services.dashboard.redact import redact
from app.services.dashboard.stream import Broadcaster, StreamEvent
from app.services.errors import StateError
from app.services.tokens import hash_token
from app.settings import get_settings

LINE = LineRequest(line_id="l1", text="maito", quantity=20, unit="l", needed_by="2026-11-16")

LINK = re.compile(r"/c/([A-Za-z0-9_-]{43})$")


def new_number() -> str:
    return f"+35840{random.randrange(10**6, 10**7)}"


async def sign_in(
    db: AsyncSession, phone: str, channel: Channel = "web", lang: str = "en"
) -> Caller:
    """A demo account for `phone` in a new browser, as the caller on `channel`."""
    account = await accounts.create_demo_account(db, phone, [], lang)
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=[],
        lang=lang,
        channel=channel,
    )


async def ready_quote(db: AsyncSession, caller: Caller) -> QuoteResponse:
    quote = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[LINE]))
    assert quote.quote_hash is not None
    return quote


def token_of(message: SmsMessage) -> str:
    match = LINK.search(message.link)
    assert match, message.link
    return match.group(1)


async def messages_of(db: AsyncSession, caller: Caller) -> list[SmsMessage]:
    return list(await db.scalars(select(SmsMessage).where(SmsMessage.user_id == caller.user_id)))


async def test_the_token_is_never_returned_and_is_stored_hashed(db, caplog):
    caplog.set_level(logging.DEBUG)
    caller = await sign_in(db, new_number())
    quote = await ready_quote(db, caller)

    response = await confirmations.request_confirmation(db, caller, quote)

    [message] = await messages_of(db, caller)
    token = token_of(message)
    assert len(token) == 43  # 32 random bytes, URL-safe base64
    assert message.link == f"{get_settings().public_base_url}/c/{token}"

    # Not in the response, nor anywhere in the confirmation row, nor in the logs.
    assert response.model_dump() == {
        "sent_to_masked": caller.phone_masked,
        "sms_status": "off",
        "inbox": True,
    }
    assert token not in response.model_dump_json()
    confirmation = await db.get_one(Confirmation, message.confirmation_id)
    assert confirmation.token_hash == hash_token(token)
    row = (
        await db.execute(
            text("SELECT row_to_json(c)::text FROM confirmations c WHERE id = :id"),
            {"id": confirmation.id},
        )
    ).scalar_one()
    assert token not in row
    assert token not in caplog.text
    assert "/c/" not in caplog.text

    assert confirmation.quote_id == quote.quote_id
    assert confirmation.quote_hash == quote.quote_hash
    assert confirmation.channel == "web"


async def test_each_link_has_its_own_token(db):
    caller = await sign_in(db, new_number())
    for _ in range(2):
        await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))

    first, second = await messages_of(db, caller)
    assert token_of(first) != token_of(second)


async def test_the_link_goes_only_to_the_callers_own_account(db):
    phone = new_number()
    caller = await sign_in(db, phone)
    same_number_other_browser = await sign_in(db, phone)
    other_number = await sign_in(db, new_number())

    await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))

    [message] = await messages_of(db, caller)
    confirmation = await db.get_one(Confirmation, message.confirmation_id)
    assert confirmation.user_id == caller.user_id
    assert confirmation.company_id == caller.company_id
    assert confirmation.recipient_e164 == phone
    assert len(await confirmations.inbox(db, caller.user_id)) == 1
    assert await confirmations.inbox(db, same_number_other_browser.user_id) == []
    assert await confirmations.inbox(db, other_number.user_id) == []


async def test_a_caller_without_an_account_gets_nothing_sent(db):
    quote = await ready_quote(db, await sign_in(db, new_number()))
    nobody = DEV_CALLER.model_copy(update={"user_id": uuid.uuid4()})

    with pytest.raises(StateError):
        await confirmations.request_confirmation(db, nobody, quote)
    assert (
        await db.scalar(select(Confirmation).where(Confirmation.quote_id == quote.quote_id))
    ) is None


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "S.I.MO: confirm your order, {total}. Junction 2026 demo, no real order is placed."),
        (
            "fi",
            "S.I.MO: vahvista tilauksesi, {total}. Junction 2026 -demo, oikeaa tilausta ei tehdä.",
        ),
    ],
)
async def test_the_message_is_in_the_accounts_language(db, lang, text):
    caller = await sign_in(db, new_number(), lang=lang)
    quote = await ready_quote(db, caller)

    await confirmations.request_confirmation(db, caller, quote)

    [message] = await confirmations.inbox(db, caller.user_id)
    total = confirmations.format_euros(quote.total_cents)
    assert message.text == text.format(total=total)
    [row] = await messages_of(db, caller)
    assert row.body.startswith(text.format(total=total).split(". ")[0] + f": {message.link} ")


def test_format_euros():
    assert confirmations.format_euros(12840) == "128,40 €"
    assert confirmations.format_euros(5) == "0,05 €"
    assert confirmations.format_euros(123456789) == "1 234 567,89 €"


async def test_the_phone_channel_holds_the_message_until_the_call_ends(db):
    caller = await sign_in(db, new_number(), channel="phone")
    quote = await ready_quote(db, caller)

    response = await confirmations.request_confirmation(db, caller, quote)

    assert response.sms_status == "held"
    assert response.inbox is True
    assert await confirmations.inbox(db, caller.user_id) == []
    [row] = await messages_of(db, caller)
    assert (row.path, row.status, row.delivered_at) == ("inbox", "held", None)

    assert await confirmations.release_held_messages(db, caller.user_id) == [quote.quote_id]

    [message] = await confirmations.inbox(db, caller.user_id)
    assert message.id == str(row.id)
    assert row.status == "delivered"
    assert await confirmations.release_held_messages(db, caller.user_id) == []


@pytest.mark.parametrize("channel", ["web", "web_chat", "connector"])
async def test_other_channels_deliver_at_once(db, channel):
    caller = await sign_in(db, new_number(), channel=channel)

    response = await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))

    assert response.sms_status == "off"
    assert len(await confirmations.inbox(db, caller.user_id)) == 1
    assert await confirmations.release_held_messages(db, caller.user_id) == []


async def test_releasing_touches_only_that_users_messages(db):
    phone = new_number()
    one = await sign_in(db, phone, channel="phone")
    two = await sign_in(db, phone, channel="phone")
    await confirmations.request_confirmation(db, one, await ready_quote(db, one))
    await confirmations.request_confirmation(db, two, await ready_quote(db, two))

    await confirmations.release_held_messages(db, one.user_id)

    assert len(await confirmations.inbox(db, one.user_id)) == 1
    assert await confirmations.inbox(db, two.user_id) == []


async def _next_event(events) -> tuple[str, object]:
    sse = await asyncio.wait_for(anext(events), 2)
    return sse.event, json.loads(sse.data)


async def test_the_stream_sends_a_snapshot_then_inbox_message_after_commit(db):
    caller = await sign_in(db, new_number())
    await db.commit()

    async def snapshot():
        return [m.model_dump(mode="json") for m in await confirmations.inbox(db, caller.user_id)]

    events = confirmations.inbox_events(caller.user_id, snapshot)
    try:
        assert await _next_event(events) == ("snapshot", [])

        await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))
        await db.commit()

        event, data = await _next_event(events)
        [message] = await confirmations.inbox(db, caller.user_id)
        assert event == "inbox_message"
        assert data == message.model_dump(mode="json")
        assert LINK.search(data["link"])  # the user's own stream keeps the link
    finally:
        await events.aclose()
    assert caller.user_id not in confirmations._inboxes


async def test_a_held_message_reaches_the_stream_when_released(db):
    caller = await sign_in(db, new_number(), channel="phone")
    await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))
    await db.commit()

    async def snapshot():
        return []

    events = confirmations.inbox_events(caller.user_id, snapshot)
    try:
        await _next_event(events)
        await confirmations.release_held_messages(db, caller.user_id)
        await db.commit()

        event, data = await _next_event(events)
        assert event == "inbox_message"
        assert LINK.search(data["link"])
    finally:
        await events.aclose()


async def test_a_rolled_back_request_is_not_streamed(db):
    caller = await sign_in(db, new_number())
    await db.commit()
    received = []
    broadcaster = confirmations._inbox_broadcaster(caller.user_id)
    broadcaster.publish = received.append  # type: ignore[method-assign]
    try:
        await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))
        await db.rollback()
        await db.commit()
    finally:
        confirmations._inboxes.pop(caller.user_id, None)

    assert received == []


async def test_another_users_stream_gets_nothing(db):
    phone = new_number()
    caller = await sign_in(db, phone)
    other = await sign_in(db, phone)
    await db.commit()
    received = []
    broadcaster = confirmations._inbox_broadcaster(other.user_id)
    broadcaster.publish = received.append  # type: ignore[method-assign]
    try:
        await confirmations.request_confirmation(db, caller, await ready_quote(db, caller))
        await db.commit()
    finally:
        confirmations._inboxes.pop(other.user_id, None)

    assert received == []


async def test_no_token_or_link_reaches_the_public_dashboard(db, caplog):
    """Nothing about the confirmation is published on the dashboard stream, and even if an
    inbox message got there, the one redaction step would strip its link and token."""
    caplog.set_level(logging.DEBUG)
    public = Broadcaster()
    published: list[StreamEvent] = []
    original = public.publish

    def spy(event: StreamEvent) -> None:
        published.append(event)
        original(event)

    public.publish = spy  # type: ignore[method-assign]
    from app.services.dashboard import stream

    previous, stream._broadcaster = stream._broadcaster, public
    try:
        caller = await sign_in(db, new_number(), channel="phone")
        response = await confirmations.request_confirmation(
            db, caller, await ready_quote(db, caller)
        )
        await confirmations.release_held_messages(db, caller.user_id)
        await db.commit()
    finally:
        stream._broadcaster = previous

    [row] = await messages_of(db, caller)
    token = token_of(row)
    assert published == []
    assert token not in response.model_dump_json()
    assert token not in caplog.text

    [message] = await confirmations.inbox(db, caller.user_id)
    leaked = redact({"type": "inbox_delivered", "message": message, "body": row.body})
    assert token not in json.dumps(leaked)
    assert "link" not in leaked["message"]
    assert "/c/…" in leaked["body"]
