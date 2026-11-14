"""The hash-chained audit log (#41, technical-plan.md §8.5, docs/audit-chain.md)."""

from .chain import GENESIS_HASH, ChainCheck
from .rule_sets import (
    UnknownRuleSetError,
    engine_input_from_payload,
    engine_input_payload,
    ensure_rule_set,
    load_rule_set_by_ref,
)
from .verify import check_chain, verify_chain
from .writer import PersonalDataError, RecordedEvent, record

__all__ = [
    "GENESIS_HASH",
    "ChainCheck",
    "PersonalDataError",
    "RecordedEvent",
    "UnknownRuleSetError",
    "check_chain",
    "engine_input_from_payload",
    "engine_input_payload",
    "ensure_rule_set",
    "load_rule_set_by_ref",
    "record",
    "verify_chain",
]
