"""Turning catalogue rows into the engine's product record, without a database."""

from app.models import Product, ProductAllergen
from app.services.catalog import _record


def _product(**fields) -> Product:
    return Product(
        id="469393",
        name_fi="GRAN CASTELLI 100G JUUSTORAASTE",
        name_en="GRAN CASTELLI 100G GRATED CHEESE",
        category_id="10603",
        sales_unit="ST",
        base_unit="ST",
        country_of_origin="it",
        has_classifications=True,
        **fields,
    )


def test_classifications_without_allergen_entries_are_no_listing():
    # 469393 has nutrition facts but empty allergen and nonAllergen groups (#113).
    record = _record(_product(), [], [], [], [], [], None)

    assert record.allergen_listing is False


def test_a_free_from_entry_is_a_listing():
    # 475708 declares milk and lactose FREE_FROM and nothing else.
    allergens = [
        ProductAllergen(product_id="475708", code="AM", containment="FREE_FROM"),
        ProductAllergen(product_id="475708", code="ML", containment="FREE_FROM"),
    ]
    record = _record(_product(), [], [], allergens, [], [], None)

    assert record.allergen_listing is True
