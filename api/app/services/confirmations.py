"""Confirmation requests and the simulated phone inbox (#46, technical-plan.md §8.2, §9.2).

`request_confirmation()` makes a confirmation for a ready quote and sends its link to the
account that made the order, and only there: the caller's own user and number. There is
no recipient argument (vision §6).

- The link is `<PUBLIC_BASE_URL>/c/<token>`, with a 256-bit token. Only its SHA-256 is
  stored with the confirmation. The link travels in the inbox message, and nowhere else:
  never in a return value, a log line, an audit or dashboard event or the public stream.
- Every message lands in the user's simulated phone inbox (`sms_messages`, path `inbox`).
  Twilio (path `twilio`, behind `SMS_TWILIO_ENABLED` and `SMS_ALLOWLIST`) comes later.
- On the phone channel the message is `held` until the call ends: the voice relay (#52)
  calls `release_held_messages()` on hang-up, a dropped call or the time limit. A phone
  request that only finishes after the call has ended delivers at once (#88). Every other
  channel delivers at once.

A delivered message goes out on the user's inbox stream after the database transaction
commits, so a rolled-back request never shows up in a browser. Like the other services,
these functions take the request's `AsyncSession` and only flush: the caller commits.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sse_starlette import ServerSentEvent

from app.models import Confirmation, OrderSession, Quote, SmsMessage, User
from app.schemas import ConfirmationRequestResponse, Localized, QuoteResponse
from app.schemas.common import Lang
from app.settings import get_settings

from . import audit
from .caller import Caller, Channel
from .dashboard.stream import Broadcaster, StreamEvent
from .errors import StateError
from .phone import mask_phone
from .sessions import IDLE_TIMEOUT
from .tokens import hash_token, new_token

log = logging.getLogger(__name__)

# Channels whose message waits for the end of the call.
HELD_CHANNELS: frozenset[Channel] = frozenset({"phone"})

INBOX_MESSAGE_EVENT = "inbox_message"


class InboxMessage(BaseModel):
    """One message in the simulated phone (`InboxMessage` in `web/src/lib/demo/types.ts`)."""

    id: str
    at: datetime
    text: str
    link: str


def confirmation_link(token: str) -> str:
    return f"{get_settings().public_base_url}/c/{token}"


def format_euros(cents: int) -> str:
    """`12840` -> `128,40 €`, the format of the message text in both languages."""
    whole, rest = divmod(cents, 100)
    return f"{whole:,}".replace(",", " ") + f",{rest:02d} €"


# The message in the user's language: the inbox text without the link, and the whole SMS
# body with it. A stranger who gets it must see that it is a demo (call-screen.md §6).
_TEXT = {
    "fi": "S.I.MO: vahvista tilauksesi, {total}. Junction 2026 -demo, oikeaa tilausta ei tehdä.",
    "en": "S.I.MO: confirm your order, {total}. Junction 2026 demo, no real order is placed.",
}
_BODY = {
    "fi": "S.I.MO: vahvista tilauksesi, {total}: {link} Junction 2026 -demo, "
    "oikeaa tilausta ei tehdä.",
    "en": "S.I.MO: confirm your order, {total}: {link} Junction 2026 demo, "
    "no real order is placed.",
}


def message_text(lang: Lang, total_cents: int, link: str) -> tuple[str, str]:
    """`(text, body)`: what the simulated phone shows beside the link, and the SMS body."""
    total = format_euros(total_cents)
    return _TEXT[lang].format(total=total), _BODY[lang].format(total=total, link=link)


async def request_confirmation(
    db: AsyncSession, caller: Caller, quote: QuoteResponse, *, now: datetime | None = None
) -> ConfirmationRequestResponse:
    """Make a confirmation for `quote` and send its link to the caller's own inbox.

    The quote service has already checked that the quote is ready and the caller's. Raises
    StateError when the caller has no account to send to (the DEV_FAKE_CALLER customer).
    """
    now = now or datetime.now(UTC)
    user = await db.get(User, caller.user_id)
    if user is None or user.company_id != caller.company_id:
        raise StateError("there is no account to send the confirmation link to; sign in first")
    if quote.quote_hash is None:
        raise StateError("the quote has no hash, so it can't be confirmed")

    token = new_token()
    confirmation = Confirmation(
        token_hash=hash_token(token),
        quote_id=quote.quote_id,
        quote_hash=quote.quote_hash,
        company_id=user.company_id,
        user_id=user.id,
        recipient_e164=user.phone_e164,
        channel=caller.channel,
        created_at=now,
        expires_at=quote.expires_at,
    )
    db.add(confirmation)
    await db.flush()

    link = confirmation_link(token)
    text, body = message_text(user.lang, quote.total_cents, link)
    held = caller.channel in HELD_CHANNELS and await call_in_progress(db, user.id, now=now)
    message = SmsMessage(
        confirmation_id=confirmation.id,
        user_id=user.id,
        path="inbox",
        status="held" if held else "delivered",
        body=body,
        text=text,
        link=link,
        created_at=now,
        delivered_at=None if held else now,
    )
    db.add(message)
    await db.flush()
    if not held:
        _publish_after_commit(db, message)
        if caller.channel in HELD_CHANNELS:
            # No call to wait for: it ended while this request ran, and the relay has
            # released already (#88).
            quote_row = await db.get_one(Quote, uuid.UUID(quote.quote_id))
            await record_inbox_delivered(db, quote_row.session_id, quote_row.id)
    log.info(
        "Confirmation %s for quote %s: inbox message %s %s",
        confirmation.id,
        quote.quote_id,
        message.id,
        message.status,
    )
    return ConfirmationRequestResponse(
        sent_to_masked=mask_phone(user.phone_e164),
        # Twilio is off for now (#46's Twilio items): `held` until the call ends, else `off`.
        delivery_status="held" if held else "off",
        inbox=True,
    )


async def call_in_progress(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> bool:
    """Whether a phone call of the user is still going on, so a new link waits for its end.

    A call is a relay-started phone session (`call_id`) that has not ended, active in the
    last `IDLE_TIMEOUT` (the call's tool calls find it the same way, and a call is shorter
    than that), so a session left open by a crash doesn't hold links forever.

    Locks those sessions until commit, which makes the hold race-free against the relay's
    `voice_calls.end_call()`, which locks the call's session before it releases: either
    the end of the call waits for this transaction and then releases the held message, or
    it has committed `ended_at` first and this query, waiting on the lock and then
    re-checking the row, no longer finds the call (#88).
    """
    now = now or datetime.now(UTC)
    calls = await db.scalars(
        select(OrderSession.id)
        .where(
            OrderSession.user_id == user_id,
            OrderSession.channel == "phone",
            OrderSession.call_id.is_not(None),
            OrderSession.ended_at.is_(None),
            OrderSession.last_activity_at > now - IDLE_TIMEOUT,
        )
        .order_by(OrderSession.id)
        .with_for_update()
    )
    return bool(calls.all())


async def record_inbox_delivered(
    db: AsyncSession, session_id: uuid.UUID, quote_id: uuid.UUID | str
) -> None:
    """`inbox_delivered`: a held link reached the demo phone."""
    await audit.record(
        db,
        type="inbox_delivered",
        actor="service",
        session_id=session_id,
        quote_id=quote_id,
        payload={"quote_id": str(quote_id), "path": "inbox"},
        text=Localized(
            fi="Vahvistuslinkki toimitettiin demopuhelimeen",
            en="The confirmation link was delivered to the demo phone",
        ),
    )


async def release_held_messages(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> list[str]:
    """Deliver the user's held messages to their inbox. For the voice relay (#52) at the
    end of a call: hang-up, a dropped call or the time limit. Not an agent tool.

    Returns the quote ids whose links were delivered, empty when nothing was held. Safe to
    call more than once.
    """
    now = now or datetime.now(UTC)
    rows = (
        await db.execute(
            select(SmsMessage, Confirmation.quote_id)
            .join(Confirmation, Confirmation.id == SmsMessage.confirmation_id)
            .where(
                SmsMessage.user_id == user_id,
                SmsMessage.path == "inbox",
                SmsMessage.status == "held",
            )
            .order_by(SmsMessage.created_at, SmsMessage.id)
            .with_for_update(of=SmsMessage)
        )
    ).all()
    for message, _ in rows:
        message.status = "delivered"
        message.delivered_at = now
        _publish_after_commit(db, message)
    await db.flush()
    if rows:
        log.info("Released %d held inbox message(s) for user %s", len(rows), user_id)
    return [quote_id for _, quote_id in rows]


async def inbox(db: AsyncSession, user_id: uuid.UUID) -> list[InboxMessage]:
    """The user's delivered inbox messages, oldest first. Held messages don't show yet."""
    messages = await db.scalars(
        select(SmsMessage)
        .where(
            SmsMessage.user_id == user_id,
            SmsMessage.path == "inbox",
            SmsMessage.status == "delivered",
        )
        .order_by(SmsMessage.delivered_at, SmsMessage.id)
    )
    return [_view(m) for m in messages]


def _view(message: SmsMessage) -> InboxMessage:
    return InboxMessage(
        id=str(message.id),
        at=message.delivered_at or message.created_at,
        text=message.text,
        link=message.link,
    )


# --- The per-user inbox stream ---
#
# One Broadcaster per user with a subscriber, in this process (uvicorn runs one worker,
# technical-plan.md §10.2). No redaction: the stream is the user's own phone, and the link
# is its content. It is never mixed with the public dashboard broadcaster.

_inboxes: dict[uuid.UUID, Broadcaster] = {}

_PENDING_KEY = "simo_inbox_pending"


def _no_redaction(data: Any) -> Any:
    return data


def _inbox_broadcaster(user_id: uuid.UUID) -> Broadcaster:
    broadcaster = _inboxes.get(user_id)
    if broadcaster is None:
        broadcaster = _inboxes[user_id] = Broadcaster(history_size=0, redactor=_no_redaction)
    return broadcaster


def publish_inbox_message(user_id: uuid.UUID, message: InboxMessage) -> None:
    """Send `inbox_message` to the user's open inbox streams, if any."""
    broadcaster = _inboxes.get(user_id)
    if broadcaster is not None:
        broadcaster.publish(StreamEvent(INBOX_MESSAGE_EVENT, message.model_dump(mode="json")))


async def inbox_events(
    user_id: uuid.UUID, snapshot: Callable[[], Awaitable[Any]]
) -> AsyncIterator[ServerSentEvent]:
    """The events of `GET /api/v1/private/inbox/stream` for one browser: a `snapshot` with
    the inbox so far, then an `inbox_message` for each new message."""
    broadcaster = _inbox_broadcaster(user_id)
    subscription = broadcaster.subscribe(snapshot)
    try:
        async for item in subscription:
            yield item
    finally:
        await subscription.aclose()
        if broadcaster.subscriber_count == 0 and _inboxes.get(user_id) is broadcaster:
            del _inboxes[user_id]


def _publish_after_commit(db: AsyncSession, message: SmsMessage) -> None:
    db.info.setdefault(_PENDING_KEY, []).append((message.user_id, _view(message)))


@event.listens_for(Session, "after_commit")
def _publish_pending(session: Session) -> None:
    for user_id, message in session.info.pop(_PENDING_KEY, []):
        publish_inbox_message(user_id, message)


@event.listens_for(Session, "after_soft_rollback")
def _drop_pending(session: Session, previous_transaction: Any) -> None:
    if previous_transaction.parent is None:  # the whole transaction, not a savepoint
        session.info.pop(_PENDING_KEY, None)
