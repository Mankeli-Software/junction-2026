"""Candidate checks in technical-plan.md §4.2 order. #39 adds the substitution and
deeper price checks.

Each check either fills in the candidate or returns the reason it was removed.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.schemas import (
    Claim,
    ClaimRule,
    Exclusion,
    LineRequest,
    Localized,
    Offer,
    ProductRecord,
    ReasonCode,
    RuleSet,
    StockStatus,
)

from . import units
from .text import Field, day, number, unit_name

# Kitchen-rule claims (policy/allergen_rules.yaml) as product claims (ProductRecord.claims).
CLAIMS = {
    ("LACTOSE", "FREE_FROM"): Claim.lactose_free,
    ("GLUTEN", "FREE_FROM"): Claim.gluten_free,
    ("VEGAN", None): Claim.vegan,
    ("VEGETARIAN", None): Claim.vegetarian,
}
UNSAFE = {"CONTAINS", "MAY_CONTAIN"}
# How far unit price ÷ comparison price may be from the known size. Both prices are
# rounded to the cent, so a small pack can be a few percent off without being wrong.
PRICE_RATIO_TOLERANCE = Decimal("0.05")


@dataclass
class Removal:
    code: ReasonCode
    fields: dict[str, Field] = field(default_factory=dict)


@dataclass
class Candidate:
    product: ProductRecord
    offer: Offer | None = None
    sales_unit: str = ""
    amount: units.Amount | None = None
    stock: StockStatus = StockStatus.verified
    unit_price: Decimal = Decimal(0)
    total_cents: int = 0
    surplus: Decimal = Decimal(0)  # in the asked unit, from rounding up to whole sales units
    within_limits: bool = True  # the surplus is within the automatic round-up limits


@dataclass(frozen=True)
class Context:
    line: LineRequest
    exclusions: list[Exclusion]
    offers: dict[str, Offer]
    rules: RuleSet
    business_now: datetime


def check(candidate: Candidate, ctx: Context) -> Removal | None:
    for step in (_diet, _kitchen, _offer, _availability, _units, _stock, _price):
        if (removal := step(candidate, ctx)) is not None:
            return removal
    return None


def _diet(c: Candidate, ctx: Context) -> Removal | None:
    missing = sorted(set(ctx.line.claims) - set(c.product.claims))
    if missing:
        labels = [_claim_label(m, ctx.rules) for m in missing]
        label = Localized(
            fi=", ".join(lbl.fi for lbl in labels), en=", ".join(lbl.en for lbl in labels)
        )
        return Removal(ReasonCode.DIET_CLAIM_MISSING, {"product": c.product.name, "choice": label})
    return None


def _claim_label(claim: Claim, rules: RuleSet) -> Localized:
    """The kitchen label for a claim with the same name (lactose_free), else the claim id."""
    if claim.value in Exclusion.__members__.values():
        return rules.kitchen[Exclusion(claim.value)].label
    return Localized(fi=claim.value, en=claim.value)


def _has_claim(product: ProductRecord, rule: ClaimRule) -> bool:
    claim = CLAIMS.get((rule.code, rule.level))
    return claim is not None and claim in product.claims


@dataclass(frozen=True)
class _Block:
    """Why one exclusion removes a product: an allergen code it lists (contains or may
    contain), or `code=None` when it lacks a claim the exclusion requires."""

    exclusion: Exclusion
    code: str | None


def _blocks(product: ProductRecord, exclusions: list[Exclusion], rules: RuleSet) -> _Block | None:
    """The first exclusion (in sorted order) that removes the product, and why. The one
    reading of the kitchen rules behind both `_kitchen` and `may_block`."""
    listed = {a.code for a in product.allergens if a.containment in UNSAFE}
    for exclusion in sorted(exclusions):
        rule = rules.kitchen[exclusion]
        blocking = [code for code in rule.block if code in listed]
        if rule.block_unless_claim and not all(
            _has_claim(product, r) for r in rule.block_unless_claim.claim
        ):
            blocking += [code for code in rule.block_unless_claim.codes if code in listed]
        if blocking:
            return _Block(exclusion, blocking[0])
        if not all(_has_claim(product, r) for r in rule.require_claim):
            return _Block(exclusion, None)
    return None


def may_block(product: ProductRecord, exclusions: list[Exclusion], rules: RuleSet) -> bool:
    """Whether one of the kitchen's exclusions removes this product: it lists (contains or
    may contain) a code the exclusion blocks, or one it blocks unless the product has a
    claim it lacks, or it lacks a claim the exclusion requires. The same check the engine
    runs, for callers outside it (gathering substitute candidates). A product with no
    allergen listing is not blocked (the engine keeps it, with a notice)."""
    return _blocks(product, exclusions, rules) is not None


def _kitchen(c: Candidate, ctx: Context) -> Removal | None:
    block = _blocks(c.product, ctx.exclusions, ctx.rules)
    if block is None:
        return None
    label = ctx.rules.kitchen[block.exclusion].label
    if block.code is None:
        return Removal(ReasonCode.DIET_CLAIM_MISSING, {"product": c.product.name, "choice": label})
    listed = {a.code: a.containment for a in c.product.allergens if a.containment in UNSAFE}
    return Removal(
        ReasonCode.ALLERGEN_CONFLICT,
        _allergen_fields(c.product, block.code, listed[block.code], label, ctx.rules),
    )


def allergens_unknown(product: ProductRecord, exclusions: list[Exclusion], rules: RuleSet) -> bool:
    """True when the kitchen has an exclusion and the product's allergens can't be checked:
    no listing at all, or `UNDECLARED` for a code one of the exclusions looks at.
    Such a product stays orderable; the order gets one notice (vision §10)."""
    if not exclusions:
        return False
    if not product.allergen_listing:
        return True
    relevant: set[str] = set()
    for exclusion in exclusions:
        rule = rules.kitchen[exclusion]
        relevant.update(rule.block)
        if rule.block_unless_claim:
            relevant.update(rule.block_unless_claim.codes)
    return any(a.containment == "UNDECLARED" and a.code in relevant for a in product.allergens)


def _allergen_fields(
    product: ProductRecord, code: str, containment: str, label: Localized, rules: RuleSet
) -> dict[str, Field]:
    allergen = rules.allergens[code]
    phrase = rules.containment[containment]
    return {
        "product": product.name,
        "allergen": allergen.gs1_label.removesuffix(" and its derivatives").lower(),
        "allergen_fi": allergen.name_fi_partitive or allergen.name_fi,
        "containment_en": phrase.en,
        "containment_fi": phrase.fi,
        "choice": label,
    }


def _offer(c: Candidate, ctx: Context) -> Removal | None:
    c.offer = ctx.offers.get(c.product.product_id)
    if c.offer is None or not c.offer.ok or c.offer.unit_price_gross is None:
        return Removal(ReasonCode.OFFER_UNAVAILABLE, {"product": c.product.name})
    return None


def _availability(c: Candidate, ctx: Context) -> Removal | None:
    offer = c.offer
    assert offer is not None
    needed_by = ctx.line.needed_by
    fields: dict[str, Field] = {"product": c.product.name, "date": day(needed_by)}
    in_stock = [s for s in offer.schedule if s.amount > 0]
    if offer.sales_block or not in_stock:
        return Removal(ReasonCode.UNAVAILABLE, fields)
    if not any(s.available_date <= needed_by for s in in_stock):
        return Removal(ReasonCode.DELIVERY_DATE_UNREACHABLE, fields)
    if (
        ctx.rules.policy.enforce_closing_time
        and offer.closing_time is not None
        and ctx.business_now >= offer.closing_time
    ):
        return Removal(ReasonCode.PAST_CLOSING_TIME, fields)
    return None


def _units(c: Candidate, ctx: Context) -> Removal | None:
    assert c.offer is not None
    c.sales_unit = c.offer.sales_unit or c.product.sales_unit
    if c.sales_unit not in c.product.units or not _price_ratio_agrees(c):
        return Removal(ReasonCode.UNIT_UNKNOWN, {"product": c.product.name})
    amount = units.sales_units(ctx.line, c.product, c.sales_unit, ctx.rules)
    if isinstance(amount, ReasonCode) or amount.sales_units < 1:
        return Removal(
            amount if isinstance(amount, ReasonCode) else ReasonCode.UNIT_CONVERSION_UNKNOWN,
            {
                "product": c.product.name,
                "quantity": number(ctx.line.quantity),
                "unit": ctx.line.package_word or ctx.line.unit.value,
            },
        )
    c.amount = amount
    c.surplus = units.surplus(ctx.line, amount)
    c.within_limits = units.within_limits(ctx.line, amount, ctx.rules)
    return None


def _price_ratio_agrees(c: Candidate) -> bool:
    """Unit price ÷ comparison price is the litres or kilos in one sales unit. If the
    product data says otherwise, the sales unit is not what we think it is (§4.2)."""
    assert c.offer is not None
    price, comparison = c.offer.unit_price_gross, c.offer.comparison_price_gross
    unit = c.offer.comparison_unit
    if price is None or not comparison or unit not in ("L", "KG"):
        return True
    known = units.size_or_name(c.product, c.sales_unit, unit)
    if known is None:
        return True
    implied = price / comparison
    return abs(implied - known[0]) <= PRICE_RATIO_TOLERANCE * known[0]


def _stock(c: Candidate, ctx: Context) -> Removal | None:
    assert c.offer is not None and c.amount is not None
    available = max(s.amount for s in c.offer.schedule if s.available_date <= ctx.line.needed_by)
    if available >= ctx.rules.policy.unverified_stock_threshold:
        c.stock = StockStatus.unverified
    elif available < c.amount.sales_units:
        return Removal(
            ReasonCode.PARTIAL_STOCK,
            {
                "product": c.product.name,
                "available": number(available),
                "unit": unit_name(ctx.rules, c.sales_unit, plural=True),
            },
        )
    return None


def _price(c: Candidate, ctx: Context) -> Removal | None:
    assert c.offer is not None and c.offer.unit_price_gross is not None and c.amount is not None
    valid_to: date | None = c.offer.price_valid_to
    if valid_to is not None and valid_to < ctx.line.needed_by:
        return Removal(
            ReasonCode.PRICE_NOT_VALID, {"product": c.product.name, "date": day(ctx.line.needed_by)}
        )
    c.unit_price = c.offer.unit_price_gross
    # Line total = quantity × gross unit price, rounded up to the next cent (§4.2).
    c.total_cents = math.ceil(Decimal(c.amount.sales_units) * c.unit_price * 100)
    return None
