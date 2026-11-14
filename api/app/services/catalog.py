"""The catalogue for the services: product search (#30) and product records from the
catalogue tables (#29), plus the `search_products` tool with price and availability (#31).

`search_candidates()` and `get_products()` are what the quote service (#45) calls. Search is
neutral about the kitchen (docs/plans/30-product-search.md §7.1): the engine applies the
allergen and diet exclusions.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import valio
from app.engine.text import unit_name
from app.engine.units import base_measure
from app.models import (
    Product,
    ProductAllergen,
    ProductClaim,
    ProductSubstitution,
    ProductUnit,
    ProductUnitConversion,
)
from app.schemas import (
    Claim,
    Localized,
    Offer,
    ProductHit,
    ProductRecord,
    SearchProductsRequest,
    SearchProductsResponse,
    StockStatus,
)
from app.schemas.engine import ProductAllergen as AllergenEntry
from app.schemas.engine import UnitConversion
from app.search import CLAIM_IDS
from app.search import search_products as search
from app.services.caller import Caller
from app.services.policy import get_rule_set

# Catalogue claim ids (product_claims.claim_id) as the contract's claims.
_CLAIMS = {claim_id: claim for claim, claim_id in CLAIM_IDS.items()}
_THOUSAND = Decimal(1000)
# The unit codes the engine converts asked litres and kilos to.
_MEASURES = {"L", "KG"}


async def search_candidates(
    db: AsyncSession,
    q: str | None,
    claims: Sequence[Claim],
    category: str | None,
    limit: int = 20,
    semantic: bool = False,
) -> list[ProductRecord]:
    """Product records for one line, in the search's order (score, then product id).

    No words with a claim or category gives that filtered set by product id; no words and
    no filter gives nothing. semantic ranks by meaning only (substitute searches, #78).
    """
    hits = await search(
        db, q or "", claims=claims, category=category, limit=limit, semantic=semantic
    )
    return await get_products(db, [hit.product_id for hit in hits])


async def get_products(db: AsyncSession, ids: Sequence[str]) -> list[ProductRecord]:
    """The records for these ids, in the order given. Unknown ids are left out."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []
    products = {p.id: p for p in await db.scalars(select(Product).where(Product.id.in_(wanted)))}
    found = sorted(products)

    async def rows(model, *order):
        query = select(model).where(model.product_id.in_(found)).order_by(*order)
        grouped = defaultdict(list)
        for row in await db.scalars(query):
            grouped[row.product_id].append(row)
        return grouped

    units = await rows(ProductUnit, ProductUnit.size_in_base_units, ProductUnit.unit_id)
    conversions = await rows(ProductUnitConversion, ProductUnitConversion.packaging_type)
    allergens = await rows(ProductAllergen, ProductAllergen.code, ProductAllergen.containment)
    claims = await rows(ProductClaim, ProductClaim.claim_id, ProductClaim.qualifier)
    substitutions = await rows(
        ProductSubstitution, ProductSubstitution.position, ProductSubstitution.substitute_product_id
    )
    return [
        _record(
            products[i],
            units[i],
            conversions[i],
            allergens[i],
            claims[i],
            substitutions[i],
        )
        for i in wanted
        if i in products
    ]


def _record(
    product: Product,
    units: list[ProductUnit],
    conversions: list[ProductUnitConversion],
    allergens: list[ProductAllergen],
    claims: list[ProductClaim],
    substitutions: list[ProductSubstitution],
) -> ProductRecord:
    return ProductRecord(
        product_id=product.id,
        name=Localized(fi=product.name_fi, en=product.name_en or product.name_fi),
        category=product.category_id,
        sales_unit=product.sales_unit,
        base_unit=product.base_unit,
        units=[u.unit_id for u in units],
        unit_conversions=_conversions(product, units, conversions),
        allergens=[AllergenEntry(code=a.code, containment=a.containment) for a in allergens],
        allergen_listing=product.has_classifications,
        claims=sorted({_CLAIMS[c.claim_id] for c in claims if c.claim_id in _CLAIMS}),
        origin=product.country_of_origin.upper() if product.country_of_origin else None,
        image_url=None,  # product images come with #33
        substitutions=[s.substitute_product_id for s in substitutions],
    )


def _conversions(
    product: Product, units: list[ProductUnit], conversions: list[ProductUnitConversion]
) -> list[UnitConversion]:
    """The packaging levels in base units (KI = 20 ST), then each level's net content in
    litres or kilos (ST = 1 L). Synkka gives the net content in one unit only, so a milk
    converts to litres and not to kilos. The net weight counts only for a level with no
    net content at all.

    A packaging level named after a measure (`KG` or `L` in `units[]`, for example
    "KG = 1 ST" on a 1 l milk) is not a conversion: only the net content says how much
    one level holds."""
    out = [
        UnitConversion(from_unit=u.unit_id, to_unit=product.base_unit, factor=u.size_in_base_units)
        for u in units
        if u.unit_id != product.base_unit
        and u.unit_id not in _MEASURES
        and u.size_in_base_units > 0
    ]
    for c in conversions:
        if c.unit_id is None:
            continue
        if c.volume_ml:
            to_unit, amount = "L", c.volume_ml
        elif c.content_weight_g or (c.net_weight_g and not c.content_pieces):
            to_unit, amount = "KG", c.content_weight_g or c.net_weight_g
        else:
            continue
        out.append(UnitConversion(from_unit=c.unit_id, to_unit=to_unit, factor=amount / _THOUSAND))
    return out


# --- The search_products tool -----------------------------------------------------------


async def search_products(
    db: AsyncSession, caller: Caller, request: SearchProductsRequest
) -> SearchProductsResponse:
    """Search results with today's price and availability for the shortlist (#31).

    Neutral about the kitchen, like the search: the engine applies the exclusions when a
    product is put on a quote. Without `needed_by`, availability is asked for the business
    day (the frozen demo clock).
    """
    records = await search_candidates(
        db, request.q, request.claims, request.category, limit=request.limit
    )
    rules = get_rule_set()
    needed_by = request.needed_by or rules.policy.business_time.date()
    offers = {
        o.product_id: o for o in await valio.get_offers([r.product_id for r in records], needed_by)
    }
    return SearchProductsResponse(
        results=[_hit(r, offers.get(r.product_id), rules) for r in records]
    )


def _hit(record: ProductRecord, offer: Offer | None, rules) -> ProductHit:
    sales_unit = (offer.sales_unit if offer else None) or record.sales_unit
    price = offer.unit_price_gross if offer and offer.ok else None
    measure = base_measure(record, sales_unit)
    per_base = (
        (price / measure[0]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if price is not None and measure
        else None
    )
    stock, available = _stock(offer, rules.policy.unverified_stock_threshold)
    return ProductHit(
        product_id=record.product_id,
        name=record.name,
        category=record.category,
        sales_unit=sales_unit,
        sales_unit_label=unit_name(rules, sales_unit),
        image_url=record.image_url,
        unit_price_gross=price,
        price_per_base_unit=per_base,
        base_unit=measure[1] if measure else None,
        stock_status=stock,
        available_date=available,
        origin=record.origin,
    )


def _stock(offer: Offer | None, unverified_at: Decimal) -> tuple[StockStatus, date | None]:
    """Unavailable when the offer failed, is blocked or has nothing in stock; unverified for
    the "unknown stock" placeholder amounts. The date is the earliest one with stock."""
    if offer is None or not offer.ok or offer.sales_block:
        return StockStatus.unavailable, None
    in_stock = sorted((s for s in offer.schedule if s.amount > 0), key=lambda s: s.available_date)
    if not in_stock:
        return StockStatus.unavailable, None
    if max(s.amount for s in in_stock) >= unverified_at:
        return StockStatus.unverified, in_stock[0].available_date
    return StockStatus.verified, in_stock[0].available_date
