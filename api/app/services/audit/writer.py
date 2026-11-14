"""Append one event to the audit chain, with its dashboard pointer (#41, §8.5, §8.6).

`record()` runs inside the caller's transaction and never commits, so an event is
stored exactly when the change it describes is. The advisory lock keeps the chain linear
and is released at commit or rollback.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from sqlalchemy import insert, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app import telemetry
from app.models import AuditEvent, StatusEvent
from app.schemas import AuditEventType, Localized
from app.services.dashboard.redact import redact

from .chain import GENESIS_HASH, ChainFields, format_at, payload_hash

# Any fixed number, the same in every process: one lock for the whole chain.
ADVISORY_LOCK_KEY = 0x41_A0D1_7C4A
_LOCK = sql_text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=ADVISORY_LOCK_KEY)


class PersonalDataError(ValueError):
    """The event holds a full phone number, an email, a confirmation link or a secret key.

    Events are written with masked identities only (technical-plan.md §8.5)."""


@dataclass(frozen=True)
class RecordedEvent:
    seq: int
    at: datetime
    at_text: str  # the exact hashed string
    type: AuditEventType
    session_id: uuid.UUID | None
    quote_id: uuid.UUID | None
    payload_hash: str
    prev_hash: str
    session_prev_hash: str | None
    hash: str
    status_event_id: int


async def record(
    db: AsyncSession,
    *,
    type: AuditEventType | str,
    actor: str,
    payload: BaseModel | dict[str, Any],
    text: Localized | None = None,
    session_id: uuid.UUID | str | None = None,
    quote_id: uuid.UUID | str | None = None,
    at: datetime | None = None,
) -> RecordedEvent:
    """Append an event and its `status_events` row. Raises `ValueError` for an unknown type
    or an empty actor and `PersonalDataError` for unmasked personal data, before writing.

    `at` defaults to the real clock (not the business clock, technical-plan.md §4.1).
    """
    event_type = AuditEventType(type)
    session_id, quote_id = _uuid(session_id), _uuid(quote_id)
    if not actor:
        raise ValueError("an audit event needs an actor")
    data = _json_ready(payload)
    text_fi, text_en = (text.fi, text.en) if text is not None else (None, None)
    _refuse_personal_data({"payload": data, "text_fi": text_fi, "text_en": text_en})

    when = at or datetime.now(UTC)
    at_text = format_at(when)
    digest = payload_hash(data, text_fi, text_en)

    await db.execute(_LOCK)
    last = (
        await db.execute(
            select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
        )
    ).first()
    seq, prev_hash = (last.seq + 1, last.hash) if last else (1, GENESIS_HASH)
    session_prev_hash = None
    if session_id is not None:
        session_prev_hash = (
            await db.execute(
                select(AuditEvent.hash)
                .where(AuditEvent.session_id == session_id)
                .order_by(AuditEvent.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    fields = ChainFields(
        prev_hash=prev_hash,
        session_prev_hash=session_prev_hash,
        seq=seq,
        at=at_text,
        type=event_type.value,
        actor=actor,
        session_id=_uuid_text(session_id),
        quote_id=_uuid_text(quote_id),
        payload_hash=digest,
    )
    event_hash = fields.hash()

    await db.execute(
        insert(AuditEvent).values(
            seq=seq,
            at=when,
            type=event_type.value,
            actor=actor,
            session_id=session_id,
            quote_id=quote_id,
            payload=data,
            text_fi=text_fi,
            text_en=text_en,
            payload_hash=digest,
            prev_hash=prev_hash,
            session_prev_hash=session_prev_hash,
            hash=event_hash,
        )
    )
    status_id = (
        await db.execute(
            insert(StatusEvent)
            .values(audit_seq=seq, session_id=session_id, type=event_type.value, at=when)
            .returning(StatusEvent.id)
        )
    ).scalar_one()

    # A copy for Application Insights (#84): the row above stays the record (hash chain);
    # this line puts the session's timeline next to its spans. Not the payload, only its hash
    # and the readable sentence (a transcript's text is already redacted). Written inside the
    # transaction, so a rolled-back event can still appear here; `seq` and `hash` tell.
    telemetry.event(
        f"audit {event_type.value}",
        audit_type=event_type.value,
        actor=actor,
        seq=seq,
        hash=event_hash,
        payload_hash=digest,
        session_id=_uuid_text(session_id),
        quote_id=_uuid_text(quote_id),
        text=text_en,
    )

    return RecordedEvent(
        seq=seq,
        at=when,
        at_text=at_text,
        type=event_type,
        session_id=session_id,
        quote_id=quote_id,
        payload_hash=digest,
        prev_hash=prev_hash,
        session_prev_hash=session_prev_hash,
        hash=event_hash,
        status_event_id=status_id,
    )


def _json_ready(payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    data = to_jsonable_python(payload)
    if not isinstance(data, dict):
        raise ValueError("an audit payload must be a JSON object")
    return data


def _uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def _uuid_text(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def _refuse_personal_data(content: dict[str, Any]) -> None:
    """The dashboard's redaction must find nothing to change: no full phone number or
    email, no `/c/<token>` path, no token, link or cookie key."""
    if redact(content) != content:
        raise PersonalDataError(
            "audit events may hold only masked phone numbers and emails, and never a "
            "confirmation token or link"
        )
