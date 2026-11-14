"""Check the stored audit chain, globally or for one session (#41, docs/audit-chain.md).

The dashboard's `GET /api/v1/public/audit/verify` and `scripts/verify_audit_chain.py` call
this. Each row is compared with its neighbours as the table holds them, so a changed,
deleted or inserted row shows up at the first `seq` that no longer fits.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import VerifyResult

from .chain import GENESIS_HASH, ChainCheck, ChainFields, StoredEvent, check_events, format_at

# The links are computed over the whole table, so a session's rows are checked against
# their real neighbours in the global chain too.
_ROWS = """
SELECT * FROM (
    SELECT
        e.*,
        lag(e.seq) OVER (ORDER BY e.seq) AS previous_seq,
        lag(e.hash) OVER (ORDER BY e.seq) AS expected_prev_hash,
        CASE WHEN e.session_id IS NULL THEN NULL
             ELSE lag(e.hash) OVER (PARTITION BY e.session_id ORDER BY e.seq)
        END AS expected_session_prev_hash
    FROM audit_events e
) linked
{where}
ORDER BY seq
"""


async def check_chain(db: AsyncSession, session_id: uuid.UUID | str | None = None) -> ChainCheck:
    """Check every event, or only the session's events when `session_id` is given."""
    if session_id is None:
        statement = text(_ROWS.format(where=""))
    else:
        sid = session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(session_id)
        statement = text(_ROWS.format(where="WHERE session_id = :sid")).bindparams(sid=sid)
    rows = (await db.execute(statement)).mappings()
    return check_events(_stored(row) for row in rows)


async def verify_chain(db: AsyncSession, session_id: uuid.UUID | str | None = None) -> VerifyResult:
    """`check_chain()` in the dashboard's shape. `signature_valid` belongs to a quote, so it
    is null here; the dashboard fills it for a session's current quote (#40)."""
    result = await check_chain(db, session_id)
    return VerifyResult(
        ok=result.ok,
        checked=result.checked,
        first_bad_seq=result.first_bad_seq,
        signature_valid=None,
    )


def _stored(row) -> StoredEvent:
    return StoredEvent(
        fields=ChainFields(
            prev_hash=row["prev_hash"],
            session_prev_hash=row["session_prev_hash"],
            seq=row["seq"],
            at=format_at(row["at"]),
            type=row["type"],
            actor=row["actor"],
            session_id=None if row["session_id"] is None else str(row["session_id"]),
            quote_id=None if row["quote_id"] is None else str(row["quote_id"]),
            payload_hash=row["payload_hash"],
        ),
        hash=row["hash"],
        payload=row["payload"],
        payload_deleted=row["payload"] is None,
        text_fi=row["text_fi"],
        text_en=row["text_en"],
        previous_seq=row["previous_seq"],
        expected_prev_hash=row["expected_prev_hash"] or GENESIS_HASH,
        expected_session_prev_hash=row["expected_session_prev_hash"],
    )
