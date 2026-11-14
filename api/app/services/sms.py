"""Real SMS through Twilio for a confirmation link (#46, technical-plan.md §8.2, §9.7).

Every link lands in the simulated phone inbox (`confirmations`). A real SMS goes out too,
as a `twilio` row next to the `inbox` row, only when:

- Twilio is enabled: `SMS_TWILIO_ENABLED` and all three Twilio settings (`twilio_enabled`);
- the recipient's number is on `SMS_ALLOWLIST`, so a typed number that belongs to a
  stranger never gets our SMS;
- the number has had fewer than `MAX_PER_HOUR` in the last hour (`call-screen.md` §6).
  Over the limit the link goes to the inbox only, and the log says so.

The network call never runs inside a database transaction or under a lock (#86). A row is
`held` while its call is on, and `pending` once committed; after the commit it is sent in
three steps: claim it (`sending`, one short transaction), call Twilio (no transaction),
record the result (one short transaction, with `sms_sent` or `sms_failed`). Twilio's
status callback (`POST /api/v1/twilio/status`) moves it on to `delivered` or `failed`.

The link is in the row's body and goes to Twilio, nowhere else: never into a log line, an
audit payload, an exception or the public stream. Numbers are logged masked.
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import event, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import Confirmation, OrderSession, Quote, SmsMessage
from app.schemas import Localized
from app.schemas.dashboard import SessionState
from app.settings import get_settings

from . import audit, sessions, twilio
from .phone import mask_phone

log = logging.getLogger(__name__)

MAX_PER_HOUR = 3
LIMIT_WINDOW = timedelta(hours=1)
STATUS_CALLBACK_PATH = "/api/v1/twilio/status"
# How long the end of a call waits for Twilio's answer before it reports `sent` (queued).
WAIT_S = 6.0

# A status only moves forward. `delivered` and `failed` are final.
_RANK = {
    "held": 0,
    "pending": 1,
    "sending": 2,
    "queued": 3,
    "sent": 4,
    "delivered": 5,
    "failed": 5,
}
FINAL = frozenset({"delivered", "failed"})

# One request at a time per number while it counts against the limit. Two-key advisory
# locks, with a class of their own, so they never meet the audit chain's lock.
_LIMIT_LOCK = sql_text("SELECT pg_advisory_xact_lock(CAST(:cls AS integer), CAST(:key AS integer))")
_LIMIT_LOCK_CLASS = 46

DeliveryStatus = Literal["held", "sent", "failed", "off"]


def status_callback_url() -> str:
    """Where Twilio reports delivery, and the URL its signatures are made over."""
    return get_settings().public_base_url + STATUS_CALLBACK_PATH


def delivery_status(status: str) -> DeliveryStatus:
    """A `twilio` row's status as `delivery_status` (`ConfirmationRequestResponse`, and the
    relay's `ended` message): queued counts as sent."""
    if status == "held":
        return "held"
    return "failed" if status == "failed" else "sent"


async def add_twilio_message(
    db: AsyncSession,
    confirmation: Confirmation,
    *,
    body: str,
    text: str,
    link: str,
    held: bool,
    now: datetime,
) -> SmsMessage | None:
    """The `twilio` row for a new confirmation, or None when its link goes to the inbox
    only. A row that isn't held is sent once `db` commits."""
    settings = get_settings()
    number = confirmation.recipient_e164
    if not settings.twilio_enabled or number not in settings.sms_allowlist_numbers:
        return None
    await db.execute(_LIMIT_LOCK, {"cls": _LIMIT_LOCK_CLASS, "key": _lock_key(number)})
    recent = await db.scalar(
        select(func.count())
        .select_from(SmsMessage)
        .join(Confirmation, Confirmation.id == SmsMessage.confirmation_id)
        .where(
            SmsMessage.path == "twilio",
            Confirmation.recipient_e164 == number,
            SmsMessage.created_at > now - LIMIT_WINDOW,
        )
    )
    if (recent or 0) >= MAX_PER_HOUR:
        log.warning(
            "SMS limit reached for %s (%d in the last hour): confirmation %s goes to the "
            "inbox only",
            mask_phone(number),
            recent,
            confirmation.id,
        )
        return None
    message = SmsMessage(
        confirmation_id=confirmation.id,
        user_id=confirmation.user_id,
        path="twilio",
        status="held" if held else "pending",
        body=body,
        text=text,
        link=link,
        created_at=now,
    )
    db.add(message)
    await db.flush()
    if not held:
        _send_after_commit(db, message.id)
    return message


async def release_held(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """At the end of the user's call: their held `twilio` rows become `pending` and are
    sent once `db` commits. Returns their ids."""
    messages = list(
        await db.scalars(
            select(SmsMessage)
            .where(
                SmsMessage.user_id == user_id,
                SmsMessage.path == "twilio",
                SmsMessage.status == "held",
            )
            .order_by(SmsMessage.created_at, SmsMessage.id)
            .with_for_update()
        )
    )
    for message in messages:
        message.status = "pending"
        _send_after_commit(db, message.id)
    await db.flush()
    return [m.id for m in messages]


async def delivery_status_for_quote(quote_id: str) -> Literal["sent", "failed", "off"]:
    """After the end of a call has committed: how the link of `quote_id` went by SMS.

    `off` when no SMS goes out for it. Waits up to `WAIT_S` for Twilio's answer to a
    message on its way, and then counts it as sent (queued)."""
    async with get_sessionmaker()() as db:
        row = (
            await db.execute(
                select(SmsMessage.id, SmsMessage.status)
                .join(Confirmation, Confirmation.id == SmsMessage.confirmation_id)
                .where(Confirmation.quote_id == str(quote_id), SmsMessage.path == "twilio")
                .order_by(SmsMessage.created_at.desc(), SmsMessage.id.desc())
                .limit(1)
            )
        ).first()
    if row is None:
        return "off"
    status = row.status
    if status in ("pending", "sending"):
        task = _start(row.id)
        if task is not None:
            try:
                status = await asyncio.wait_for(asyncio.shield(task), WAIT_S)
            except TimeoutError:
                status = "queued"
    if status == "held":  # not released by the end of the call, so nothing went out
        return "off"
    return "failed" if status == "failed" else "sent"


# --- Sending, after the commit ----------------------------------------------------------

_SEND_KEY = "simo_sms_pending"
_tasks: dict[uuid.UUID, asyncio.Task[str]] = {}


def _send_after_commit(db: AsyncSession, message_id: uuid.UUID) -> None:
    db.info.setdefault(_SEND_KEY, []).append(message_id)


@event.listens_for(Session, "after_commit")
def _send_pending(session: Session) -> None:
    for message_id in session.info.pop(_SEND_KEY, []):
        _start(message_id)


@event.listens_for(Session, "after_soft_rollback")
def _drop_pending(session: Session, previous_transaction: object) -> None:
    if getattr(previous_transaction, "parent", None) is None:
        session.info.pop(_SEND_KEY, None)


def _start(message_id: uuid.UUID) -> asyncio.Task[str] | None:
    """The task that sends the message, started if it isn't running yet."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.warning("SMS %s is pending, but there is no event loop to send it", message_id)
        return None
    task = _tasks.get(message_id)
    if task is not None and not task.done() and task.get_loop() is loop:
        return task
    task = loop.create_task(_send(message_id), name=f"sms {message_id}")
    _tasks[message_id] = task

    def forget(done: asyncio.Task[str]) -> None:
        if _tasks.get(message_id) is done:
            del _tasks[message_id]

    task.add_done_callback(forget)
    return task


async def wait_for_sending() -> None:
    """Wait for every message on its way (tests, and a clean shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks.values()), return_exceptions=True)


async def _send(message_id: uuid.UUID) -> str:
    """Send one pending message: claim, call Twilio, record. Returns its status. Never
    raises, and logs only ids, masked numbers, HTTP statuses and Twilio's error codes."""
    try:
        claimed = await _claim(message_id)
        if claimed is None:
            return await _current_status(message_id)
        to, body = claimed
        try:
            sent = await twilio.send_sms(to=to, body=body, status_callback=status_callback_url())
        except twilio.TwilioError as error:
            log.warning("Twilio refused SMS %s to %s: %s", message_id, mask_phone(to), error)
            return await _record(message_id, "failed", error_code=error.code)
        log.info("SMS %s to %s: %s", message_id, mask_phone(to), sent.status)
        return await _record(message_id, sent.status, sid=sent.sid)
    except Exception as error:
        # Not the exception text: a database error may carry statement parameters (#89).
        log.error("Sending SMS %s failed: %s", message_id, type(error).__name__)
        return "failed"


async def _claim(message_id: uuid.UUID) -> tuple[str, str] | None:
    """`pending` -> `sending`, so only one sender ever sends it. The recipient and the
    body, or None when it isn't pending (sent already, or another task has it)."""
    async with get_sessionmaker()() as db, db.begin():
        row = (
            await db.execute(
                select(SmsMessage, Confirmation.recipient_e164)
                .join(Confirmation, Confirmation.id == SmsMessage.confirmation_id)
                .where(SmsMessage.id == message_id, SmsMessage.path == "twilio")
                .with_for_update(of=SmsMessage)
            )
        ).first()
        if row is None or row.SmsMessage.status != "pending":
            return None
        row.SmsMessage.status = "sending"
        return row.recipient_e164, row.SmsMessage.body


async def _current_status(message_id: uuid.UUID) -> str:
    async with get_sessionmaker()() as db:
        status = await db.scalar(select(SmsMessage.status).where(SmsMessage.id == message_id))
    return status or "failed"


async def _record(
    message_id: uuid.UUID, status: str, *, sid: str | None = None, error_code: str | None = None
) -> str:
    async with get_sessionmaker()() as db, db.begin():
        message = await db.get_one(SmsMessage, message_id)
        await update_status(db, message, status, sid=sid, error_code=error_code)
        return message.status


async def record_status_callback(
    db: AsyncSession, sid: str, twilio_status: str, error_code: str | None
) -> bool:
    """Twilio's status callback for message `sid`. False when it changes nothing: an
    unknown sid or status, or a status the message is already past."""
    status = twilio.STATUSES.get(twilio_status)
    if status is None:
        return False
    message = await db.scalar(select(SmsMessage).where(SmsMessage.twilio_sid == sid))
    if message is None:
        log.info("Twilio status %s for an SMS we don't know", twilio_status)
        return False
    return await update_status(db, message, status, error_code=error_code)


async def update_status(
    db: AsyncSession,
    message: SmsMessage,
    status: str,
    *,
    sid: str | None = None,
    error_code: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Move a `twilio` row on to `status`, with its audit event: `sms_sent` when Twilio
    took it, `sms_delivered`, or `sms_failed`, which also shows on the dashboard as the
    session's `sms_failed` state while it waits for confirmation. The inbox message stays,
    so the buyer can still confirm. False when the row is already there or past it."""
    now = now or datetime.now(UTC)
    confirmation = await db.get_one(Confirmation, message.confirmation_id)
    quote_id = sessions.parse_uuid(confirmation.quote_id)
    quote = await db.get(Quote, quote_id) if quote_id else None
    # Lock order (#87): the session, then the message.
    session = (
        await db.get(OrderSession, quote.session_id, with_for_update=True)
        if quote is not None and status == "failed"
        else None
    )
    await db.refresh(message, with_for_update=True)
    if sid is not None:
        message.twilio_sid = sid
    if message.status in FINAL or _RANK[status] <= _RANK[message.status]:
        await db.flush()
        return False
    first_answer = message.status in ("pending", "sending")
    message.status = status
    if error_code is not None:
        message.error_code = error_code
    if status == "delivered":
        message.delivered_at = now
    if session is not None and session.state == SessionState.awaiting_confirmation:
        sessions.set_state(session, SessionState.sms_failed, now)
    await db.flush()

    masked = mask_phone(confirmation.recipient_e164)
    payload: dict[str, object] = {
        "quote_id": confirmation.quote_id,
        "path": "twilio",
        "sent_to_masked": masked,
        "status": status,
    }
    if status == "failed":
        payload["error_code"] = message.error_code
        event_type, text = (
            "sms_failed",
            Localized(
                fi=f"Tekstiviesti numeroon {masked} epäonnistui; linkki on demopuhelimessa",
                en=f"The SMS to {masked} failed; the link is in the demo phone",
            ),
        )
    elif status == "delivered":
        event_type, text = (
            "sms_delivered",
            Localized(
                fi=f"Tekstiviesti toimitettiin numeroon {masked}",
                en=f"The SMS was delivered to {masked}",
            ),
        )
    elif first_answer:
        event_type, text = (
            "sms_sent",
            Localized(
                fi=f"Vahvistuslinkki lähetettiin tekstiviestinä numeroon {masked}",
                en=f"The confirmation link was sent by SMS to {masked}",
            ),
        )
    else:
        return True  # queued -> sent: no event of its own
    await audit.record(
        db,
        type=event_type,
        actor="service",
        session_id=quote.session_id if quote is not None else None,
        quote_id=quote_id,
        payload=payload,
        text=text,
        at=now,
    )
    return True


def _lock_key(number: str) -> int:
    """A 32-bit key for the number's limit lock. The number itself stays out of the
    statement's parameters."""
    return int.from_bytes(hashlib.sha256(number.encode()).digest()[:4], "big", signed=True)
