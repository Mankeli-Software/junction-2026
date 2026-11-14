"""Asked quantity to whole sales units (technical-plan.md §4.2, simple version for #36).

#38 adds the sales-unit cross-check against the price ratio, pack sizes read from
names and the rounding limits.
"""

import math
from dataclasses import dataclass
from decimal import Decimal

from app.schemas import LineRequest, ProductRecord, RequestedUnit, RuleSet

# The unit code an asked unit converts to. `sales_unit` and `package` are resolved apart.
TARGET = {RequestedUnit.l: "L", RequestedUnit.kg: "KG", RequestedUnit.piece: "ST"}


@dataclass(frozen=True)
class Amount:
    sales_units: int
    # How much of the asked unit one sales unit holds; None when asked in sales units.
    size: Decimal | None

    @property
    def in_asked_unit(self) -> Decimal:
        return Decimal(self.sales_units) * (self.size or 1)


def size(product: ProductRecord, unit: str, target: str) -> Decimal | None:
    """How many `target` units one `unit` holds, following the product's conversions."""
    if unit == target:
        return Decimal(1)
    edges: dict[str, list[tuple[str, Decimal]]] = {}
    for c in product.unit_conversions:
        if c.factor > 0:
            edges.setdefault(c.from_unit, []).append((c.to_unit, c.factor))
            edges.setdefault(c.to_unit, []).append((c.from_unit, 1 / c.factor))
    # Breadth-first, visiting units in sorted order so the result never depends on input order.
    seen, frontier = {unit}, [(unit, Decimal(1))]
    while frontier:
        nxt = []
        for current, factor in frontier:
            for other, step in sorted(edges.get(current, [])):
                if other == target:
                    return factor * step
                if other not in seen:
                    seen.add(other)
                    nxt.append((other, factor * step))
        frontier = nxt
    return None


def package_unit(rules: RuleSet, word: str | None, product: ProductRecord) -> str | None:
    """The product's unit a packaging word names ("laatikko", "cases"), if exactly one does."""
    if not word:
        return None
    w = word.strip().lower()
    hits = {
        code
        for code, n in rules.units.items()
        if code in product.units
        and w in {n.name_fi.lower(), n.name_en.lower(), n.name_fi_partitive.lower(),
                 n.name_en_plural.lower()}
    }  # fmt: skip
    return hits.pop() if len(hits) == 1 else None


def sales_units(
    line: LineRequest, product: ProductRecord, sales_unit: str, rules: RuleSet
) -> Amount | None:
    """Whole sales units covering the asked quantity, or None if it can't be converted."""
    if line.unit == RequestedUnit.sales_unit:
        return Amount(math.ceil(line.quantity), None)
    target = (
        package_unit(rules, line.package_word, product)
        if line.unit == RequestedUnit.package
        else (TARGET[line.unit])
    )
    if target is None:
        return None
    per_unit = size(product, sales_unit, target)
    if per_unit is None:
        return None
    return Amount(math.ceil(line.quantity / per_unit), per_unit)


def base_measure(product: ProductRecord, sales_unit: str) -> tuple[Decimal, str] | None:
    """Litres or kilos in one sales unit, for the price per litre or kilo."""
    for target, label in (("L", "l"), ("KG", "kg")):
        if (amount := size(product, sales_unit, target)) is not None:
            return amount, label
    return None
