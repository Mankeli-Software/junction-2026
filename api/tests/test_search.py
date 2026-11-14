"""Product search (#30, docs/plans/30-product-search.md §6.1).

The parsing tests need nothing. The search tests load the loader sample (the milk
shortlist) plus a set of distractors (coffee milk, low-lactose and cooked mince, ...) and
need DATABASE_URL (see conftest.py). Search quality on the full catalogue is measured
with `python -m app.search.eval`, not here.
"""

import json
from pathlib import Path

import pytest

from app.loaders.catalogue import ALLERGEN_CODE_FILE, CATEGORY_FILE, load
from app.loaders.product_file import read_allergen_codes, read_categories
from app.schemas.common import Claim
from app.search import search_products
from app.search.text import parse_query, unasked_modifiers

FIXTURES = Path(__file__).parent / "fixtures"

# In the samples: lactose-free milks (FREE_FROM_LACTOSE, category 10400).
LACTOSE_FREE_MILKS = {"462775", "464073", "464119", "464201", "464306", "464440", "464768"}
COFFEE_MILKS = {"462626", "463380"}
LOW_LACTOSE_MILK = "463047"
RAW_BEEF_MINCE = {"463104", "470418"}
COOKED_OR_MIXED_MINCE = {"462832", "463127", "466210"}


def test_amounts_are_joined_and_normalised():
    query = parse_query("Naudan jauheliha 17 % 2 kg 0,5 l")
    assert query.amounts == ("17%", "2kg", "0.5l")
    assert [t.word for t in query.terms] == ["naudan", "jauheliha"]


def test_synonyms_extend_a_word():
    term = parse_query("naudan")
    assert term.terms[0].alternatives == ("naudan", "nauta")


def test_claim_words_can_be_ignored():
    query = parse_query("lactose free milk", ignore=frozenset({"lactose", "free"}))
    assert [t.word for t in query.terms] == ["milk"]


def test_modifiers_count_only_when_not_asked():
    assert unasked_modifiers("Atria Kypsä Naudan Jauheliha", parse_query("jauheliha")) == ("kypsa",)
    assert unasked_modifiers("Atria Kypsä Naudan Jauheliha", parse_query("kypsä jauheliha")) == ()


@pytest.fixture(scope="module")
async def catalogue(db_engine):
    products = []
    for name in ("products_sample.json", "products_search_sample.json"):
        products += json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    await load(
        db_engine,
        products,
        read_categories(CATEGORY_FILE),
        read_allergen_codes(ALLERGEN_CODE_FILE),
    )
    return db_engine


async def _ids(engine, q, **kwargs):
    async with engine.connect() as conn:
        return [h.product_id for h in await search_products(conn, q, **kwargs)]


async def test_lactose_free_milk_never_returns_low_lactose(catalogue):
    ids = await _ids(catalogue, "maito", claims=[Claim.lactose_free])
    assert LOW_LACTOSE_MILK not in ids
    assert set(ids) >= LACTOSE_FREE_MILKS


async def test_plain_milks_rank_above_coffee_milk(catalogue):
    ids = await _ids(catalogue, "laktoositon maito", claims=[Claim.lactose_free])
    worst_plain = max(ids.index(i) for i in LACTOSE_FREE_MILKS)
    assert all(ids.index(i) > worst_plain for i in COFFEE_MILKS if i in ids)


async def test_english_query_finds_the_same_milks(catalogue):
    en = await _ids(catalogue, "lactose free milk", claims=[Claim.lactose_free])
    # The contract is "no wrong kind in the top 5" (spec §6.2), not a strict order.
    assert set(en[: len(LACTOSE_FREE_MILKS) + 1]) >= LACTOSE_FREE_MILKS
    assert not set(en[:5]) & COFFEE_MILKS


@pytest.mark.parametrize(
    "q", ["laktositon maito", "kevyt maito", "kevyt maitojuoma", "kevytmaitojuomaa"]
)
async def test_typos_and_compounds_find_the_cheapest_milk(catalogue, q):
    assert "464306" in await _ids(catalogue, q)


async def test_vague_mince_puts_raw_beef_first(catalogue):
    ids = await _ids(catalogue, "naudan jauheliha")
    assert set(ids[:2]) == RAW_BEEF_MINCE
    assert not set(ids[:2]) & COOKED_OR_MIXED_MINCE


async def test_refinement_by_fat_percentage(catalogue):
    assert (await _ids(catalogue, "naudan jauheliha 17%"))[0] == "470418"


async def test_category_filter(catalogue):
    ids = await _ids(catalogue, "maito", category="10500")
    assert ids == []
    assert await _ids(catalogue, "voi", category="10500") == ["463798"]


async def test_filters_without_text_return_ids_in_order(catalogue):
    ids = await _ids(catalogue, "", claims=[Claim.lactose_free], category="10400")
    assert ids == sorted(ids)
    assert LOW_LACTOSE_MILK not in ids
    assert set(ids) >= LACTOSE_FREE_MILKS


async def test_empty_query_without_filters_returns_nothing(catalogue):
    assert await _ids(catalogue, "  ") == []


async def test_same_query_same_result(catalogue):
    first = await _ids(catalogue, "maito")
    assert first == await _ids(catalogue, "maito")
