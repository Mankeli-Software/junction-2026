"""Product search on the fixture catalogue. The real search (#29) and offers (#31) replace it."""

from decimal import ROUND_HALF_UP, Decimal
from functools import cache

from pydantic import BaseModel

from app.schemas import (
    Localized,
    Offer,
    ProductHit,
    ProductRecord,
    SearchProductsRequest,
    SearchProductsResponse,
    StockStatus,
)
from app.services.caller import Caller
from app.services.fixtures import load


class _FixtureProduct(BaseModel):
    record: ProductRecord
    offer: Offer
    stock_status: StockStatus


@cache
def _products() -> tuple[_FixtureProduct, ...]:
    data = load("products.json")
    products = (_FixtureProduct.model_validate(p) for p in data["products"])
    return tuple(sorted(products, key=lambda p: p.record.product_id))


@cache
def _unit_labels() -> dict[str, Localized]:
    data = load("products.json")
    return {
        code: Localized.model_validate(label) for code, label in data["sales_unit_labels"].items()
    }


def records() -> list[ProductRecord]:
    return [p.record for p in _products()]


def offers() -> list[Offer]:
    return [p.offer for p in _products()]


def _price_per_base_unit(product: _FixtureProduct) -> Decimal | None:
    price = product.offer.unit_price_gross
    record = product.record
    factor = next(
        (
            c.factor
            for c in record.unit_conversions
            if c.from_unit == record.sales_unit and c.to_unit == record.base_unit
        ),
        None,
    )
    if price is None or not factor:
        return None
    return (price / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _hit(product: _FixtureProduct) -> ProductHit:
    record, offer = product.record, product.offer
    label = _unit_labels().get(
        record.sales_unit, Localized(fi=record.sales_unit, en=record.sales_unit)
    )
    return ProductHit(
        product_id=record.product_id,
        name=record.name,
        category=record.category,
        sales_unit=record.sales_unit,
        sales_unit_label=label,
        image_url=record.image_url,
        unit_price_gross=offer.unit_price_gross,
        price_per_base_unit=_price_per_base_unit(product),
        base_unit=record.base_unit,
        stock_status=product.stock_status,
        available_date=offer.schedule[0].available_date if offer.schedule else None,
        origin=record.origin,
    )


def search_products(caller: Caller, request: SearchProductsRequest) -> SearchProductsResponse:
    """Case-insensitive substring match on the names, then the claim and category filters."""
    q = request.q.casefold()
    hits = [
        p
        for p in _products()
        if q in p.record.name.fi.casefold() or q in p.record.name.en.casefold()
    ]
    hits = [p for p in hits if set(request.claims) <= set(p.record.claims)]
    if request.category is not None:
        hits = [p for p in hits if p.record.category == request.category]
    return SearchProductsResponse(results=[_hit(p) for p in hits[: request.limit]])
