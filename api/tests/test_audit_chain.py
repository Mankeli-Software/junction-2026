"""The audit chain's hash format against the shared vectors (docs/audit-chain.md)."""

import hashlib
import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.audit.chain import (
    GENESIS_HASH,
    ChainFields,
    StoredEvent,
    check_events,
    format_at,
    payload_hash,
)

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "audit-chain-vectors.json").read_text()
)


def _fields(event: dict) -> ChainFields:
    return ChainFields(
        prev_hash=event["prev_hash"],
        session_prev_hash=event["session_prev_hash"],
        seq=event["seq"],
        at=event["at"],
        type=event["type"],
        actor=event["actor"],
        session_id=event["session_id"],
        quote_id=event["quote_id"],
        payload_hash=event["payload_hash"],
    )


@pytest.mark.parametrize("event", VECTORS["events"], ids=lambda e: f"seq{e['seq']}")
def test_vectors(event: dict):
    expected = event["payload_hash"]
    assert payload_hash(event["payload"], event["text_fi"], event["text_en"]) == expected
    fields = _fields(event)
    assert fields.hash_input().decode() == event["hash_input"]
    assert fields.hash() == event["hash"]
    # Written out by hand, as docs/audit-chain.md says.
    by_hand = "\n".join(
        "" if event[k] is None else str(event[k])
        for k in (
            "prev_hash",
            "session_prev_hash",
            "seq",
            "at",
            "type",
            "actor",
            "session_id",
            "quote_id",
            "payload_hash",
        )
    )
    assert hashlib.sha256(by_hand.encode()).hexdigest() == event["hash"]


def test_vectors_form_a_chain():
    events = VECTORS["events"]
    assert VECTORS["genesis_hash"] == GENESIS_HASH
    assert events[0]["prev_hash"] == GENESIS_HASH
    for before, after in zip(events, events[1:], strict=False):
        assert after["prev_hash"] == before["hash"]


def test_format_at_is_utc_with_microseconds():
    helsinki = timezone(timedelta(hours=2))
    assert format_at(datetime(2026, 11, 14, 12, 0, tzinfo=helsinki)) == (
        "2026-11-14T10:00:00.000000Z"
    )
    assert format_at(datetime(2026, 11, 14, 10, 0, 0, 5, tzinfo=UTC)) == (
        "2026-11-14T10:00:00.000005Z"
    )
    with pytest.raises(ValueError):
        format_at(datetime(2026, 11, 14, 10, 0))


def test_payload_hash_ignores_key_order_and_covers_texts():
    a = payload_hash({"a": 1, "b": [1.5, "ä"]}, "fi", "en")
    assert a == payload_hash({"b": [1.5, "ä"], "a": 1}, "fi", "en")
    assert a != payload_hash({"a": 1, "b": [1.5, "ä"]}, "fi", "en, edited")


def _stored() -> list[StoredEvent]:
    out = []
    last_in_session: dict[str, str] = {}
    previous: dict | None = None
    for event in VECTORS["events"]:
        sid = event["session_id"]
        out.append(
            StoredEvent(
                fields=_fields(event),
                hash=event["hash"],
                payload=event["payload"],
                payload_deleted=False,
                text_fi=event["text_fi"],
                text_en=event["text_en"],
                previous_seq=previous["seq"] if previous else None,
                expected_prev_hash=previous["hash"] if previous else GENESIS_HASH,
                expected_session_prev_hash=last_in_session.get(sid) if sid else None,
            )
        )
        previous = event
        if sid:
            last_in_session[sid] = event["hash"]
    return out


def test_check_passes_on_the_vectors():
    result = check_events(_stored())
    assert (result.ok, result.checked, result.first_bad_seq) == (True, 3, None)


@pytest.mark.parametrize(
    ("index", "change", "reason"),
    [
        (1, {"payload": {"text": "Sata litraa", "lang": "fi", "transcript": True}}, "payload_hash"),
        (1, {"text_en": "Buyer: something else"}, "payload_hash"),
        (2, {"hash": "f" * 64}, "hash"),
        (2, {"previous_seq": 1}, "seq_gap"),
        (1, {"expected_prev_hash": "e" * 64}, "prev_hash"),
        (2, {"expected_session_prev_hash": None}, "session_prev_hash"),
    ],
)
def test_check_stops_at_the_tampered_event(index: int, change: dict, reason: str):
    events = _stored()
    events[index] = replace(events[index], **change)
    result = check_events(events)
    assert not result.ok
    assert result.first_bad_seq == events[index].fields.seq
    assert result.reason == reason
    assert result.checked == index + 1


def test_a_deleted_payload_still_checks():
    events = _stored()
    events[1] = replace(events[1], payload=None, text_fi=None, text_en=None, payload_deleted=True)
    assert check_events(events).ok


def test_tampering_another_field_breaks_the_hash():
    events = _stored()
    fields = replace(events[2].fields, actor="agent")
    events[2] = replace(events[2], fields=fields)
    result = check_events(events)
    assert (result.first_bad_seq, result.reason) == (3, "hash")


def _script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "verify_audit_chain.py"
    spec = importlib.util.spec_from_file_location("verify_audit_chain", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_checks_a_downloaded_file(tmp_path: Path):
    script = _script()
    events = VECTORS["events"]
    good = tmp_path / "good.json"
    good.write_text(json.dumps(events))
    assert script.check_file(good).ok

    # Only the session's events, as the dashboard's download gives them.
    session = tmp_path / "session.json"
    session.write_text(json.dumps(events[1:]))
    assert script.check_file(session).ok

    tampered = [dict(e) for e in events]
    tampered[2]["payload"] = {**tampered[2]["payload"], "total_cents": 1}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(tampered))
    result = script.check_file(bad)
    assert (result.ok, result.first_bad_seq) == (False, 3)
