"""Asked quantity to whole sales units (technical-plan.md §4.2).

Sizes come from the product's `unit_conversions`. When none of them reaches litres or
kilos, a pack size read from the name ("1 l", "0,5 l", "6 x 150 g") is used and flagged.
"""

import math
import re
from dataclasses import dataclass
from decimal import Decimal

from app.schemas import LineRequest, ProductRecord, ReasonCode, RequestedUnit, RuleSet

# The unit code an asked unit converts to. `sales_unit` and `package` are resolved apart.
TARGET = {RequestedUnit.l: "L", RequestedUnit.kg: "KG", RequestedUnit.piece: "ST"}

# A pack size in a product name: "1 l", "0,5L", "500 g", "2,5 kg", "6 x 150 g".
_SIZE = re.compile(
    r"(?<![\w,.])(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|l|dl|cl|ml)(?![\w])",
    re.IGNORECASE,
)
_TO_BASE = {
    "kg": ("KG", Decimal(1)),
    "g": ("KG", Decimal("0.001")),
    "l": ("L", Decimal(1)),
    "dl": ("L", Decimal("0.1")),
    "cl": ("L", Decimal("0.01")),
    "ml": ("L", Decimal("0.001")),
}


@dataclass(frozen=True)
class Amount:
    sales_units: int
    # How much of the asked unit one sales unit holds; None when asked in sales units.
    size: Decimal | None
    from_name: bool = False  # the size came from the product name

    @property
    def in_asked_unit(self) -> Decimal:
        return Decimal(self.sales_units) * (self.size or 1)


def name_size(product: ProductRecord) -> tuple[Decimal, str] | None:
    """Litres or kilos in one base unit, read from the name, if the names agree on one size.

    Both the Finnish and the English name are read; two different sizes give None.
    """
    found: set[tuple[Decimal, str]] = set()
    for name in (product.name.fi, product.name.en):
        for count, number, unit in _SIZE.findall(name):
            target, factor = _TO_BASE[unit.lower()]
            amount = Decimal(number.replace(",", ".")) * factor * Decimal(count or 1)
            found.add((amount.normalize(), target))
    return found.pop() if len(found) == 1 else None


def _edges(product: ProductRecord, with_name: bool) -> dict[str, list[tuple[str, Decimal]]]:
    edges: dict[str, list[tuple[str, Decimal]]] = {}

    def add(a: str, b: str, factor: Decimal) -> None:
        edges.setdefault(a, []).append((b, factor))
        edges.setdefault(b, []).append((a, 1 / factor))

    for c in product.unit_conversions:
        if c.factor > 0:
            add(c.from_unit, c.to_unit, c.factor)
    if with_name and product.base_unit and (named := name_size(product)) is not None:
        add(product.base_unit, named[1], named[0])
    return edges


def _search(edges: dict[str, list[tuple[str, Decimal]]], unit: str, target: str) -> Decimal | None:
    if unit == target:
        return Decimal(1)
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


def size(product: ProductRecord, unit: str, target: str) -> Decimal | None:
    """How many `target` units one `unit` holds, following the product's conversions only."""
    return _search(_edges(product, with_name=False), unit, target)


def size_or_name(product: ProductRecord, unit: str, target: str) -> tuple[Decimal, bool] | None:
    """Like `size`, falling back to the pack size in the name. The bool says it was used."""
    if (found := size(product, unit, target)) is not None:
        return found, False
    if target in ("L", "KG") and (found := _search(_edges(product, True), unit, target)):
        return found, True
    return None


def package_units(rules: RuleSet, word: str | None, product: ProductRecord) -> set[str]:
    """The product's units a packaging word names ("laatikko", "cases")."""
    if not word:
        return set()
    w = word.strip().lower()
    return {
        code
        for code, n in rules.units.items()
        if code in product.units
        and w in {n.name_fi.lower(), n.name_en.lower(), n.name_fi_partitive.lower(),
                 n.name_en_plural.lower()}
    }  # fmt: skip


def sales_units(
    line: LineRequest, product: ProductRecord, sales_unit: str, rules: RuleSet
) -> Amount | ReasonCode:
    """Whole sales units covering the asked quantity, or why it can't be converted."""
    if line.unit == RequestedUnit.sales_unit:
        return Amount(math.ceil(line.quantity), None)
    if line.unit == RequestedUnit.package:
        hits = package_units(rules, line.package_word, product)
        if len(hits) > 1:
            return ReasonCode.PACKAGING_AMBIGUOUS
        if not hits:
            return ReasonCode.UNIT_CONVERSION_UNKNOWN
        target = hits.pop()
    else:
        target = TARGET[line.unit]
    found = size_or_name(product, sales_unit, target)
    if found is None:
        return ReasonCode.UNIT_CONVERSION_UNKNOWN
    per_unit, from_name = found
    return Amount(math.ceil(line.quantity / per_unit), per_unit, from_name)


def surplus(line: LineRequest, amount: Amount) -> Decimal:
    """How much more than asked the whole sales units give, in the asked unit."""
    return amount.in_asked_unit - line.quantity


def within_limits(line: LineRequest, amount: Amount, rules: RuleSet) -> bool:
    """Round-up is automatic only if the surplus is at most one sales unit and the ratio."""
    extra = surplus(line, amount)
    limit = rules.policy.rounding
    one_unit = amount.size or Decimal(1)
    return (
        extra <= limit.max_overage_units * one_unit
        and extra <= limit.max_overage_ratio * line.quantity
    )


def base_measure(product: ProductRecord, sales_unit: str) -> tuple[Decimal, str] | None:
    """Litres or kilos in one sales unit, for the price per litre or kilo."""
    for target, label in (("L", "l"), ("KG", "kg")):
        if (found := size_or_name(product, sales_unit, target)) is not None:
            return found[0], label
    return None
