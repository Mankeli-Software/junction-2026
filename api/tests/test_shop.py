"""The webshop's public catalogue (#118). The database tests need DATABASE_URL."""

import csv

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.interfaces.rest.shop import CACHE
from app.loaders.catalogue import CATEGORY_FILE
from app.main import app
from app.models import Product
from app.services import shop
from app.services.errors import NotFoundError
from tests.conftest import catalogue_images, catalogue_products

MILK = "10400"  # Milk and sour milk drinks: the category with the most sample images
SKIMMED_LACTOSE_FREE = "464201"  # in two kitchen types' seeded order history


def with_images(category: str) -> int:
    images = catalogue_images()
    return sum(p["category"] == category and p["id"] in images for p in catalogue_products())


def test_every_shop_path_has_an_english_name():
    names = shop._section_names()
    with CATEGORY_FILE.open(encoding="utf-8") as f:
        paths = [row["shop_path_fi"] for row in csv.DictReader(f)]
    for path in paths:
        place = shop._place(path)
        assert place.section in names, path
        assert place.group in names, path
    assert shop._place(None) == shop._place("") == shop._place("Tuoretuotteet")
    assert shop._place(None).section == shop.OTHER


def test_pack_size_comes_from_the_name():
    assert shop._pack_size("Valio rasvaton maito 1 l") == "1 l"
    assert shop._pack_size("Koskenlaskija 1,5 kg") == "1,5 kg"
    assert shop._pack_size("Peruna e10 kg") == "10 kg"
    assert shop._pack_size("Arla Maitojuoma 1L laktoositon") == "1 l"
    assert shop._pack_size("Lautasliina valkoinen") is None


async def test_the_tree_lists_only_categories_with_images(db: AsyncSession):
    catalogue = await shop.load_catalogue(db)
    listed = {
        c.id: c.product_count
        for section in catalogue.sections
        for group in section.groups
        for c in group.categories
    }
    assert listed[MILK] == with_images(MILK) > 3
    assert all(count > 0 for count in listed.values())
    fresh = catalogue.sections[0]
    assert fresh.name.fi == "Tuoretuotteet" and fresh.name.en == "Fresh products"
    dairy = next(g for g in fresh.groups if g.name.fi == "Maitotaloustuotteet")
    assert dairy.name.en == "Dairy"
    assert MILK in [c.id for c in dairy.categories]
    # Sections follow data/shop_sections.csv.
    order = [name for name in shop._section_names() if shop.SEPARATOR not in name]
    names = [s.name.fi for s in catalogue.sections]
    assert names == sorted(names, key=order.index)


async def test_a_category_lists_its_top_products_with_images(db: AsyncSession):
    result = await shop.load_products(db, MILK)
    ids = [p.product_id for p in result.products]
    assert len(ids) == with_images(MILK) == result.category.product_count
    assert set(ids) <= catalogue_images().keys()
    assert result.section.en == "Fresh products" and result.group.en == "Dairy"
    assert ids[0] == SKIMMED_LACTOSE_FREE  # in the seeded histories
    # Then by recipe use, Valio's own first, then by name.
    uses = shop._recipe_uses()
    recipes = dict((await db.execute(select(uses.c.product_id, uses.c.n))).all())
    vendors = dict((await db.execute(select(Product.id, Product.vendor_name))).all())
    keys = [
        (
            -recipes.get(p.product_id, 0),
            not shop._is_valio(p.brand, vendors[p.product_id]),
            p.name.fi.casefold(),
        )
        for p in result.products[1:]
    ]
    assert keys == sorted(keys)
    assert all(p.image_url.startswith("https://") for p in result.products)
    assert all(p.units_per_sales_unit >= 1 for p in result.products)


async def test_at_most_top_products(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(shop, "TOP", 3)
    result = await shop.load_products(db, MILK)
    assert len(result.products) == 3 == result.category.product_count


async def test_an_unknown_category_is_not_found(db: AsyncSession):
    with pytest.raises(NotFoundError):
        await shop.load_products(db, "no-such-category")


def test_the_endpoints_are_public(app_db: AsyncEngine):
    client = TestClient(app, base_url="http://localhost")
    tree = client.get("/api/v1/shop/categories")
    assert tree.status_code == 200
    assert tree.headers["cache-control"] == CACHE
    assert tree.json()["sections"]
    products = client.get(f"/api/v1/shop/categories/{MILK}/products")
    assert products.status_code == 200
    body = products.json()
    assert body["category"]["id"] == MILK
    assert not {"price", "price_cents", "stock", "availability"} & body["products"][0].keys()
    assert client.get("/api/v1/shop/categories/nope/products").status_code == 404
