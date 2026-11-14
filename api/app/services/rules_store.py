"""Rule sets by reference, for replay (#41). Interim: only the rule set loaded now.

`load_rule_set_by_ref()` is the interface replay uses (#45); #41 (Aku) replaces the body
with a lookup in the `rule_sets` table and keeps the signature.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import RuleSet
from app.services.policy import get_rule_set


class UnknownRuleSetError(LookupError):
    """No stored rule set has this reference."""


async def load_rule_set_by_ref(db: AsyncSession, ref: str) -> RuleSet:
    """The rule set whose `RuleSet.ref` is `ref`. Raises UnknownRuleSetError otherwise."""
    rules = get_rule_set()
    if rules.ref != ref:
        raise UnknownRuleSetError(f"unknown rule set {ref}")
    return rules
