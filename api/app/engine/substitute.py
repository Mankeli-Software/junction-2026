"""The substitution ladder (technical-plan.md §4.2, #39).

Runs only when a line can't be filled from its own candidates. The order of tries:
the same product in another pack, then a curated `substitutions[]` pair, then a similar
product, then a callback request. The first two are swapped automatically, but only if
no allergen is added and the price per kg or litre is at most the policy's limit higher.
Anything else goes to the buyer as a question.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.schemas import Offer, ProductRecord, ReasonCode, RuleSet, StockStatus

from . import units
from .filters import UNSAFE, Candidate

OTHER_PACK, CURATED, SIMILAR = 1, 2, 3
AUTOMATIC = {OTHER_PACK: ReasonCode.SUBSTITUTED_PACK_SIZE, CURATED: ReasonCode.SUBSTITUTED_CURATED}


@dataclass
class Step:
    candidate: Candidate
    step: int
    order: int  # position in the quote service's candidate list, best first


@dataclass
class Choice:
    """What the ladder decided: swap automatically (`code` is SUBSTITUTED_*) or ask."""

    ranked: list[Step]
    chosen: Step
    code: ReasonCode
    percent: Decimal | None = None  # price increase, for SUBSTITUTE_PRICE_TOO_HIGH


def other_pack(original: ProductRecord, product: ProductRecord) -> bool:
    """Same category and the same name once the pack sizes are taken out."""
    if original.product_id == product.product_id or original.category != product.category:
        return False
    stem = units.without_size(original.name.fi)
    return bool(stem) and stem == units.without_size(product.name.fi)


def step_of(original: ProductRecord, product: ProductRecord, curated: set[str]) -> int:
    if other_pack(original, product):
        return OTHER_PACK
    if product.product_id in curated:
        return CURATED
    return SIMILAR


def rank(steps: list[Step], ordered_before: set[str]) -> list[Step]:
    """Ladder step first; within a step waste first, then the candidate order (best by
    meaning, #78), then price, verified stock, history, Finnish origin and product id."""
    return sorted(
        steps,
        key=lambda s: (
            s.step,
            not s.candidate.within_limits,
            Decimal(0) if s.candidate.within_limits else s.candidate.surplus,
            s.order,
            s.candidate.total_cents,
            s.candidate.stock != StockStatus.verified,
            s.candidate.product.product_id not in ordered_before,
            s.candidate.product.origin != "FI",
            s.candidate.product.product_id,
        ),
    )


def choose(
    original: Candidate, ranked: list[Step], offers: dict[str, Offer], rules: RuleSet
) -> Choice:
    """The first automatic swap in ladder order, else a question about the best one."""
    before = original_price(original, offers)
    for s in ranked:
        if s.step in AUTOMATIC and _blocker(original, before, s.candidate, rules) is None:
            return Choice(ranked, s, AUTOMATIC[s.step])
    best = ranked[0]
    if best.step in AUTOMATIC:
        blocker = _blocker(original, before, best.candidate, rules)
        if isinstance(blocker, Decimal):
            return Choice(ranked, best, ReasonCode.SUBSTITUTE_PRICE_TOO_HIGH, blocker)
    return Choice(ranked, best, ReasonCode.SUBSTITUTE_SUGGESTED)


def _blocker(
    original: Candidate, before: tuple[Decimal, str] | None, sub: Candidate, rules: RuleSet
) -> Decimal | str | None:
    """Why the swap can't be automatic: the price increase in percent when it is over the
    limit, a word when an allergen is added or the prices can't be compared, else None."""
    added = _unsafe(sub.product) - _unsafe(original.product)
    if added:
        return "allergen"
    after = price_per_base(sub)
    if before is None or after is None or before[1] != after[1] or before[0] <= 0:
        return "not comparable"
    increase = after[0] / before[0] - 1
    if increase > rules.policy.substitution.max_price_increase_ratio:
        return (increase * 100).quantize(Decimal(1))
    return None


def _unsafe(product: ProductRecord) -> set[str]:
    return {a.code for a in product.allergens if a.containment in UNSAFE}


def price_per_base(c: Candidate) -> tuple[Decimal, str] | None:
    """Gross price per litre or kilo of a priced candidate."""
    measure = units.base_measure(c.product, c.sales_unit)
    if measure is None or measure[0] <= 0:
        return None
    return c.unit_price / measure[0], measure[1]


def original_price(c: Candidate, offers: dict[str, Offer]) -> tuple[Decimal, str] | None:
    """Price per litre or kilo of the product being replaced, from its offer if it has one.
    It was removed, maybe before its offer was looked at, so the offer is looked up here."""
    offer = offers.get(c.product.product_id)
    if offer is None or not offer.ok or offer.unit_price_gross is None:
        return None
    measure = units.base_measure(c.product, offer.sales_unit or c.product.sales_unit)
    if measure is None or measure[0] <= 0:
        return None
    return offer.unit_price_gross / measure[0], measure[1]
