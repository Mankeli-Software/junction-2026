"""Availability, units and rounding (#38): hand-built cases and the recorded snapshot."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.valio import SnapshotStore, build_offer
from app.engine import decide
from app.engine.units import name_size
from app.schemas import (
    Claim,
    Decision,
    Localized,
    OfferSource,
    ProductAllergen,
    ProductRecord,
    RequestedUnit,
    StockStatus,
    UnitConversion,
)
from tests.engine_fixtures import BUSINESS_NOW, MONDAY, engine_input, milk_line, offer, product

# --- Pack size from the name -------------------------------------------------------------


def _named(fi: str, en: str | None = None) -> ProductRecord:
    record = product("1", fi)
    return record.model_copy(update={"name": Localized(fi=fi, en=en or fi)})


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Valio täysmaito 1 l laktoositon UHT", (Decimal("1"), "L")),
        ("Valio kevytmaito 0,5 l", (Decimal("0.5"), "L")),
        ("Arla Maitojuoma 1L rasvaton", (Decimal("1"), "L")),
        ("Kermajuusto 500 g", (Decimal("0.5"), "KG")),
        ("Voi 2,5 kg", (Decimal("2.5"), "KG")),
        ("Jogurtti 6 x 150 g", (Decimal("0.9"), "KG")),
        ("Kahvikerma 2 dl", (Decimal("0.2"), "L")),
    ],
)
def test_pack_size_is_read_from_the_name(name, expected):
    assert name_size(_named(name)) == expected


@pytest.mark.parametrize(
    ("fi", "en"),
    [
        ("Juusto 17 % viipale", None),  # a percentage is no size
        ("Maito 1 l", "Milk 2 l"),  # the names disagree
        ("Juusto 400 g / 1 kg", None),  # two sizes
        ("Valio PROfeel proteiinijuoma", None),
    ],
)
def test_no_single_size_in_the_name_is_none(fi, en):
    assert name_size(_named(fi, en)) is None


def _without_conversions(record: ProductRecord) -> ProductRecord:
    keep = [c for c in record.unit_conversions if c.to_unit not in ("L", "KG")]
    return record.model_copy(update={"unit_conversions": keep})


def test_pack_size_from_the_name_is_used_and_flagged():
    milk = _without_conversions(product("1", "Maito 0,5 l"))
    out = decide(
        engine_input(
            milk_line(quantity="10"),
            candidates={"milk": ["1"]},
            products=[milk],
            offers=[offer("1", "1.00")],
        )
    )

    [line] = out.lines
    assert line.quantity_sales_units == 20
    assert line.price_per_base_unit == Decimal("2.0000")
    assert "PACK_SIZE_FROM_NAME" in line.reason_codes
    assert ("PACK_SIZE_FROM_NAME", "acknowledge") in [(f.code, f.kind) for f in out.flags]


def test_a_conversion_wins_over_the_name_and_is_not_flagged():
    out = decide(
        engine_input(
            milk_line(quantity="10"),
            candidates={"milk": ["1"]},
            products=[product("1", "Maito 2 l", litres="1")],
            offers=[offer("1", "1.00")],
        )
    )

    assert out.lines[0].quantity_sales_units == 10
    assert "PACK_SIZE_FROM_NAME" not in out.lines[0].reason_codes


# --- Sales unit checked against the price ratio ------------------------------------------


def _with_comparison(pid: str, price: str, comparison: str, unit: str = "L", **kw):
    return offer(pid, price, **kw).model_copy(
        update={"comparison_price_gross": Decimal(comparison), "comparison_unit": unit}
    )


def test_price_ratio_that_matches_the_case_size_passes():
    case = product("1", "Maito 1 l", sales_unit="KI", per_case=10)
    out = decide(
        engine_input(
            milk_line(quantity="20"),
            candidates={"milk": ["1"]},
            products=[case],
            offers=[_with_comparison("1", "15.12", "1.51", sales_unit="KI")],
        )
    )

    assert out.decision == Decision.ready
    assert out.lines[0].quantity_sales_units == 2


def test_price_ratio_that_disagrees_with_the_sales_unit_is_unit_unknown():
    # Availability says ST, but the price is for a case of 10 litres.
    out = decide(
        engine_input(
            milk_line(quantity="20"),
            candidates={"milk": ["1"]},
            products=[product("1", "Maito 1 l", per_case=10)],
            offers=[_with_comparison("1", "15.12", "1.51")],
        )
    )

    assert out.decision == Decision.rejected
    assert out.rejections[0].reason_code == "UNIT_UNKNOWN"


def test_price_ratio_is_skipped_when_the_size_is_unknown():
    unknown = _without_conversions(product("1", "Maito"))
    out = decide(
        engine_input(
            milk_line(quantity="3", unit=RequestedUnit.sales_unit),
            candidates={"milk": ["1"]},
            products=[unknown],
            offers=[_with_comparison("1", "2.00", "1.00")],
        )
    )

    assert out.decision == Decision.ready


# --- Units that fail go back to the buyer ------------------------------------------------


def test_unknown_conversion_asks_the_buyer():
    out = decide(
        engine_input(
            milk_line(quantity="5", unit=RequestedUnit.kg),
            candidates={"milk": ["1"]},
            products=[product("1", "Maito")],  # litres only, no weight
            offers=[offer("1", "1.00")],
        )
    )

    assert out.decision == Decision.needs_clarification
    assert out.lines == []
    assert "sales units" in out.clarification.question.en


def test_packaging_word_with_two_sizes_asks_the_buyer():
    record = product("1", "Maito 1 l", per_case=10)
    record = record.model_copy(
        update={
            "units": ["ST", "KI", "CASE"],
            "unit_conversions": [
                *record.unit_conversions,
                UnitConversion(from_unit="CASE", to_unit="ST", factor=Decimal(6)),
            ],
        }
    )
    out = decide(
        engine_input(
            milk_line(quantity="2", unit=RequestedUnit.package, package_word="laatikkoa"),
            candidates={"milk": ["1"]},
            products=[record],
            offers=[offer("1", "1.00")],
        )
    )

    assert out.decision == Decision.needs_clarification
    assert "more than one size" in out.clarification.question.en


def test_packaging_word_with_one_size_converts():
    out = decide(
        engine_input(
            milk_line(quantity="2", unit=RequestedUnit.package, package_word="laatikkoa"),
            candidates={"milk": ["1"]},
            products=[product("1", "Maito 1 l", per_case=10)],
            offers=[offer("1", "1.00")],
        )
    )

    assert out.lines[0].quantity_sales_units == 20


# --- Waste first --------------------------------------------------------------------------

LITRE = product("1L", "Maito 1 l")
FIVE = product("5L", "Maito 5 l", litres="5")
TEN = product("10L", "Maito 10 l", litres="10")


def test_an_exact_fit_beats_a_cheaper_product_with_waste():
    # 12 litres: twelve 1 l packs fit exactly; three 5 l packs are cheaper but waste 3 l.
    out = decide(
        engine_input(
            milk_line(quantity="12"),
            candidates={"milk": ["5L", "1L"]},
            products=[LITRE, FIVE],
            offers=[offer("1L", "2.00"), offer("5L", "4.00")],
        )
    )

    [line] = out.lines
    assert line.product_id == "1L"
    assert line.alternatives == []  # the wasteful one is not offered
    assert "ROUNDED_UP" not in line.reason_codes


def test_price_decides_among_candidates_within_the_limits():
    # 100 litres: both fit exactly, the 10 l pack is cheaper per litre.
    out = decide(
        engine_input(
            milk_line(quantity="100"),
            candidates={"milk": ["1L", "10L"]},
            products=[LITRE, TEN],
            offers=[offer("1L", "2.00"), offer("10L", "15.00")],
        )
    )

    [line] = out.lines
    assert line.product_id == "10L"
    assert [a.product_id for a in line.alternatives] == ["1L"]


def test_a_small_round_up_within_the_limits_is_not_flagged():
    # 99.5 litres → 100 packs: 0.5 l over, under one pack and under 2 %.
    out = decide(
        engine_input(
            milk_line(quantity="99.5"),
            candidates={"milk": ["1L"]},
            products=[LITRE],
            offers=[offer("1L", "2.00")],
        )
    )

    [line] = out.lines
    assert line.quantity_sales_units == 100
    assert "ROUNDED_UP" in line.reason_codes
    assert all(f.code != "ROUNDED_UP" for f in out.flags)


def test_without_a_fit_the_least_surplus_wins_and_must_be_acknowledged():
    # 12 litres: 5 l packs waste 3 l, 10 l packs waste 8 l but are cheaper.
    out = decide(
        engine_input(
            milk_line(quantity="12"),
            candidates={"milk": ["10L", "5L"]},
            products=[FIVE, TEN],
            offers=[offer("5L", "4.00"), offer("10L", "5.00")],
        )
    )

    [line] = out.lines
    assert line.product_id == "5L"
    assert line.quantity_sales_units == 3
    assert [a.product_id for a in line.alternatives] == ["10L"]
    [flag] = [f for f in out.flags if f.code == "ROUNDED_UP"]
    assert flag.kind == "acknowledge"
    assert flag.flag_key == "ROUNDED_UP:milk"
    assert flag.text.en == "I rounded Maito 5 l up to 3 pieces to make whole sales units."


# --- Availability -------------------------------------------------------------------------


def test_a_sales_block_makes_the_product_unavailable():
    blocked = offer("1L", "2.00").model_copy(update={"sales_block": True})
    out = decide(
        engine_input(
            milk_line(quantity="1"),
            candidates={"milk": ["1L"]},
            products=[LITRE],
            offers=[blocked],
        )
    )

    assert out.rejections[0].reason_code == "UNAVAILABLE"


def test_stock_available_only_after_the_needed_date_is_unreachable():
    out = decide(
        engine_input(
            milk_line(quantity="1", needed_by=date(2026, 11, 13)),
            candidates={"milk": ["1L"]},
            products=[LITRE],
            offers=[offer("1L", "2.00", available=MONDAY)],
        )
    )

    assert out.rejections[0].reason_code == "DELIVERY_DATE_UNREACHABLE"


def test_past_the_closing_time_is_rejected():
    out = decide(
        engine_input(
            milk_line(quantity="1"),
            candidates={"milk": ["1L"]},
            products=[LITRE],
            offers=[offer("1L", "2.00", closing="2026-11-12T08:59:00+02:00")],
        )
    )

    assert out.rejections[0].reason_code == "PAST_CLOSING_TIME"


# --- The recorded snapshot ----------------------------------------------------------------

SAMPLE = Path(__file__).parent / "fixtures" / "products_sample.json"
SNAPSHOT_IDS = ["464073", "464201", "464306", "462775", "463380", "464119", "464440"]


def _record(raw: dict) -> ProductRecord:
    """A ProductRecord from the product file, as the real `get_products()` (#30) will build it:
    `units[]` become conversions to the base unit; litres come only from the name here."""
    synkka = raw["synkkaData"]
    names = {n["language"]: n["value"] for n in synkka["names"]}
    groups = {c["name"]: c.get("values", []) for c in synkka.get("classifications") or []}
    claims = [
        Claim.lactose_free
        for v in groups.get("nutritionalClaim", [])
        if v["id"] == "FREE_FROM_LACTOSE"
    ]
    allergens = [
        ProductAllergen(code=v["id"], containment=v["unit"])
        for v in groups.get("allergen", [])
        if v.get("unit") in ("CONTAINS", "MAY_CONTAIN", "FREE_FROM", "UNDECLARED")
    ]
    return ProductRecord(
        product_id=raw["id"],
        name=Localized(fi=names["fi"], en=names.get("en", names["fi"])),
        category=raw["category"],
        sales_unit=raw["salesUnit"],
        base_unit=raw["baseUnit"],
        units=[u["unitId"] for u in raw["units"]],
        unit_conversions=[
            UnitConversion(
                from_unit=u["unitId"],
                to_unit=raw["baseUnit"],
                factor=Decimal(str(u["sizeInBaseUnits"])),
            )
            for u in raw["units"]
            if u["unitId"] != raw["baseUnit"] and u["unitId"] not in ("KG", "ZML")
        ],
        allergens=allergens,
        allergen_listing=bool(groups),
        claims=sorted(set(claims)),
        origin=(raw.get("countryOfOrigin") or "").upper() or None,
        image_url=None,
        substitutions=[],
    )


@pytest.fixture(scope="module")
def snapshot():
    raw = {p["id"]: p for p in json.loads(SAMPLE.read_text())}
    products = [_record(raw[pid]) for pid in SNAPSHOT_IDS]
    store = SnapshotStore()
    prices = store.get("price", SNAPSHOT_IDS, MONDAY)
    stock = store.get("availability", SNAPSHOT_IDS, MONDAY)
    offers = [
        build_offer(pid, prices.get(pid), stock.get(pid), OfferSource.snapshot, now=BUSINESS_NOW)
        for pid in SNAPSHOT_IDS
    ]
    return products, offers


def _snapshot_quote(snapshot, pid: str, quantity: str = "20", unit=RequestedUnit.l):
    products, offers = snapshot
    return decide(
        engine_input(
            milk_line(quantity=quantity, unit=unit),
            candidates={"milk": [pid]},
            products=products,
            offers=offers,
        )
    )


@pytest.mark.parametrize("pid", ["464201", "464306"])
def test_snapshot_unlimited_stock_is_orderable_and_unverified(snapshot, pid):
    out = _snapshot_quote(snapshot, pid)

    assert out.decision == Decision.ready
    [line] = out.lines
    assert line.quantity_sales_units == 20
    assert line.stock_status == StockStatus.unverified
    assert "PACK_SIZE_FROM_NAME" in line.reason_codes


def test_snapshot_limited_stock_is_verified_until_it_runs_out(snapshot):
    assert _snapshot_quote(snapshot, "463380", "698").lines[0].stock_status == StockStatus.verified
    partial = _snapshot_quote(snapshot, "463380", "699")
    assert partial.rejections[0].reason_code == "PARTIAL_STOCK"


def test_snapshot_terminal_stock_in_cases_is_unverified(snapshot):
    out = _snapshot_quote(snapshot, "464119", "25")

    [line] = out.lines
    assert line.sales_unit == "KI"
    assert line.quantity_sales_units == 3  # 30 l for 25 l: the only candidate, so flagged
    assert line.stock_status == StockStatus.unverified
    assert {f.code for f in out.flags} >= {"ROUNDED_UP", "AVAILABILITY_UNVERIFIED"}


def test_snapshot_empty_schedule_is_unavailable(snapshot):
    assert _snapshot_quote(snapshot, "464440").rejections[0].reason_code == "UNAVAILABLE"


def test_snapshot_small_stock_runs_out_first(snapshot):
    assert _snapshot_quote(snapshot, "462775", "51").decision == Decision.ready
    assert _snapshot_quote(snapshot, "462775", "52").rejections[0].reason_code == "PARTIAL_STOCK"


def test_snapshot_price_ratios_agree_with_the_sales_units(snapshot):
    products, offers = snapshot
    for o in offers:
        if o.comparison_price_gross is None:
            continue
        out = _snapshot_quote(snapshot, o.product_id, "1", RequestedUnit.sales_unit)
        assert all(r.reason_code != "UNIT_UNKNOWN" for r in out.rejections), o.product_id


def test_snapshot_milk_scenario_end_to_end(snapshot):
    products, offers = snapshot
    out = decide(
        engine_input(
            milk_line(quantity="1000"),
            candidates={"milk": SNAPSHOT_IDS},
            products=products,
            offers=offers,
        )
    )

    assert out.decision == Decision.ready
    [line] = out.lines
    assert line.quantity_in_asked_unit == Decimal("1000")
    assert line.delivery_date == MONDAY
