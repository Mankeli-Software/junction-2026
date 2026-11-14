"""Loading the sample product file into Postgres. Needs DATABASE_URL (see conftest.py)."""

import io
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.loaders import images as images_loader
from app.loaders.catalogue import ALLERGEN_CODE_FILE, CATEGORY_FILE, load
from app.loaders.product_file import read_allergen_codes, read_categories
from app.models import Product, ProductAllergen, ProductClaim, ProductImage, ProductUnit

SAMPLE = Path(__file__).parent / "fixtures" / "products_sample.json"
IMAGE_SAMPLE = Path(__file__).parent / "fixtures" / "product_images_sample.json"


@pytest.fixture(autouse=True)
async def no_products(db_engine):
    """Start from an empty catalogue: other tests leave the shared test catalogue loaded."""
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM products"))


async def _load(engine, products=None, images=None):
    if products is None:
        products = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return await load(
        engine,
        products,
        read_categories(CATEGORY_FILE),
        read_allergen_codes(ALLERGEN_CODE_FILE),
        images,
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


# --- Product images (#108) ---------------------------------------------------------------


def _sample_images():
    return images_loader.read_image_file(IMAGE_SAMPLE)


async def _image_rows(engine):
    async with engine.connect() as conn:
        rows = await conn.execute(select(ProductImage.product_id, ProductImage.image_url))
        return dict(rows.all())


async def test_the_catalogue_load_fills_the_image_urls(db_engine):
    images = _sample_images()
    result = await _load(db_engine, images=images)

    stored = await _image_rows(db_engine)
    assert stored["464073"] == images["464073"].url
    assert stored["464073"].startswith("https://api.valioaimo.fi/medias/")
    assert "461963" not in stored  # no image in the map: the clients show the placeholder
    assert result.counts["images"] == len(stored) == 13
    assert result.counts["images_by_gtin"] == 13
    assert result.counts["images_by_name"] == 0
    anomalies = {(a.kind, a.product_id) for a in result.anomalies}
    # Map entries for products outside this load are skipped and reported.
    assert ("image_not_in_catalogue", "460121") in anomalies
    assert ("product_without_image", "461963") in anomalies
    assert ("product_without_image", "464440") in anomalies


async def test_a_load_without_images_keeps_the_stored_ones(db_engine):
    await _load(db_engine, images=_sample_images())
    before = await _image_rows(db_engine)

    result = await _load(db_engine)

    assert await _image_rows(db_engine) == before
    assert "images" not in result.counts


async def test_the_images_refresh_alone_and_can_be_rerun(db_engine):
    await _load(db_engine)
    async with db_engine.connect() as conn:
        loaded_at = await conn.scalar(select(Product.loaded_at).where(Product.id == "464073"))
    images = {
        **_sample_images(),
        "464768": images_loader.ImageEntry("https://api.valioaimo.fi/medias/x", "name"),
        "999999": images_loader.ImageEntry("https://api.valioaimo.fi/medias/y", "gtin"),
    }

    first = await images_loader.load(db_engine, images)
    second = await images_loader.load(db_engine, images)

    assert (
        first.counts
        == second.counts
        == {
            "images": 13,
            "images_by_gtin": 12,
            "images_by_name": 1,
        }
    )
    assert (await _image_rows(db_engine))["464768"] == "https://api.valioaimo.fi/medias/x"
    assert ("image_not_in_catalogue", "999999") in {
        (a.kind, a.product_id) for a in second.anomalies
    }
    async with db_engine.connect() as conn:
        match = await conn.scalar(
            select(ProductImage.image_match).where(ProductImage.product_id == "464768")
        )
        assert match == "name"
        reloaded_at = await conn.scalar(select(Product.loaded_at).where(Product.id == "464073"))
    assert reloaded_at == loaded_at  # the products themselves are not reloaded

    report = io.StringIO()
    images_loader.report(second, report)
    assert "images_by_name" in report.getvalue()
    assert "product_without_image: 2" in report.getvalue()


def test_the_committed_image_file_reads():
    images = images_loader.read_image_file()

    assert len(images) == 13598
    assert sum(e.match == "name" for e in images.values()) == 166
    assert images["460000"].url.startswith("https://api.valioaimo.fi/medias/300Wx300H-")


def test_an_unknown_match_kind_is_refused(tmp_path):
    path = tmp_path / "images.json"
    path.write_text(json.dumps({"1": {"image": "https://x/y", "match": "namesearch"}}))

    with pytest.raises(ValueError, match="unknown match"):
        images_loader.read_image_file(path)
