"""The caller's kitchen profile and usual items, from the caller and a fixture (#44 replaces it)."""

from functools import cache

from app.schemas import CustomerContext, Exclusion, ExclusionLabel, Localized, UsualItem
from app.services.caller import Caller
from app.services.fixtures import load

# The labels in policy/allergen_rules.yaml. The policy loader (#35) will own them.
EXCLUSION_LABELS = {
    Exclusion.milk_free: Localized(fi="maidoton", en="milk-free"),
    Exclusion.lactose_free: Localized(fi="laktoositon", en="lactose-free"),
    Exclusion.gluten_free: Localized(fi="gluteeniton", en="gluten-free"),
    Exclusion.nut_free: Localized(fi="pähkinätön", en="nut-free"),
    Exclusion.egg_free: Localized(fi="kananmunaton", en="egg-free"),
    Exclusion.fish_free: Localized(fi="kalaton", en="fish-free"),
    Exclusion.vegan: Localized(fi="vegaaninen", en="vegan"),
}


@cache
def _usual_items() -> tuple[UsualItem, ...]:
    return tuple(UsualItem.model_validate(i) for i in load("customer.json")["usual_items"])


def usual_items(caller: Caller) -> list[UsualItem]:
    return list(_usual_items())


def get_customer_context(caller: Caller) -> CustomerContext:
    return CustomerContext(
        company_name=caller.company_name,
        phone_masked=caller.phone_masked,
        exclusions=[ExclusionLabel(key=e, label=EXCLUSION_LABELS[e]) for e in caller.exclusions],
        usual_items=usual_items(caller),
        lang=caller.lang,
    )
