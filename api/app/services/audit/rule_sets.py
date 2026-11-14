"""Each distinct rule set stored once, and engine inputs that point at it (#41).

The rules stay in `policy/` and in memory. For replay, `rule_sets` keeps a copy of every
rule set a quote was made with, and audit payloads carry `rules_ref` instead of the full
~20 KB `RuleSet`. The first use of a rule set writes a `rule_set_loaded` event with its
`rules_hash`, so the chain covers the stored rules too.

This happens on first use rather than at startup, so a transaction that writes a quote
always finds its rule set stored, and an API that starts without a database still starts.
"""

from datetime import UTC, datetime
from typing import Any

import rfc8785
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleSetRow
from app.schemas import AuditEventType, EngineInput, Localized
from app.schemas.rules import RuleSet

from .chain import sha256_hex
from .writer import record

REF_SEPARATOR = "+sha256:"


class UnknownRuleSetError(LookupError):
    """No stored rule set has this reference."""


def rules_hash(rules: dict[str, Any]) -> str:
    return sha256_hex(rfc8785.dumps(rules))


async def ensure_rule_set(db: AsyncSession, rule_set: RuleSet) -> bool:
    """Store the rule set unless it is there already. True when it was new, in which case
    a `rule_set_loaded` event was written in the same transaction."""
    rules = rule_set.model_dump(mode="json")
    digest = rules_hash(rules)
    inserted = (
        await db.execute(
            insert(RuleSetRow)
            .values(
                content_hash=rule_set.content_hash,
                version=rule_set.version,
                rules=rules,
                rules_hash=digest,
                loaded_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(RuleSetRow.content_hash)
        )
    ).scalar_one_or_none()
    if inserted is None:
        return False
    await record(
        db,
        type=AuditEventType.rule_set_loaded,
        actor="system",
        payload={
            "ref": rule_set.ref,
            "version": rule_set.version,
            "content_hash": rule_set.content_hash,
            "rules_hash": digest,
        },
        text=Localized(
            fi=f"Sääntöversio {rule_set.version} otettu käyttöön",
            en=f"Rule set {rule_set.version} in use",
        ),
    )
    return True


async def engine_input_payload(db: AsyncSession, engine_input: EngineInput) -> dict[str, Any]:
    """The engine input as stored in an audit payload: `rules_ref` in place of `rules`.

    Stores the rule set first if needed, so the reference always resolves."""
    await ensure_rule_set(db, engine_input.rules)
    data = engine_input.model_dump(mode="json", exclude={"rules"})
    data["rules_ref"] = engine_input.rules.ref
    return data


def parse_ref(ref: str) -> tuple[str, str]:
    """`<version>+sha256:<content_hash>` -> (version, content_hash)."""
    version, sep, content_hash = ref.rpartition(REF_SEPARATOR)
    if not sep or not version or len(content_hash) != 64:
        raise ValueError(f"not a rule set reference: {ref!r}")
    return version, content_hash


async def load_rule_set_by_ref(db: AsyncSession, ref: str) -> RuleSet:
    """The stored rule set for a reference. Raises `UnknownRuleSetError` when it isn't stored and
    `ValueError` when the stored rules no longer match their hash or the reference."""
    version, content_hash = parse_ref(ref)
    row = (
        await db.execute(select(RuleSetRow).where(RuleSetRow.content_hash == content_hash))
    ).scalar_one_or_none()
    if row is None:
        raise UnknownRuleSetError(f"rule set {ref} is not stored")
    if rules_hash(row.rules) != row.rules_hash:
        raise ValueError(f"stored rule set {ref} does not match its rules_hash")
    rule_set = RuleSet.model_validate(row.rules)
    if rule_set.ref != ref:
        raise ValueError(f"stored rule set is {rule_set.ref}, not {ref}")
    return rule_set


async def engine_input_from_payload(db: AsyncSession, payload: dict[str, Any]) -> EngineInput:
    """Rebuild the `EngineInput` from `engine_input_payload()` output, for replay."""
    data = dict(payload)
    rules = await load_rule_set_by_ref(db, data.pop("rules_ref"))
    return EngineInput.model_validate({**data, "rules": rules})
