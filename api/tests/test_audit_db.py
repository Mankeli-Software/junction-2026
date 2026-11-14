"""The audit writer, the append-only tables and the chain check, on a real Postgres (#41).

Each test runs in a transaction that is rolled back (`db` fixture), so every test starts
from an empty chain. Skipped without DATABASE_URL.
"""

import asyncio
import importlib.util
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app import engine
from app.schemas import AuditEventType, Localized
from app.services.audit import (
    PersonalDataError,
    check_chain,
    engine_input_from_payload,
    engine_input_payload,
    ensure_rule_set,
    load_rule_set_by_ref,
    record,
    verify_chain,
)
from app.services.audit.chain import GENESIS_HASH, ChainFields, format_at, payload_hash
from app.services.dashboard.listener import libpq_url
from tests.conftest import API_DIR, empty_audit_tables
from tests.engine_fixtures import engine_input

SESSION_A = uuid.UUID("5b0c7a3e-2f41-4d8e-9a6b-1c2d3e4f5a6b")
SESSION_B = uuid.UUID("0d9f7c1e-3a2b-4c5d-8e6f-7a8b9c0d1e2f")
QUOTE = uuid.UUID("8f14e45f-ceea-467a-9a6e-2b7c1d0e9f31")
T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
MIGRATION_0008 = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0008_audit_chain.py"
)


async def _session_events(db: AsyncSession) -> None:
    """Two interleaved sessions, five events: A, A, B, A, B."""
    plan = [
        (SESSION_A, AuditEventType.session_started, "relay", None),
        (SESSION_A, AuditEventType.buyer_said, "buyer", None),
        (SESSION_B, AuditEventType.session_started, "mcp", None),
        (SESSION_A, AuditEventType.quote_built, "engine", QUOTE),
        (SESSION_B, AuditEventType.tool_called, "mcp", None),
    ]
    for i, (session, kind, actor, quote) in enumerate(plan):
        await record(
            db,
            type=kind,
            actor=actor,
            payload={"step": i, "phone": "+358 40 *** **12", "price": 1.195},
            text=Localized(fi=f"Vaihe {i}", en=f"Step {i}"),
            session_id=session,
            quote_id=quote,
            at=T0 + timedelta(seconds=i, microseconds=7),
        )


async def _tamper(db: AsyncSession, sql: str, **params) -> None:
    """Change a row as someone with owner rights would: switch the guard off for it."""
    await db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only"))
    await db.execute(text(sql), params)
    await db.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only"))


async def test_events_chain_globally_and_per_session(db: AsyncSession):
    await _session_events(db)
    rows = (await db.execute(text("SELECT * FROM audit_events ORDER BY seq"))).mappings().all()

    assert [r["seq"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0]["prev_hash"] == GENESIS_HASH
    for before, after in zip(rows, rows[1:], strict=False):
        assert after["prev_hash"] == before["hash"]
    # Session links skip the other session's events.
    assert rows[0]["session_prev_hash"] is None
    assert rows[2]["session_prev_hash"] is None
    assert rows[3]["session_prev_hash"] == rows[1]["hash"]
    assert rows[4]["session_prev_hash"] == rows[2]["hash"]

    # The stored row hashes as docs/audit-chain.md says.
    row = rows[3]
    assert format_at(row["at"]) == "2026-11-14T10:00:03.000007Z"
    assert row["payload_hash"] == payload_hash(row["payload"], "Vaihe 3", "Step 3")
    fields = ChainFields(
        prev_hash=row["prev_hash"],
        session_prev_hash=row["session_prev_hash"],
        seq=4,
        at="2026-11-14T10:00:03.000007Z",
        type="quote_built",
        actor="engine",
        session_id=str(SESSION_A),
        quote_id=str(QUOTE),
        payload_hash=row["payload_hash"],
    )
    assert fields.hash() == row["hash"]

    status = (await db.execute(text("SELECT * FROM status_events ORDER BY id"))).mappings().all()
    assert [s["audit_seq"] for s in status] == [1, 2, 3, 4, 5]
    assert status[3]["session_id"] == SESSION_A and status[3]["type"] == "quote_built"

    assert (await verify_chain(db)).model_dump() == {
        "ok": True,
        "checked": 5,
        "first_bad_seq": None,
        "signature_valid": None,
    }
    assert (await verify_chain(db, SESSION_A)).checked == 3
    assert (await verify_chain(db, str(SESSION_B))).checked == 2


async def test_tampered_payload_fails_at_its_seq(db: AsyncSession):
    await _session_events(db)
    await _tamper(
        db, "UPDATE audit_events SET payload = jsonb_set(payload, '{price}', '0.5') WHERE seq = 4"
    )
    result = await check_chain(db)
    assert (result.ok, result.first_bad_seq, result.reason) == (False, 4, "payload_hash")
    assert (await verify_chain(db, SESSION_A)).first_bad_seq == 4
    # The other session doesn't contain the row and still checks.
    assert (await verify_chain(db, SESSION_B)).ok


async def test_tampered_text_fails_at_its_seq(db: AsyncSession):
    await _session_events(db)
    await _tamper(db, "UPDATE audit_events SET text_en = 'Step 9' WHERE seq = 2")
    assert (await check_chain(db)).first_bad_seq == 2


async def test_recomputed_payload_hash_still_breaks_the_hash(db: AsyncSession):
    await _session_events(db)
    payload = {"step": 1, "phone": "+358 40 *** **12", "price": 0.5}
    await _tamper(
        db,
        "UPDATE audit_events SET payload = CAST(:p AS jsonb), payload_hash = :h WHERE seq = 2",
        p='{"step": 1, "phone": "+358 40 *** **12", "price": 0.5}',
        h=payload_hash(payload, "Vaihe 1", "Step 1"),
    )
    result = await check_chain(db)
    assert (result.first_bad_seq, result.reason) == (2, "hash")


async def test_rewritten_hash_breaks_the_next_link(db: AsyncSession):
    await _session_events(db)
    await _tamper(db, "UPDATE audit_events SET hash = :h WHERE seq = 3", h="f" * 64)
    result = await check_chain(db)
    assert (result.first_bad_seq, result.reason) == (3, "hash")


async def test_deleted_row_breaks_the_chain(db: AsyncSession):
    await _session_events(db)
    await db.execute(text("ALTER TABLE status_events DISABLE TRIGGER status_events_append_only"))
    await db.execute(text("DELETE FROM status_events WHERE audit_seq = 3"))
    await _tamper(db, "DELETE FROM audit_events WHERE seq = 3")
    result = await check_chain(db)
    assert (result.first_bad_seq, result.reason) == (4, "seq_gap")
    assert (await check_chain(db, SESSION_B)).first_bad_seq == 5


async def test_moving_an_event_to_another_session_is_caught(db: AsyncSession):
    await _session_events(db)
    await _tamper(db, "UPDATE audit_events SET session_id = :b WHERE seq = 4", b=SESSION_B)
    assert (await check_chain(db)).first_bad_seq == 4


async def test_a_deleted_payload_keeps_the_chain(db: AsyncSession):
    await _session_events(db)
    await _tamper(
        db, "UPDATE audit_events SET payload = NULL, text_fi = NULL, text_en = NULL WHERE seq = 2"
    )
    assert (await check_chain(db)).ok


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET actor = 'x'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events CASCADE",
        "UPDATE status_events SET type = 'x'",
        "TRUNCATE status_events",
        "DELETE FROM rule_sets",
    ],
)
async def test_tables_are_append_only_even_for_the_owner(db: AsyncSession, statement: str):
    await _session_events(db)
    await ensure_rule_set(db, engine_input().rules)
    with pytest.raises(DBAPIError, match="append-only"):
        async with db.begin_nested():
            await db.execute(text(statement))


async def test_app_role_gets_only_insert_and_select(db: AsyncSession):
    spec = importlib.util.spec_from_file_location("migration_0008", MIGRATION_0008)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    role = "audit_app_test"
    await db.execute(text(f"CREATE ROLE {role}"))  # rolled back with the test
    await db.execute(text(migration.grant_append_only_sql(role)))
    await db.execute(text(f"SET LOCAL ROLE {role}"))
    await _session_events(db)  # INSERT and SELECT, status_events' identity included
    assert (await check_chain(db)).ok
    with pytest.raises(DBAPIError, match="permission denied"):
        async with db.begin_nested():
            await db.execute(text("UPDATE audit_events SET actor = 'x'"))


@pytest.mark.parametrize(
    ("payload", "sentence"),
    [
        ({"phone": "+358401234512"}, None),
        ({"nested": [{"note": "call +358 40 123 4512"}]}, None),
        ({"email": "jane.doe@example.com"}, None),
        ({"url": "https://simo.mankeli.co/c/abc123"}, None),
        ({"token": "abc"}, None),
        ({}, "Linkki lähetetty numeroon +358401234512"),
    ],
)
async def test_personal_data_is_refused(db: AsyncSession, payload: dict, sentence: str | None):
    with pytest.raises(PersonalDataError):
        await record(
            db,
            type=AuditEventType.sms_sent,
            actor="confirmation",
            payload=payload,
            text=Localized(fi=sentence, en="x") if sentence else None,
            session_id=SESSION_A,
        )
    count = (await db.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 0


async def test_masked_identities_are_accepted(db: AsyncSession):
    event = await record(
        db,
        type="customer_identified",
        actor="relay",
        payload={"identity_masked": "+358 40 *** **12", "email": "j***@example.com"},
        session_id=str(SESSION_A),
    )
    assert event.seq == 1 and event.session_id == SESSION_A


async def test_unknown_type_and_missing_actor_are_refused(db: AsyncSession):
    with pytest.raises(ValueError):
        await record(db, type="quote_bulit", actor="engine", payload={})
    with pytest.raises(ValueError):
        await record(db, type="quote_built", actor="", payload={})


async def test_rule_set_is_stored_once_with_its_event(db: AsyncSession):
    rules = engine_input().rules
    assert await ensure_rule_set(db, rules) is True
    assert await ensure_rule_set(db, rules) is False
    rows = (await db.execute(text("SELECT type, payload FROM audit_events"))).mappings().all()
    assert [r["type"] for r in rows] == ["rule_set_loaded"]
    assert rows[0]["payload"]["ref"] == rules.ref
    assert await load_rule_set_by_ref(db, rules.ref) == rules


async def test_engine_input_replays_from_the_audit_payload(db: AsyncSession):
    original = engine_input()
    payload = await engine_input_payload(db, original)
    assert "rules" not in payload and payload["rules_ref"] == original.rules.ref
    await record(
        db,
        type=AuditEventType.quote_built,
        actor="engine",
        payload={"engine_input": payload},
        session_id=SESSION_A,
        quote_id=QUOTE,
    )
    stored = (
        await db.execute(text("SELECT payload FROM audit_events WHERE type = 'quote_built'"))
    ).scalar_one()
    replayed = await engine_input_from_payload(db, stored["engine_input"])
    assert replayed == original
    assert engine.decide(replayed) == engine.decide(original)
    assert (await check_chain(db)).ok


async def test_edited_rules_row_is_refused_on_replay(db: AsyncSession):
    rules = engine_input().rules
    await ensure_rule_set(db, rules)
    await db.execute(text("ALTER TABLE rule_sets DISABLE TRIGGER rule_sets_append_only"))
    await db.execute(text("UPDATE rule_sets SET rules = jsonb_set(rules, '{version}', '\"x\"')"))
    with pytest.raises(ValueError, match="rules_hash"):
        await load_rule_set_by_ref(db, rules.ref)


async def test_status_event_sends_notify(db_engine: AsyncEngine):
    """Committed for real, since NOTIFY is delivered at commit; cleaned up afterwards."""
    url = db_engine.url.render_as_string(hide_password=False)
    async with await psycopg.AsyncConnection.connect(libpq_url(url), autocommit=True) as listen:
        await listen.execute("LISTEN status_events")
        try:
            async with AsyncSession(db_engine) as db, db.begin():
                event = await record(
                    db, type="session_started", actor="relay", payload={}, session_id=SESSION_A
                )
            notify = await asyncio.wait_for(anext(listen.notifies()), timeout=5)
            assert notify.channel == "status_events"
            assert notify.payload == str(event.status_event_id)
        finally:
            async with db_engine.begin() as conn:
                await empty_audit_tables(conn)


async def test_migration_chains_the_interim_rows(db_engine: AsyncEngine):
    """#45's unchained rows, with a gap in `seq`, become a valid chain from 1."""
    url = db_engine.url.set(database=f"{db_engine.url.database}_backfill")
    admin = create_async_engine(db_engine.url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    env = {
        **os.environ,
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "MIGRATION_DATABASE_URL": "",
    }

    def alembic(*args: str) -> None:
        subprocess.run(["alembic", *args], cwd=API_DIR, env=env, check=True)

    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(alembic, "upgrade", "0007")
        async with engine.begin() as conn:
            for i, session in enumerate([SESSION_A, SESSION_B, SESSION_A]):
                await conn.execute(
                    text(
                        "INSERT INTO audit_events "
                        "(type, actor, session_id, payload, text_fi, text_en, public) "
                        "VALUES ('tool_called', 'agent', :s, CAST(:p AS jsonb), 'fi', 'en', '{}')"
                    ),
                    {"s": session, "p": f'{{"n": {i}}}'},
                )
            # A rolled-back insert leaves a gap in the identity.
            await conn.execute(
                text("SELECT nextval(pg_get_serial_sequence('audit_events', 'seq'))")
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_events "
                    "(type, actor, session_id, payload, text_fi, text_en, public) "
                    "VALUES ('tool_returned', 'service', :s, '{}', 'fi', 'en', '{}')"
                ),
                {"s": SESSION_B},
            )
        await asyncio.to_thread(alembic, "upgrade", "head")

        async with AsyncSession(engine) as db:
            result = await check_chain(db)
            assert (result.ok, result.checked) == (True, 4)
            assert (await check_chain(db, SESSION_B)).checked == 2
            seqs = (await db.execute(text("SELECT audit_seq FROM status_events ORDER BY id"))).all()
            assert [s for (s,) in seqs] == [1, 2, 3, 4]
            # New events continue the chain.
            await record(db, type="session_ended", actor="relay", payload={}, session_id=SESSION_A)
            assert (await check_chain(db)).checked == 5
            await db.rollback()

        await asyncio.to_thread(alembic, "downgrade", "0007")
        await asyncio.to_thread(alembic, "upgrade", "head")
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        await admin.dispose()
