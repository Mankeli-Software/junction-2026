"""Sanity checks from the customer's order history (technical-plan.md §4.2, #42).

They never block: each one becomes a flag the buyer acknowledges on the confirmation page.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.schemas import HistoryLine, LineRequest, Localized, ReasonCode, RequestedUnit, RuleSet

from . import units
from .filters import Candidate
from .text import Field, number, unit_name

# The quantity is unusual when it is below the smallest past quantity divided by this, or
# above the largest times this. Seeded quantities vary ±15%, so re-orders never flag, but a
# unit or typing error (×10, ×1000) does.
UNUSUAL_FACTOR = Decimal(2)
MIN_PAST_ORDERS = 3


def unusual_quantity(
    line: LineRequest, chosen: Candidate, history: list[HistoryLine], rules: RuleSet
) -> dict[str, Field] | None:
    """Fields for QUANTITY_UNUSUAL besides the product, or None when the amount is within
    the usual range or there are too few past orders of the product to tell. Compared in
    sales units."""
    assert chosen.amount is not None
    past: dict[datetime, Decimal] = {}
    for h in history:
        if h.product_id != chosen.product.product_id:
            continue
        amount = past_sales_units(h, line, chosen, rules)
        if amount is not None:
            past[h.ordered_at] = past.get(h.ordered_at, Decimal(0)) + amount
    if len(past) < MIN_PAST_ORDERS:
        return None
    low, high = min(past.values()), max(past.values())
    ordered = Decimal(chosen.amount.sales_units)
    if low / UNUSUAL_FACTOR <= ordered <= high * UNUSUAL_FACTOR:
        return None
    many = unit_name(rules, chosen.sales_unit, plural=True)
    low_text, high_text = number(_round(low)), number(_round(high))
    return {
        "quantity": number(ordered),
        "unit": unit_name(rules, chosen.sales_unit, plural=chosen.amount.sales_units != 1),
        "usual": Localized(
            fi=f"{low_text.fi}–{high_text.fi} {many.fi}",
            en=f"{low_text.en} to {high_text.en} {many.en}",
        ),
    }


def past_sales_units(
    h: HistoryLine, line: LineRequest, chosen: Candidate, rules: RuleSet
) -> Decimal | None:
    """A past quantity in the chosen product's sales units, or None if it can't be converted.
    History quantities are in the asked unit (`l`, `kg`, `piece`, `sales_unit`)."""
    try:
        unit = RequestedUnit(h.sales_unit)
    except ValueError:
        return None
    if unit == RequestedUnit.sales_unit:
        return h.quantity
    if unit == RequestedUnit.package:
        return None
    past = line.model_copy(update={"quantity": h.quantity, "unit": unit, "package_word": None})
    amount = units.sales_units(past, chosen.product, chosen.sales_unit, rules)
    if isinstance(amount, ReasonCode) or not amount.size:
        return None
    return h.quantity / amount.size


def duplicate(
    chosen: Candidate, history: list[HistoryLine], issued_at: datetime, rules: RuleSet
) -> dict[str, Field] | None:
    """Fields for DUPLICATE_ORDER besides the product (none) when the product was in an
    order placed within the duplicate window before the quote (real clock), whatever the
    quantity."""
    since = issued_at - timedelta(seconds=rules.policy.duplicate_window_seconds)
    pid = chosen.product.product_id
    recent = any(h.product_id == pid and since <= h.ordered_at <= issued_at for h in history)
    return {} if recent else None


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1")).normalize()
