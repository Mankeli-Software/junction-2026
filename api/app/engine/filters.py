"""Candidate checks in technical-plan.md §4.2 order. Simple versions for #36:
#37 deepens the allergen filter, #38 availability and units, #39 the price checks.

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


def _kitchen(c: Candidate, ctx: Context) -> Removal | None:
    listed = {a.code: a.containment for a in c.product.allergens if a.containment in UNSAFE}
    for exclusion in sorted(ctx.exclusions):
        rule = ctx.rules.kitchen[exclusion]
        blocking = [code for code in rule.block if code in listed]
        if rule.block_unless_claim and not all(
            _has_claim(c.product, r) for r in rule.block_unless_claim.claim
        ):
            blocking += [code for code in rule.block_unless_claim.codes if code in listed]
        if blocking:
            code = blocking[0]
            return Removal(
                ReasonCode.ALLERGEN_CONFLICT,
                _allergen_fields(c.product, code, listed[code], rule.label, ctx.rules),
            )
        if not all(_has_claim(c.product, r) for r in rule.require_claim):
            return Removal(
                ReasonCode.DIET_CLAIM_MISSING, {"product": c.product.name, "choice": rule.label}
            )
    return None


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
    if c.sales_unit not in c.product.units:
        return Removal(ReasonCode.UNIT_UNKNOWN, {"product": c.product.name})
    c.amount = units.sales_units(ctx.line, c.product, c.sales_unit, ctx.rules)
    if c.amount is None or c.amount.sales_units < 1:
        return Removal(
            ReasonCode.UNIT_CONVERSION_UNKNOWN,
            {
                "product": c.product.name,
                "quantity": number(ctx.line.quantity),
                "unit": ctx.line.package_word or ctx.line.unit.value,
            },
        )
    return None


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
