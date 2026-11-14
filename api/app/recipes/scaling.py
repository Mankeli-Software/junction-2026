"""Scaling a recipe to a portion count and picking the pack for a linked ingredient (#34).

Pure functions: the service reads the rows and the catalogue and passes them in.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

# Kilos, litres and grams are rounded to this many significant digits: 38.9 kg, 3.89 kg,
# 389 g and 0.4 g are each as exact as a kitchen measures them.
SIGNIFICANT_DIGITS = 3
# Counted units are whole: 12.2 pieces is 13.
COUNTED_UNITS = frozenset({"kpl", "pcs", "piece", "st"})


def scale(per_portion: Decimal, portions: int, unit: str | None) -> Decimal:
    """The amount for `portions`, rounded sensibly for the unit."""
    amount = per_portion * portions
    if amount <= 0:
        return Decimal(0)
    if unit is not None and unit.lower() in COUNTED_UNITS:
        return amount.to_integral_value(rounding=ROUND_CEILING)
    exponent = amount.adjusted() - (SIGNIFICANT_DIGITS - 1)
    rounded = amount.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP)
    # No exponent notation (3.9E+1) and no trailing zeros (0.200).
    return rounded.quantize(Decimal(1)) if rounded == rounded.to_integral() else rounded.normalize()


@dataclass(frozen=True)
class Pack:
    """One catalogue product a recipe product links to (recipe_product_links)."""

    product_id: str
    units_per_sales_unit: Decimal
    net_weight_kg: Decimal | None  # one base unit; None when unknown

    @property
    def sales_unit_kg(self) -> Decimal | None:
        if not self.net_weight_kg:
            return None
        return self.net_weight_kg * self.units_per_sales_unit


def choose_pack(packs: list[Pack], kilos: Decimal | None) -> Pack | None:
    """The pack that covers the amount with the least left over, then the fewest sales
    units, then the product id. Packs of unknown weight come last."""
    if not packs:
        return None

    def key(pack: Pack) -> tuple:
        size = pack.sales_unit_kg
        if size is None or kilos is None or kilos <= 0:
            return (1, Decimal(0), 0, pack.product_id)
        units = math.ceil(kilos / size)
        return (0, units * size - kilos, units, pack.product_id)

    return min(packs, key=key)
