"""Append events to the audit chain, with their dashboard pointers (#41, §8.5, §8.6).

`record()` checks an event and keeps it in the caller's database session; nothing is
written yet. Right before the session's transaction commits, `write_pending()` writes all
of them in one step, under the advisory lock that keeps the chain linear (#86). So:

- an event is stored exactly when the change it describes is, as before;
- an event recorded inside a savepoint that rolls back is dropped with it, and a rollback
  of the whole transaction drops them all;
- the lock is held for milliseconds, never across a Valio or Gemini call, and is always the
  last lock a transaction takes. Lock order everywhere (#87): confirmation, session, quote,
  then the audit lock, at commit. Code must not take the audit lock itself.

`seq` and the hashes are known only once the events are written. Tests and scripts that
need them call `await db.run_sync(write_pending)`, which takes the lock there and then.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from sqlalchemy import event, insert, select
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from app import telemetry
from app.models import AuditEvent, StatusEvent
from app.schemas import AuditEventType, Localized
from app.services.dashboard.redact import redact

from .chain import GENESIS_HASH, ChainFields, format_at, payload_hash

# Any fixed number, the same in every process: one lock for the whole chain.
ADVISORY_LOCK_KEY = 0x41_A0D1_7C4A
_LOCK = sql_text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=ADVISORY_LOCK_KEY)

# Where a session keeps its unwritten events: (transaction recorded in, event) pairs.
_PENDING = "audit_pending"


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


@dataclass(frozen=True)
class _Pending:
    """A checked event, waiting for its place in the chain."""

    at: datetime
    type: AuditEventType
    actor: str
    session_id: uuid.UUID | None
    quote_id: uuid.UUID | None
    payload: dict[str, Any]
    text_fi: str | None
    text_en: str | None
    payload_hash: str


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
) -> None:
    """Keep an event, to be appended with its `status_events` row when `db` commits.
    Raises `ValueError` for an unknown type or an empty actor and `PersonalDataError` for
    unmasked personal data, right away.

    `at` defaults to the real clock (not the business clock, technical-plan.md §4.1) at
    the time of the call, not of the commit.
    """
    event_type = AuditEventType(type)
    session_id, quote_id = _uuid(session_id), _uuid(quote_id)
    if not actor:
        raise ValueError("an audit event needs an actor")
    data = _json_ready(payload)
    text_fi, text_en = (text.fi, text.en) if text is not None else (None, None)
    _refuse_personal_data({"payload": data, "text_fi": text_fi, "text_en": text_en})

    await db.connection()  # begins the transaction if needed, so the commit hook runs
    sync = db.sync_session
    transaction = sync.get_nested_transaction() or sync.get_transaction()
    pending = _Pending(
        at=at or datetime.now(UTC),
        type=event_type,
        actor=actor,
        session_id=session_id,
        quote_id=quote_id,
        payload=data,
        text_fi=text_fi,
        text_en=text_en,
        payload_hash=payload_hash(data, text_fi, text_en),
    )
    sync.info.setdefault(_PENDING, []).append((transaction, pending))


def write_pending(session: Session) -> list[RecordedEvent]:
    """Append the session's kept events to the chain, in the order they were recorded.

    Runs from the commit hook below (synchronous, inside the async session's greenlet).
    Takes the advisory lock, held until the transaction ends."""
    events = [pending for _, pending in session.info.pop(_PENDING, [])]
    if not events:
        return []

    session.execute(_LOCK)
    last = session.execute(
        select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    seq, prev_hash = (last.seq, last.hash) if last else (0, GENESIS_HASH)
    session_ids = {e.session_id for e in events if e.session_id is not None}
    session_last: dict[uuid.UUID, str | None] = dict.fromkeys(session_ids)
    if session_ids:
        latest = session.execute(
            select(AuditEvent.session_id, AuditEvent.hash)
            .where(AuditEvent.session_id.in_(session_ids))
            .ext(distinct_on(AuditEvent.session_id))
            .order_by(AuditEvent.session_id, AuditEvent.seq.desc())
        )
        session_last.update({row.session_id: row.hash for row in latest})

    rows: list[dict[str, Any]] = []
    for pending in events:
        seq += 1
        session_prev_hash = session_last.get(pending.session_id) if pending.session_id else None
        fields = ChainFields(
            prev_hash=prev_hash,
            session_prev_hash=session_prev_hash,
            seq=seq,
            at=format_at(pending.at),
            type=pending.type.value,
            actor=pending.actor,
            session_id=_uuid_text(pending.session_id),
            quote_id=_uuid_text(pending.quote_id),
            payload_hash=pending.payload_hash,
        )
        prev_hash = fields.hash()
        if pending.session_id is not None:
            session_last[pending.session_id] = prev_hash
        rows.append(
            {
                "seq": seq,
                "at": pending.at,
                "type": pending.type.value,
                "actor": pending.actor,
                "session_id": pending.session_id,
                "quote_id": pending.quote_id,
                "payload": pending.payload,
                "text_fi": pending.text_fi,
                "text_en": pending.text_en,
                "payload_hash": pending.payload_hash,
                "prev_hash": fields.prev_hash,
                "session_prev_hash": session_prev_hash,
                "hash": prev_hash,
                "at_text": fields.at,
            }
        )

    session.execute(
        insert(AuditEvent).values([{k: v for k, v in r.items() if k != "at_text"} for r in rows])
    )
    # One statement, so the pointers' ids (and their NOTIFYs) follow `seq`.
    status_ids = dict(
        session.execute(
            insert(StatusEvent)
            .values(
                [
                    {
                        "audit_seq": r["seq"],
                        "session_id": r["session_id"],
                        "type": r["type"],
                        "at": r["at"],
                    }
                    for r in rows
                ]
            )
            .returning(StatusEvent.audit_seq, StatusEvent.id)
        ).all()
    )

    for r in rows:
        # A copy for Application Insights (#84): the row stays the record (hash chain);
        # this line puts the session's timeline next to its spans. Not the payload, only
        # its hash and the readable sentence (a transcript's text is already redacted).
        # Written just before the commit, so a commit that then fails can still leave one.
        telemetry.event(
            f"audit {r['type']}",
            audit_type=r["type"],
            actor=r["actor"],
            seq=r["seq"],
            hash=r["hash"],
            payload_hash=r["payload_hash"],
            session_id=_uuid_text(r["session_id"]),
            quote_id=_uuid_text(r["quote_id"]),
            text=r["text_en"],
        )
    return [
        RecordedEvent(
            seq=r["seq"],
            at=r["at"],
            at_text=r["at_text"],
            type=AuditEventType(r["type"]),
            session_id=r["session_id"],
            quote_id=r["quote_id"],
            payload_hash=r["payload_hash"],
            prev_hash=r["prev_hash"],
            session_prev_hash=r["session_prev_hash"],
            hash=r["hash"],
            status_event_id=status_ids[r["seq"]],
        )
        for r in rows
    ]


@event.listens_for(Session, "before_commit")
def _write_before_commit(session: Session) -> None:
    # Fires for a savepoint's commit too; its events wait for the outer commit.
    if not session.in_nested_transaction():
        write_pending(session)


@event.listens_for(Session, "after_soft_rollback")
def _drop_rolled_back(session: Session, rolled_back: SessionTransaction) -> None:
    """Drop the events recorded inside the rolled-back transaction or savepoint."""
    pending = session.info.get(_PENDING)
    if pending:
        session.info[_PENDING] = [
            (transaction, event_)
            for transaction, event_ in pending
            if not _inside(transaction, rolled_back)
        ]


@event.listens_for(Session, "after_transaction_end")
def _forget_on_end(session: Session, transaction: SessionTransaction) -> None:
    # The outer transaction is over (committed, rolled back or closed): nothing may carry
    # over into the next one.
    if not transaction.nested and transaction.parent is None:
        session.info.pop(_PENDING, None)


def _inside(transaction: SessionTransaction | None, outer: SessionTransaction) -> bool:
    while transaction is not None:
        if transaction is outer:
            return True
        transaction = transaction.parent
    return False


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
