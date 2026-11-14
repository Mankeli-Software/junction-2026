"""The caller's kitchen profile, usual items and last order.

The kitchen profile comes from the caller (its company's profile, #44). The usual items and
the last order come from the company's seeded order history (#32), made on first use.
A caller without a company row (only in tests) gets the fixture's usual items.
"""

from collections.abc import Iterable
from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company
from app.schemas import (
    CustomerContext,
    Exclusion,
    ExclusionLabel,
    HistoryLine,
    KitchenType,
    UsualItem,
)
from app.seed import history
from app.services.caller import Caller
from app.services.fixtures import load
from app.services.policy import get_rule_set


def exclusion_labels(exclusions: Iterable[Exclusion]) -> list[ExclusionLabel]:
    """Each exclusion with its label from `policy/allergen_rules.yaml`."""
    kitchen = get_rule_set().kitchen
    return [ExclusionLabel(key=e, label=kitchen[e].label) for e in exclusions]


@cache
def _fixture_usual_items() -> tuple[UsualItem, ...]:
    return tuple(UsualItem.model_validate(i) for i in load("customer.json")["usual_items"])


async def _company(db: AsyncSession, caller: Caller) -> Company | None:
    """The caller's company with its kitchen type and history ensured, or None."""
    company = await db.get(Company, caller.company_id)
    if company is not None:
        await history.ensure_history(
            db, company, caller.exclusions, get_rule_set().policy.business_time
        )
    return company


async def usual_items(db: AsyncSession, caller: Caller) -> list[UsualItem]:
    """ "My usual": the company's staples at their usual quantity."""
    company = await _company(db, caller)
    if company is None:
        return list(_fixture_usual_items())
    return await history.usual_items(db, company.id)


async def recent_lines(db: AsyncSession, caller: Caller) -> list[HistoryLine]:
    """The company's order history lines, for the engine's history summary."""
    company = await _company(db, caller)
    return [] if company is None else await history.recent_lines(db, company.id)


async def last_order(db: AsyncSession, caller: Caller) -> list[UsualItem]:
    """The latest order's lines, for "the same as last time"."""
    company = await _company(db, caller)
    return [] if company is None else await history.last_order(db, company.id)


async def get_customer_context(db: AsyncSession, caller: Caller) -> CustomerContext:
    company = await _company(db, caller)
    if company is None:
        usual, last, kind = list(_fixture_usual_items()), [], None
    else:
        usual = await history.usual_items(db, company.id)
        last = await history.last_order(db, company.id)
        kind = KitchenType(company.kitchen_type) if company.kitchen_type else None
    return CustomerContext(
        company_name=caller.company_name,
        phone_masked=caller.phone_masked,
        exclusions=exclusion_labels(caller.exclusions),
        usual_items=usual,
        lang=caller.lang,
        kitchen_type=kind,
        last_order=last,
    )
