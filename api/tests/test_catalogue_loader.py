"""Loading the sample product file into Postgres. Needs DATABASE_URL (see conftest.py)."""

import json
from pathlib import Path

from sqlalchemy import func, select

from app.loaders.catalogue import ALLERGEN_CODE_FILE, CATEGORY_FILE, load
from app.loaders.product_file import read_allergen_codes, read_categories
from app.models import Product, ProductAllergen, ProductClaim, ProductUnit

SAMPLE = Path(__file__).parent / "fixtures" / "products_sample.json"


async def _load(engine, products=None):
    if products is None:
        products = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return await load(
        engine,
        products,
        read_categories(CATEGORY_FILE),
        read_allergen_codes(ALLERGEN_CODE_FILE),
    )


async def _count(engine, model):
    async with engine.connect() as conn:
        return await conn.scalar(select(func.count()).select_from(model))


async def test_loads_the_sample(db_engine):
    result = await _load(db_engine)

    assert result.counts["products"] == 15
    assert result.counts["categories"] == 349
    assert await _count(db_engine, Product) == 15
    assert await _count(db_engine, ProductUnit) == result.counts["units"]
    async with db_engine.connect() as conn:
        claims = (
            await conn.scalars(
                select(ProductClaim.claim_id).where(ProductClaim.product_id == "464073")
            )
        ).all()
    assert "FREE_FROM_LACTOSE" in claims
    anomalies = {(a.kind, a.product_id) for a in result.anomalies}
    assert ("no_classifications", "461963") in anomalies
    assert ("allergen_contradiction", "468044") in anomalies


async def test_reloading_gives_the_same_rows(db_engine):
    first = await _load(db_engine)
    allergens = await _count(db_engine, ProductAllergen)
    second = await _load(db_engine)

    assert first.counts == second.counts
    assert await _count(db_engine, ProductAllergen) == allergens


async def test_products_missing_from_the_file_are_kept_and_reported(db_engine):
    products = json.loads(SAMPLE.read_text(encoding="utf-8"))
    await _load(db_engine, products)

    result = await _load(db_engine, [p for p in products if p["id"] != "460001"])

    assert await _count(db_engine, Product) == 15
    assert ("product_not_in_file", "460001") in {(a.kind, a.product_id) for a in result.anomalies}
