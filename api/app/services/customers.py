"""The caller's kitchen profile and usual items.

The kitchen profile comes from the caller (its company's profile, #44). The usual items
still come from a fixture until the order history lands (#32, #61).
"""

from collections.abc import Iterable
from functools import cache

from app.schemas import CustomerContext, Exclusion, ExclusionLabel, UsualItem
from app.services.caller import Caller
from app.services.fixtures import load
from app.services.policy import get_rule_set


def exclusion_labels(exclusions: Iterable[Exclusion]) -> list[ExclusionLabel]:
    """Each exclusion with its label from `policy/allergen_rules.yaml`."""
    kitchen = get_rule_set().kitchen
    return [ExclusionLabel(key=e, label=kitchen[e].label) for e in exclusions]


@cache
def _usual_items() -> tuple[UsualItem, ...]:
    return tuple(UsualItem.model_validate(i) for i in load("customer.json")["usual_items"])


def usual_items(caller: Caller) -> list[UsualItem]:
    return list(_usual_items())


def get_customer_context(caller: Caller) -> CustomerContext:
    return CustomerContext(
        company_name=caller.company_name,
        phone_masked=caller.phone_masked,
        exclusions=exclusion_labels(caller.exclusions),
        usual_items=usual_items(caller),
        lang=caller.lang,
    )
