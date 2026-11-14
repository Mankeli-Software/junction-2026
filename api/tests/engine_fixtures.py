"""Hand-built engine inputs: the milk scenario of valio-api-analysis.md §11 and helpers.

Prices are gross (VAT included). Stock of 999999999 is Valio's "unknown" sentinel.
"""

from datetime import date, datetime
from decimal import Decimal

from app.schemas import (
    Claim,
    EngineInput,
    Exclusion,
    HistoryLine,
    HistorySummary,
    KitchenProfile,
    LineRequest,
    Localized,
    Offer,
    OfferSource,
    ProductAllergen,
    ProductRecord,
    RequestedUnit,
    ScheduleLine,
    UnitConversion,
    UsualItem,
)
from tests.contract_fixtures import RULES

BUSINESS_NOW = datetime.fromisoformat("2026-11-12T09:00:00+02:00")
ISSUED_AT = datetime.fromisoformat("2026-11-14T12:00:00+02:00")
MONDAY = date(2026, 11, 16)
SENTINEL = Decimal("999999999")


def product(
    pid: str,
    name: str,
    *,
    litres: str = "1",
    sales_unit: str = "ST",
    per_case: int | None = None,
    category: str = "10400",
    claims: tuple[Claim, ...] = (Claim.lactose_free,),
    allergens: tuple[tuple[str, str], ...] = (("AM", "CONTAINS"),),
) -> ProductRecord:
    conversions = [UnitConversion(from_unit="ST", to_unit="L", factor=Decimal(litres))]
    units = ["ST"]
    if per_case:
        conversions.append(UnitConversion(from_unit="KI", to_unit="ST", factor=Decimal(per_case)))
        units.append("KI")
    return ProductRecord(
        product_id=pid,
        name=Localized(fi=name, en=name),
        category=category,
        sales_unit=sales_unit,
        base_unit="ST",
        units=units,
        unit_conversions=conversions,
        allergens=[ProductAllergen(code=c, containment=k) for c, k in allergens],
        allergen_listing=bool(allergens),
        claims=list(claims),
        origin="FI",
        image_url=None,
        substitutions=[],
    )


def offer(
    pid: str,
    price: str | None,
    stock: Decimal | int | None = SENTINEL,
    *,
    sales_unit: str = "ST",
    available: date = date(2026, 11, 13),
    closing: str | None = "2026-11-12T12:00:00+02:00",
    ok: bool = True,
) -> Offer:
    return Offer(
        product_id=pid,
        ok=ok,
        unit_price_gross=Decimal(price) if price else None,
        price_valid_to=date(2026, 12, 31),
        sales_unit=sales_unit,
        schedule=[] if stock is None else [ScheduleLine(available_date=available, amount=stock)],
        sales_block=False,
        closing_time=datetime.fromisoformat(closing) if closing else None,
        fetched_at=BUSINESS_NOW,
        source=OfferSource.snapshot,
    )


MILK_PRODUCTS = [
    product("464073", "Valio täysmaito 1 l UHT"),
    product("464201", "Valio kevytmaito 1 l UHT"),
    product("464306", "Valio Arki kevytmaito 1 l"),
    product("462775", "Arla rasvaton maito 1 l"),
    product("463380", "Arla Café maito 1 l"),
    product("464119", "Valio rasvaton maito 1 l UHT", sales_unit="KI", per_case=10),
    product("464440", "Valio kevytmaito 0,5 l", litres="0.5"),
]
MILK_OFFERS = [
    offer("464073", "1.86"),
    offer("464201", "1.77"),
    offer("464306", "1.15"),
    offer("462775", "2.92", 51),
    offer("463380", "3.01", 698),
    offer("464119", "15.12", 999999, sales_unit="KI"),
    offer("464440", "1.00", None),
]
# Search order for "maito": most relevant first.
MILK_SEARCH = ["464073", "464201", "464306", "462775", "463380", "464119", "464440"]


def milk_line(line_id: str = "milk", **kw) -> LineRequest:
    return LineRequest(
        line_id=line_id,
        text=kw.pop("text", "maito"),
        claims=kw.pop("claims", [Claim.lactose_free]),
        quantity=Decimal(kw.pop("quantity", "1000")),
        unit=kw.pop("unit", RequestedUnit.l),
        needed_by=kw.pop("needed_by", MONDAY),
        **kw,
    )


def engine_input(
    *lines: LineRequest,
    candidates: dict[str, list[str]] | None = None,
    substitutes: dict[str, list[str]] | None = None,
    products: list[ProductRecord] | None = None,
    offers: list[Offer] | None = None,
    exclusions: tuple[Exclusion, ...] = (),
    usual: tuple[UsualItem, ...] = (),
    history: tuple[HistoryLine, ...] = (),
) -> EngineInput:
    lines = lines or (milk_line(),)
    return EngineInput(
        lines=list(lines),
        kitchen=KitchenProfile(exclusions=list(exclusions)),
        history=HistorySummary(usual_items=list(usual), recent_lines=list(history)),
        candidates=candidates if candidates is not None else {"milk": MILK_SEARCH},
        substitutes=substitutes or {},
        products=products if products is not None else MILK_PRODUCTS,
        offers=offers if offers is not None else MILK_OFFERS,
        rules=RULES,
        business_now=BUSINESS_NOW,
        issued_at=ISSUED_AT,
        lang="fi",
    )
