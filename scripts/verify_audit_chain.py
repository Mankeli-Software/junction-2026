"""Check the audit hash chain (#41, docs/audit-chain.md).

Usage, from api/:
    uv run python ../scripts/verify_audit_chain.py                  # the whole chain, DATABASE_URL
    uv run python ../scripts/verify_audit_chain.py --session <id>   # one session
    uv run python ../scripts/verify_audit_chain.py --file events.json
        # a session's events as the dashboard's "Download JSON" gives them, no database

Exits 0 when the chain is intact and 1 at the first broken event, which it names.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.services.audit.chain import (  # noqa: E402
    GENESIS_HASH,
    ChainCheck,
    ChainFields,
    StoredEvent,
    check_events,
)


async def check_database(session_id: str | None) -> ChainCheck:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db import get_engine
    from app.services.audit import check_chain

    async with AsyncSession(get_engine()) as db:
        result = await check_chain(db, session_id)
    await get_engine().dispose()
    return result


def check_file(path: Path) -> ChainCheck:
    """Downloaded events, usually one session's. Links to events outside the file can't be
    checked, so `prev_hash` is checked only where two events are next to each other."""
    events = json.loads(path.read_text())
    if isinstance(events, dict):
        events = events.get("events", [])
    stored = []
    previous = None
    last_in_session: dict[str, str] = {}
    for e in sorted(events, key=lambda e: e["seq"]):
        text = e.get("text") or {}
        adjacent = previous is not None and previous["seq"] == e["seq"] - 1
        stored.append(
            StoredEvent(
                fields=ChainFields(
                    prev_hash=e["prev_hash"],
                    session_prev_hash=e["session_prev_hash"],
                    seq=e["seq"],
                    at=e["at"],
                    type=e["type"],
                    actor=e["actor"],
                    session_id=e.get("session_id"),
                    quote_id=e.get("quote_id"),
                    payload_hash=e["payload_hash"],
                ),
                hash=e["hash"],
                payload=e.get("payload"),
                payload_deleted="payload" not in e or e["payload"] is None,
                text_fi=e.get("text_fi", text.get("fi")),
                text_en=e.get("text_en", text.get("en")),
                previous_seq=None if e["seq"] == 1 else e["seq"] - 1,
                expected_prev_hash=(
                    previous["hash"]
                    if adjacent
                    else GENESIS_HASH
                    if e["seq"] == 1
                    else e["prev_hash"]
                ),
                expected_session_prev_hash=last_in_session.get(e.get("session_id") or ""),
            )
        )
        previous = e
        if e.get("session_id"):
            last_in_session[e["session_id"]] = e["hash"]
    return check_events(stored)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--session", help="check only this session's events")
    source.add_argument("--file", type=Path, help="check a downloaded events JSON file")
    args = parser.parse_args()

    result = check_file(args.file) if args.file else asyncio.run(check_database(args.session))
    if result.ok:
        print(f"Audit chain intact: {result.checked} events checked.")
        return 0
    print(
        f"Audit chain BROKEN at seq {result.first_bad_seq} ({result.reason}), "
        f"after {result.checked - 1} good events."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
