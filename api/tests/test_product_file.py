"""Parsing the product file into catalogue rows, without a database."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.loaders.product_file import parse_product, resolve_conversion_unit

SAMPLE = Path(__file__).parent / "fixtures" / "products_sample.json"
LOADED_AT = datetime(2026, 11, 14, tzinfo=UTC)


@pytest.fixture(scope="module")
def products() -> dict[str, dict]:
    return {p["id"]: p for p in json.loads(SAMPLE.read_text(encoding="utf-8"))}


def test_lactose_free_milk(products):
    rows = parse_product(products["464073"], LOADED_AT)

    assert rows.product["name_fi"] == "Valio täysmaito 1 l laktoositon UHT"
    assert rows.product["sales_unit"] == "ST"
    assert rows.product["has_classifications"] is True
    assert {"claim_id": "FREE_FROM_LACTOSE", "qualifier": "FREE_FROM"}.items() <= next(
        c for c in rows.claims if c["claim_id"] == "FREE_FROM_LACTOSE"
    ).items()
    ki = next(u for u in rows.units if u["unit_id"] == "KI")
    assert ki["size_in_base_units"] == Decimal(10)
    (conversion,) = rows.conversions
    assert conversion["unit_id"] == "ST"
    assert conversion["volume_ml"] == Decimal(1000)
    assert conversion["net_weight_g"] == Decimal(1027)
    assert rows.substitutions == [
        {"product_id": "464073", "substitute_product_id": "464768", "position": 0}
    ]
    assert rows.anomalies == []


def test_product_without_classifications_is_reported(products):
    rows = parse_product(products["461963"], LOADED_AT)

    assert rows.product["has_classifications"] is False
    assert rows.allergens == []
    assert "no_classifications" in {a.kind for a in rows.anomalies}


def test_contradicting_allergen_keeps_both_rows(products):
    rows = parse_product(products["468044"], LOADED_AT)

    am = {a["containment"] for a in rows.allergens if a["code"] == "AM"}
    assert am == {"CONTAINS", "FREE_FROM"}
    assert any(a.kind == "allergen_contradiction" for a in rows.anomalies)


def test_volume_in_grams_is_net_content_weight(products):
    rows = parse_product(products["460001"], LOADED_AT)

    (conversion,) = rows.conversions
    assert conversion["volume_ml"] is None
    assert conversion["content_weight_g"] is not None


def test_volume_in_pieces(products):
    rows = parse_product(products["460010"], LOADED_AT)

    (conversion,) = rows.conversions
    assert conversion["content_pieces"] == Decimal(1)


def test_temperature_markers_are_not_certificates(products):
    rows = parse_product(products["464073"], LOADED_AT)

    kinds = {label["label_id"]: label["kind"] for label in rows.labels}
    assert kinds["warmTemperature"] == "temperature"
    assert all(kind == "certificate" for label, kind in kinds.items() if "Temperature" not in label)


def _product(units, sales="KI", base="ST", gtin=None):
    return {
        "salesUnit": sales,
        "baseUnit": base,
        "units": units,
        "synkkaData": {"gtin": gtin},
    }


def test_conversion_unit_follows_the_gtin_first():
    product = _product([{"unitId": "ST", "gtin": "1"}, {"unitId": "KI", "gtin": "2"}], gtin="1")
    assert resolve_conversion_unit(product, "CASE") == "ST"


def test_conversion_unit_by_packaging_type():
    product = _product([{"unitId": "ST"}, {"unitId": "KI"}, {"unitId": "PAL"}])
    assert resolve_conversion_unit(product, "BASE_UNIT_OR_EACH") == "ST"
    assert resolve_conversion_unit(product, "CASE") == "KI"
    assert resolve_conversion_unit(product, "PALLET") == "PAL"


def test_conversion_unit_of_a_single_unit_product():
    product = _product([{"unitId": "KI"}], sales="KI", base="KI")
    assert resolve_conversion_unit(product, "CASE") == "KI"


def test_conversion_unit_unresolved():
    product = _product([{"unitId": "KI"}, {"unitId": "PAL"}], sales="KI", base="KI")
    assert resolve_conversion_unit(product, "CASE") is None
