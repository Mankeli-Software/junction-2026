"""The audit chain's hash and check, with no database (#41, docs/audit-chain.md).

Change the byte format only together with docs/audit-chain.md, docs/audit-chain-vectors.json
and the browser's copy in `web/src/lib/dashboard/hash.ts`.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import rfc8785

# `prev_hash` of the first event in the global chain.
GENESIS_HASH = "0" * 64


def format_at(at: datetime) -> str:
    """The hashed form of a timestamp: UTC, six fractional digits, `Z`.

    `2026-11-14T10:23:45.123456Z`. Postgres `timestamptz` keeps microseconds, so a value
    read back from the database gives the same string.
    """
    if at.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_hash(payload: Any, text_fi: str | None, text_en: str | None) -> str:
    """SHA-256 over the RFC 8785 canonical JSON of the payload and both sentences."""
    document = {"payload": payload, "text_fi": text_fi, "text_en": text_en}
    return sha256_hex(rfc8785.dumps(document))


@dataclass(frozen=True)
class ChainFields:
    """Everything `hash` covers, in its order. The payload is in via `payload_hash`."""

    prev_hash: str
    session_prev_hash: str | None
    seq: int
    at: str  # `format_at()` output
    type: str
    actor: str
    session_id: str | None  # lowercase UUID with hyphens
    quote_id: str | None
    payload_hash: str

    def hash_input(self) -> bytes:
        parts = (
            self.prev_hash,
            self.session_prev_hash,
            str(self.seq),
            self.at,
            self.type,
            self.actor,
            self.session_id,
            self.quote_id,
            self.payload_hash,
        )
        return "\n".join("" if part is None else part for part in parts).encode("utf-8")

    def hash(self) -> str:
        return sha256_hex(self.hash_input())


@dataclass(frozen=True)
class StoredEvent:
    """One `audit_events` row, with what the rows before it say it should link to.

    `expected_prev_hash` is the hash of the row just before it in `seq` order, or
    `GENESIS_HASH` when there is none; `previous_seq` is that row's `seq` (None for none).
    `expected_session_prev_hash` is the hash of the session's previous row, or None.
    """

    fields: ChainFields
    hash: str
    payload: Any
    payload_deleted: bool  # the payload and texts were removed after the event
    text_fi: str | None
    text_en: str | None
    previous_seq: int | None
    expected_prev_hash: str
    expected_session_prev_hash: str | None


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    first_bad_seq: int | None
    reason: str | None  # seq_gap, prev_hash, session_prev_hash, payload_hash or hash


def check_events(events: Iterable[StoredEvent]) -> ChainCheck:
    """Check rows in `seq` order and stop at the first one that is wrong."""
    checked = 0
    for event in events:
        checked += 1
        reason = _problem(event)
        if reason is not None:
            return ChainCheck(False, checked, event.fields.seq, reason)
    return ChainCheck(True, checked, None, None)


def _problem(event: StoredEvent) -> str | None:
    f = event.fields
    expected_previous_seq = None if f.seq == 1 else f.seq - 1
    if event.previous_seq != expected_previous_seq:
        return "seq_gap"
    if f.prev_hash != event.expected_prev_hash:
        return "prev_hash"
    if f.session_prev_hash != event.expected_session_prev_hash:
        return "session_prev_hash"
    if not event.payload_deleted and f.payload_hash != payload_hash(
        event.payload, event.text_fi, event.text_en
    ):
        return "payload_hash"
    if f.hash() != event.hash:
        return "hash"
    return None
