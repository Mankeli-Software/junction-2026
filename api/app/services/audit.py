"""The audit log writer. Interim: plain rows in `audit_events`, without the hash chain.

`record()` is the interface the services call (#45); #41 (Aku) replaces the body with the
chained writer (advisory lock, `payload_hash`, `prev_hash`, `session_prev_hash`, `hash`,
the `status_events` row) and keeps the signature. Every call site already passes what the
chain needs, so nothing else changes when it lands.

The payload is stored as given and is public on the dashboard (technical-plan.md §9.5):
never put a confirmation token or link, a full phone number or a full email in it.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent
from app.schemas import Localized

log = logging.getLogger(__name__)


async def record(
    db: AsyncSession,
    *,
    type: str,
    actor: str,
    session_id: uuid.UUID,
    quote_id: uuid.UUID | None,
    payload: dict[str, Any],
    text: Localized,
    public: dict[str, Any],
) -> None:
    """Append one event in the caller's transaction, so it commits or rolls back with it."""
    db.add(
        AuditEvent(
            type=type,
            actor=actor,
            session_id=session_id,
            quote_id=quote_id,
            payload=payload,
            text_fi=text.fi,
            text_en=text.en,
            public=public,
        )
    )
    await db.flush()
    log.debug("audit %s session=%s quote=%s", type, session_id, quote_id)
