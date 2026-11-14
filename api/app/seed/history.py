"""Demo kitchen types and their seeded order history (#32, `docs/plans/61-order-history.md`).

Every demo company is one of seven kitchen types, chosen from its phone number, and gets
eight weeks of orders at the type's rhythm from `data/demo_histories.yaml`. Everything is
seeded by the number and the order date, so the same number always gets the same history.
An item the kitchen's exclusions block is swapped through the category substitute map
(#78), so "my usual" is always something the kitchen can order.
"""

import hashlib
import random
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, OrderHistoryLine, Product
from app.schemas import Exclusion, HistoryLine, KitchenType, Localized, UsualItem
from app.search.substitutes import category_substitutes
from app.settings import REPO_ROOT, get_settings

HISTORIES_FILE = REPO_ROOT / "data" / "demo_histories.yaml"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Orders are placed at this time of day, in the business clock's time zone.
ORDER_TIME = time(9, 0)
# A product in at least this share of the company's orders is part of "my usual". Core items
# are in every order, the others in about half, so 0.75 keeps the staples only.
USUAL_SHARE = 0.75
STEP = {"kg": Decimal("0.5"), "l": Decimal("1"), "piece": Decimal("1"), "sales_unit": Decimal("1")}


@dataclass(frozen=True)
class Item:
    product_id: str
    quantity: Decimal
    unit: str
    core: bool


@dataclass(frozen=True)
class KitchenTypeSpec:
    key: KitchenType
    name: Localized
    days: tuple[int, ...]  # weekday numbers, Monday 0
    every_weeks: int
    default_exclusions: tuple[Exclusion, ...]
    items: tuple[Item, ...]


@dataclass(frozen=True)
class Line:
    ordered_at: datetime
    product_id: str
    quantity: Decimal
    unit: str


@cache
def kitchen_types() -> dict[KitchenType, KitchenTypeSpec]:
    data = yaml.safe_load(HISTORIES_FILE.read_text(encoding="utf-8"))
    out = {}
    for key, spec in data["types"].items():
        kind = KitchenType(key)
        out[kind] = KitchenTypeSpec(
            key=kind,
            name=Localized(**spec["name"]),
            days=tuple(WEEKDAYS.index(d) for d in spec["days"]),
            every_weeks=spec.get("every_weeks", 1),
            default_exclusions=tuple(Exclusion(e) for e in spec.get("default_exclusions", [])),
            items=tuple(
                Item(str(i["id"]), Decimal(str(i["quantity"])), i["unit"], i["core"])
                for i in spec["items"]
            ),
        )
    return out


@cache
def _settings_shape() -> tuple[int, Decimal]:
    data = yaml.safe_load(HISTORIES_FILE.read_text(encoding="utf-8"))
    return int(data["weeks"]), Decimal(str(data["variation"]))


def kitchen_type_for(phone_e164: str) -> KitchenType:
    """The number's kitchen type: the stage number gives the school kitchen, any other
    number one of the seven by a hash, so the same number always gets the same type."""
    if phone_e164 == get_settings().demo_stage_phone:
        return KitchenType.school_kitchen
    kinds = list(kitchen_types())
    digest = hashlib.sha256(phone_e164.encode()).digest()
    return kinds[int.from_bytes(digest[:8], "big") % len(kinds)]


def _rng(*parts: object) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))


def _stepped(quantity: Decimal, unit: str) -> Decimal:
    """Rounded to the unit's step (whole sales units, 0.5 kg, 1 l), at least one step."""
    step = STEP[unit]
    return max(step, (quantity / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step)


def _vary(base: Decimal, unit: str, variation: Decimal, rng: random.Random) -> Decimal:
    factor = Decimal(str(round(rng.uniform(-1, 1), 4))) * variation + 1
    return _stepped(base * factor, unit)


def order_dates(spec: KitchenTypeSpec, business_now: datetime) -> list[datetime]:
    """The type's order days over the history weeks, ending the day before business now."""
    weeks, _ = _settings_shape()
    last = business_now.date() - timedelta(days=1)
    first = last - timedelta(weeks=weeks) + timedelta(days=1)
    out = []
    day = first
    while day <= last:
        week = (day - first).days // 7
        if day.weekday() in spec.days and week % spec.every_weeks == 0:
            out.append(datetime.combine(day, ORDER_TIME, tzinfo=business_now.tzinfo or UTC))
        day += timedelta(days=1)
    return out


def generate(phone_e164: str, kind: KitchenType, business_now: datetime) -> list[Line]:
    """The type's history for this number, before any swap."""
    spec = kitchen_types()[kind]
    _, variation = _settings_shape()
    lines = []
    for index, ordered_at in enumerate(order_dates(spec, business_now)):
        day = ordered_at.date().isoformat()
        for item in spec.items:
            # "Sometimes" items alternate from a seeded start, so they are in exactly half
            # of the orders and never reach "my usual" by chance.
            offset = _rng(phone_e164, item.product_id).randrange(2)
            if not item.core and (index + offset) % 2:
                continue
            rng = _rng(phone_e164, day, item.product_id)
            quantity = _vary(item.quantity, item.unit, variation, rng)
            lines.append(Line(ordered_at, item.product_id, quantity, item.unit))
    return lines


async def _swaps(
    db: AsyncSession, product_ids: set[str], exclusions: list[Exclusion]
) -> dict[str, str | None]:
    """For each product the kitchen's exclusions may block, its alternative through the
    category substitute map (#78), or None if there is no safe one."""
    if not exclusions:
        return {}
    # Here, not at the top: the quote service imports this module's readers.
    from app.services import catalog
    from app.services.policy import get_rule_set
    from app.services.quotes import may_be_blocked

    rules = get_rule_set()
    records = {r.product_id: r for r in await catalog.get_products(db, sorted(product_ids))}
    swaps: dict[str, str | None] = {}
    for pid in sorted(product_ids):
        record = records.get(pid)
        if record is None or not may_be_blocked(record, exclusions, rules):
            continue
        swaps[pid] = None
        for to_category in category_substitutes().get(record.category, ()):
            found = await catalog.search_candidates(
                db, record.name.fi, [], to_category, limit=5, semantic=True
            )
            found = found or await catalog.search_candidates(db, None, [], to_category, limit=5)
            safe = [r for r in found if not may_be_blocked(r, exclusions, rules)]
            if safe:
                swaps[pid] = safe[0].product_id
                break
    return swaps


async def ensure_history(
    db: AsyncSession,
    company: Company,
    exclusions: list[Exclusion],
    business_now: datetime,
    *,
    regenerate: bool = False,
) -> KitchenType:
    """Give the company its kitchen type and history if it has none yet, or regenerate the
    history (after the kitchen's exclusions changed). Returns the type."""
    if company.kitchen_type is None:
        company.kitchen_type = kitchen_type_for(company.phone_e164).value
        regenerate = True
    kind = KitchenType(company.kitchen_type)
    if not regenerate:
        has_lines = await db.scalar(
            select(OrderHistoryLine.id).where(OrderHistoryLine.company_id == company.id).limit(1)
        )
        if has_lines is not None:
            return kind
    # Products missing from the loaded catalogue (a test or partial database) are left out.
    wanted = {item.product_id for item in kitchen_types()[kind].items}
    known = set(await db.scalars(select(Product.id).where(Product.id.in_(wanted))))
    lines = [
        line
        for line in generate(company.phone_e164, kind, business_now)
        if line.product_id in known
    ]
    swaps = await _swaps(db, {line.product_id for line in lines}, exclusions)
    await db.execute(delete(OrderHistoryLine).where(OrderHistoryLine.company_id == company.id))
    for line in lines:
        product_id = swaps.get(line.product_id, line.product_id)
        if product_id is None:  # blocked, no safe alternative: left out
            continue
        db.add(
            OrderHistoryLine(
                company_id=company.id,
                product_id=product_id,
                quantity=line.quantity,
                unit=line.unit,
                ordered_at=line.ordered_at,
                replaces_product_id=line.product_id if product_id != line.product_id else None,
            )
        )
    await db.flush()
    return kind


async def _lines(db: AsyncSession, company_id: uuid.UUID) -> list[OrderHistoryLine]:
    query = (
        select(OrderHistoryLine)
        .where(OrderHistoryLine.company_id == company_id)
        .order_by(OrderHistoryLine.ordered_at, OrderHistoryLine.product_id)
    )
    return list(await db.scalars(query))


async def _names(db: AsyncSession, ids: set[str]) -> dict[str, Localized]:
    rows = await db.execute(
        select(Product.id, Product.name_fi, Product.name_en).where(Product.id.in_(ids))
    )
    return {pid: Localized(fi=fi, en=en or fi) for pid, fi, en in rows}


async def usual_items(db: AsyncSession, company_id: uuid.UUID) -> list[UsualItem]:
    """ "My usual": every product in at least half of the company's orders, at its median
    quantity, in the order they first appear."""
    lines = await _lines(db, company_id)
    orders = {line.ordered_at for line in lines}
    if not orders:
        return []
    quantities: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for line in lines:
        quantities[(line.product_id, line.unit)].append(line.quantity)
    usual = [k for k, qs in quantities.items() if len(qs) >= USUAL_SHARE * len(orders)]
    names = await _names(db, {pid for pid, _ in usual})
    return [
        UsualItem(
            product_id=pid,
            name=names[pid],
            quantity=_stepped(Decimal(str(statistics.median(quantities[(pid, unit)]))), unit),
            unit=unit,
        )
        for pid, unit in usual
    ]


async def last_order(db: AsyncSession, company_id: uuid.UUID) -> list[UsualItem]:
    """The latest order's lines, for "the same as last time"."""
    lines = await _lines(db, company_id)
    if not lines:
        return []
    latest = max(line.ordered_at for line in lines)
    chosen = [line for line in lines if line.ordered_at == latest]
    names = await _names(db, {line.product_id for line in chosen})
    return [
        UsualItem(
            product_id=line.product_id,
            name=names[line.product_id],
            quantity=line.quantity,
            unit=line.unit,
        )
        for line in chosen
    ]


async def recent_lines(db: AsyncSession, company_id: uuid.UUID) -> list[HistoryLine]:
    """Every history line, for the engine's history summary (sanity checks, #42)."""
    return [
        HistoryLine(
            product_id=line.product_id,
            quantity=line.quantity,
            sales_unit=line.unit,
            ordered_at=line.ordered_at,
        )
        for line in await _lines(db, company_id)
    ]
