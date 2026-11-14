"""Recipes (#34): loader, hybrid search, scaling and recipe lines in build_quote.

The pure parts run everywhere; the rest needs DATABASE_URL and loads the real recipe files
and the committed vectors into the test database (the `recipes` fixture).
"""

import copy
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine
from app.adapters import valio
from app.interfaces.deps import DEV_CALLER
from app.loaders import recipes as loader
from app.models import KitchenProfile as KitchenProfileRow
from app.models import Recipe as RecipeRow
from app.recipes import data as files
from app.recipes import search as recipe_search
from app.recipes.scaling import Pack, choose_pack, scale
from app.schemas import (
    BuildQuoteRequest,
    Decision,
    EngineInput,
    Exclusion,
    GetRecipeRequest,
    LineRequest,
    SearchRecipesRequest,
    UpdateQuoteRequest,
)
from app.services import accounts, quotes, recipes
from app.services.audit import load_rule_set_by_ref
from app.services.caller import Caller
from app.services.errors import InvalidRequestError, NotFoundError
from app.settings import get_settings
from tests.conftest import load_recipes
from tests.phones import new_number

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
DAY = "2026-11-16"
# Rukiinen piimäleipä, 6 portions: piimä and butter are linked to products in the test
# catalogue; salt, yeast and the two flours are not linked.
BREAD = "31863"
# Mausteinen chai-tea: cinnamon has no amount.
CHAI = "33188"


# --- Pure parts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("per_portion", "portions", "unit", "expected"),
    [
        ("0.19444444444444445", 200, "kg", "38.9"),
        ("0.19444444444444445", 18, "kg", "3.5"),
        ("0.0003888888888888889", 1, "kg", "0.000389"),
        ("0.005", 40, "kg", "0.2"),
        ("0.0833333", 1000, "kg", "83.3"),
        ("1.2", 100, "kg", "120"),
        ("0.5", 3, "kpl", "2"),
        ("0.34", 7, "kpl", "3"),
    ],
)
def test_scaling_rounds_to_three_significant_digits_or_whole_pieces(
    per_portion, portions, unit, expected
):
    result = scale(Decimal(per_portion), portions, unit)
    assert str(result) == expected


def test_the_pack_with_the_least_left_over_wins():
    small = Pack("small", Decimal(20), Decimal("0.2"))  # a case of 20 x 200 g = 4 kg
    single = Pack("single", Decimal(1), Decimal("0.5"))
    unknown = Pack("unknown", Decimal(1), None)

    assert choose_pack([small, single, unknown], Decimal("0.9")).product_id == "single"
    assert choose_pack([small, single, unknown], Decimal("3.9")).product_id == "small"
    # Equal left over: fewer sales units.
    assert choose_pack([small, single], Decimal("4")).product_id == "small"
    assert choose_pack([unknown], Decimal(1)).product_id == "unknown"
    assert choose_pack([], Decimal(1)) is None


@pytest.mark.parametrize(
    ("q", "words", "diets"),
    [
        ("pasta 50 hengelle laktoositon", "pasta", ["laktoositon"]),
        ("Gluten-free lasagne for 200 people", "lasagne for", ["gluteeniton"]),
        ("maidoton ja vegaaninen keitto", "ja keitto", ["maidoton", "vegaaninen"]),
        ("lohikeitto", "lohikeitto", []),
    ],
)
def test_diet_words_and_portions_leave_the_query(q, words, diets):
    assert recipe_search.split_query(q) == (words, diets)


def test_rank_fusion_adds_up_the_lists_and_breaks_ties_by_id():
    fused = recipe_search.fuse({"fts": [3, 1], "trigram": [1, 2], "vector": [2, 3]})

    # Each id is once first and once second, so the scores tie and the id decides.
    assert [m.recipe_id for m in fused] == [1, 2, 3]
    assert fused[0].matched_on == ("fts:2", "trigram:1")


def test_the_vector_file_round_trips(tmp_path):
    vector = [0.0] * 767 + [1.0]
    path = tmp_path / "v.json.gz"
    files.write_vector_file({7: files.StoredVector("abc", files.encode_vector(vector))}, path)

    [(recipe_id, stored)] = files.read_vector_file(path).items()
    assert (recipe_id, stored.hash) == (7, "abc")
    assert files.decode_vector(stored.vector) == vector


def test_the_committed_vectors_cover_every_recipe():
    data = files.read_recipe_file()
    texts = files.recipe_texts(data["recipes"], data["taxonomies"])
    stored = files.read_vector_file()

    assert set(stored) == set(texts)
    assert all(stored[i].hash == files.source_hash(t) for i, t in texts.items())
    assert files.VECTOR_FILE.stat().st_size < 10_000_000


# --- Loader -----------------------------------------------------------------------------


def test_generic_ingredients_get_their_hand_made_links():
    # Juustoinen liha-makaronilaatikko (#100): only cheese and milk have a recipe product
    # in the export; macaroni, beef, onion and eggs are linked by ingredient id.
    data = files.read_recipe_file()
    [macaroni_box] = [r for r in data["recipes"] if r["id"] == 38100]

    _, ingredients, _ = loader.recipe_rows(
        [macaroni_box], data["taxonomies"], T0, files.read_ingredient_links()
    )

    assert {i["name"]: i["recipe_product_id"] for i in ingredients} == {
        "makaronia": 900001,
        "vähärasvaista naudan jauhelihaa": 900002,
        "pakastesipulikuutioita": 900003,
        "suolaa": None,
        "valkopippuria": None,
        "Valio juustoraasteseosta": 3157,
        "Valio maitoa": 12,
        "kananmunia": 900004,
    }


def test_every_ingredient_link_is_a_generic_ingredient_with_weighed_packs():
    links = files.read_ingredient_links()
    mappings = files.read_product_map()
    generic = {
        str(i["id"])
        for r in files.read_recipe_file()["recipes"]
        for _, i in files.ingredients(r)
        if not i["productId"]
    }

    assert links and set(links) <= generic
    for key in set(links.values()):
        assert int(key) >= 900001
        entry = mappings[key]
        assert entry["confidence"] == "reviewed" and entry["aimoProducts"]
        # choose_pack needs the weight of a sales unit to cover the scaled kilos.
        assert all(p["netWeightKg"] and p["unitsPerSalesUnit"] for p in entry["aimoProducts"])


async def _counts(db_engine) -> dict[str, int]:
    tables = ("recipes", "recipe_ingredients", "recipe_tags", "recipe_product_links")
    async with db_engine.connect() as conn:
        counts = {t: await conn.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables}
        counts["recipe_embeddings"] = await conn.scalar(
            text("SELECT count(*) FROM recipe_embeddings")
        )
        counts["searchable"] = await conn.scalar(
            text("SELECT count(*) FROM recipes WHERE search_fi IS NOT NULL")
        )
    return counts


async def test_the_loader_is_idempotent(db_engine):
    first = await load_recipes(db_engine)
    after_first = await _counts(db_engine)
    second = await load_recipes(db_engine)

    assert second.counts == first.counts
    assert await _counts(db_engine) == after_first
    assert after_first == {
        "recipes": 2091,
        "recipe_ingredients": 21650,
        "recipe_tags": first.counts["tags"],
        "recipe_product_links": first.counts["product_links"],
        "recipe_embeddings": 2091,
        "searchable": 2091,
    }


async def test_the_loader_drops_removed_recipes_and_outdated_vectors(db_engine):
    data = copy.deepcopy(files.read_recipe_file())
    removed = data["recipes"].pop()
    data["recipes"][0]["name"] += " uusi"  # its stored vector is for the old text
    changed = data["recipes"][0]["id"]

    result = await loader.load(db_engine, data, files.read_product_map(), files.read_vector_file())

    async with db_engine.connect() as conn:
        ids = set((await conn.scalars(text("SELECT id FROM recipes"))).all())
        with_vector = set(
            (await conn.scalars(text("SELECT recipe_id FROM recipe_embeddings"))).all()
        )
    assert removed["id"] not in ids and changed in ids
    assert changed not in with_vector
    assert result.counts["deleted_recipes"] == 1
    assert result.counts["embeddings"] == 2089
    assert any("no current vector" in note for note in result.notes)
    await load_recipes(db_engine)  # back to the real data for the other tests


# --- Search -----------------------------------------------------------------------------


def _vectors(monkeypatch, mode: str):
    monkeypatch.setenv("SEARCH_VECTORS", mode)
    get_settings.cache_clear()


@pytest.fixture
def text_only(monkeypatch):
    _vectors(monkeypatch, "off")
    yield
    get_settings.cache_clear()


async def search(db: AsyncSession, **request) -> list:
    response = await recipes.search_recipes(db, DEV_CALLER, SearchRecipesRequest(**request))
    return response.results


@pytest.mark.usefixtures("recipes", "text_only")
async def test_pasta_for_50_lactose_free(db):
    hits = await search(db, q="pasta 50 hengelle laktoositon", limit=5)

    assert len(hits) == 5
    assert all("laktoositon" in h.diet_tags for h in hits)
    assert all("pasta" in h.name.lower() for h in hits[:4])


@pytest.mark.usefixtures("recipes", "text_only")
async def test_salmon_soup_finds_salmon_soups(db):
    hits = await search(db, q="lohikeitto", limit=5)

    assert all("lohikeitto" in h.name.lower() for h in hits)


@pytest.mark.usefixtures("recipes", "text_only")
async def test_diet_and_occasion_filters(db):
    hits = await search(db, q="kanaa ja riisiä", diet=["milk_free"], limit=10)
    assert hits and all("maidoton" in h.diet_tags for h in hits)

    lunch = await search(db, q="keitto", diet=["Gluteeniton"], occasion="lunch", limit=10)
    assert lunch and all("gluteeniton" in h.diet_tags for h in lunch)
    ids = [int(h.recipe_id) for h in lunch]
    rows = await db.execute(
        text(
            "SELECT DISTINCT recipe_id FROM recipe_tags WHERE value = 'lounasruoka' "
            "AND recipe_id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    assert len(rows.all()) == len(ids)


@pytest.mark.usefixtures("recipes", "text_only")
async def test_only_filters_lists_the_newest_recipes_that_pass(db):
    hits = await search(db, q="vegaaninen", limit=3)

    assert len(hits) == 3 and all("vegaaninen" in h.diet_tags for h in hits)
    ids = [int(h.recipe_id) for h in hits]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.usefixtures("recipes", "text_only")
async def test_an_unknown_diet_is_an_error_that_lists_the_known_ones(db):
    with pytest.raises(InvalidRequestError, match="laktoositon"):
        await search(db, q="pasta", diet=["keto"])


@pytest.mark.usefixtures("recipes", "text_only")
async def test_without_vectors_search_is_text_only(db):
    for q in ("christmas dessert", "lohikeitto"):
        matches = await recipe_search.search(db, recipe_search.RecipeQuery(q, (), None))
        assert all(not m.startswith("vector") for match in matches for m in match.matched_on)
    # The English query finds (almost) nothing by its words alone.
    english = await recipe_search.search(
        db, recipe_search.RecipeQuery("christmas dessert", (), None)
    )
    assert 40695 not in [m.recipe_id for m in english]


@pytest.mark.usefixtures("recipes")
async def test_a_cached_query_vector_adds_the_vector_list(db, monkeypatch):
    # The query "christmas dessert" gets the stored vector of Jouluinen luumumousse, so the
    # nearest recipe is that one, found by meaning although no word matches.
    await db.execute(
        text(
            """
            INSERT INTO query_embeddings (query_text, model, embedding)
            SELECT 'christmas dessert', model, embedding FROM recipe_embeddings
            WHERE recipe_id = 40695
            """
        )
    )
    _vectors(monkeypatch, "cache")
    try:
        query = recipe_search.RecipeQuery("christmas dessert", (), None)
        [first, *rest] = await recipe_search.search(db, query, 5)
    finally:
        get_settings.cache_clear()

    [mousse] = [m for m in [first, *rest] if m.recipe_id == 40695]
    assert "vector:1" in mousse.matched_on
    assert any(m.matched_on == ("vector:2",) for m in rest)


# --- get_recipe -------------------------------------------------------------------------


@pytest.mark.usefixtures("recipes")
async def test_get_recipe_scales_and_links_products(db):
    recipe = await recipes.get_recipe(
        db, DEV_CALLER, GetRecipeRequest(recipe_id=BREAD, portions=60)
    )

    assert recipe.name == "Rukiinen piimäleipä" and recipe.portions == 60
    by_name = {i.name: i for i in recipe.ingredients}
    # 0.1666 kg of piimä per portion; 10 kg is ten 1 l cartons of the linked product.
    assert (by_name["Valio piimää"].quantity, by_name["Valio piimää"].unit) == (10, "kg")
    assert by_name["Valio piimää"].product_id == "463373"
    # 0.5 kg of butter: the 200 g case of 20 is the only linked pack in the test catalogue.
    assert by_name["Valio voita"].quantity == Decimal("0.5")
    assert by_name["Valio voita"].product_id == "463798"
    assert by_name["suolaa"].product_id is None
    assert [i.index for i in recipe.ingredients] == list(range(6))


@pytest.mark.usefixtures("recipes")
async def test_get_recipe_unknown_is_not_found(db):
    for recipe_id in ("1", "nope"):
        with pytest.raises(NotFoundError):
            await recipes.get_recipe(
                db, DEV_CALLER, GetRecipeRequest(recipe_id=recipe_id, portions=10)
            )


# --- Recipe lines in build_quote --------------------------------------------------------


@pytest.fixture
async def caller(db: AsyncSession) -> Caller:
    """A kitchen without exclusions: the dev caller's is lactose-free, and the bread's
    piimä is not."""
    account = await accounts.create_demo_account(db, new_number(), [], "fi")
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=[],
        lang="fi",
        channel="web",
    )


@pytest.fixture
def borrowed_offers(monkeypatch):
    """The linked products have no recorded offer: they borrow the recorded milk's."""
    real_offers = valio.get_offers

    async def get_offers(ids, needed_by):
        offers = {o.product_id: o for o in await real_offers(sorted({*ids, "464306"}), needed_by)}
        milk = offers["464306"]
        return [
            offers[i] if offers[i].ok else milk.model_copy(update={"product_id": i}) for i in ids
        ]

    monkeypatch.setattr(valio, "get_offers", get_offers)


def recipe_line(**changes) -> LineRequest:
    line = {
        "line_id": "r1",
        "quantity": 60,
        "unit": "piece",
        "needed_by": "2026-11-16",
        "recipe_ref": {"recipe_id": BREAD, "portions": 60},
        "group": "Rukiinen piimäleipä",
    }
    return LineRequest.model_validate({**line, **changes})


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_a_recipe_quote_orders_the_linked_ingredients_and_lists_the_rest(db, caller):
    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(lines=[recipe_line()]), now=T0
    )

    assert response.decision == Decision.ready, response.speak
    assert {(line.line_id, line.product_id) for line in response.lines} == {
        ("r1-0", "463373"),
        ("r1-3", "463798"),
    }
    assert {line.group for line in response.lines} == {"Rukiinen piimäleipä"}
    [group] = response.groups
    assert group.subtotal_cents == response.total_cents
    assert [(n.name, n.quantity, n.unit) for n in response.not_ordered] == [
        ("suolaa", Decimal("0.3"), "kg"),
        ("hiivaa", Decimal("0.6"), "kg"),
        ("ruisjauhoja", Decimal("5"), "kg"),
        ("vehnäjauhoja", Decimal("11"), "kg"),
    ]
    assert response.not_ordered[0].reason.en == "Not linked to a product, get it elsewhere"

    # The group shows the recipe's own image (#57), set by the quote service after the
    # engine, and kept in the stored output.
    assert group.image_url and group.image_url.startswith("https://")
    stored_image = await db.scalar(select(RecipeRow.image_url).where(RecipeRow.id == int(BREAD)))
    assert group.image_url == stored_image

    # The stored input replays to the same output, not_ordered included; the group image
    # is the service's, so the replay adds it the same way.
    quote = await quotes._load(db, caller, response.quote_id)
    assert quote.engine_output["groups"][0]["image_url"] == stored_image
    rules = await load_rule_set_by_ref(db, quote.rules_ref)
    replayed_input = EngineInput.model_validate({**quote.engine_input, "rules": rules})
    replayed = await quotes.with_group_images(
        db, engine.decide(replayed_input), replayed_input.lines, replayed_input.recipe_drafts
    )
    assert replayed.model_dump(mode="json") == quote.engine_output
    assert (await quotes.get_quote(db, caller, response.quote_id)).groups[0].image_url == (
        stored_image
    )

    # An edit sends the ingredient lines again (as the confirmation page does): the
    # not-ordered ingredients are still listed.
    edited = [
        LineRequest.model_validate(line)
        for line in quote.engine_input["lines"]
        if line["line_id"] == "r1-0"
    ]
    updated = await quotes.replace_quote(db, caller, response.quote_id, edited, now=T0)
    assert [line.line_id for line in updated.lines] == ["r1-0"]
    assert updated.not_ordered == response.not_ordered


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_one_ingredient_line_gets_its_product_or_is_not_ordered(db, caller):
    butter = recipe_line(
        line_id="b",
        quantity="0.5",
        unit="kg",
        recipe_ref={"recipe_id": BREAD, "portions": 60, "ingredient_index": 3},
    )
    salt = recipe_line(
        line_id="s",
        quantity="0.3",
        unit="kg",
        recipe_ref={"recipe_id": BREAD, "portions": 60, "ingredient_index": 1},
    )

    lines, not_ordered = await recipes.expand_lines(db, [butter, salt])

    assert [(line.line_id, line.product_id, line.quantity) for line in lines] == [
        ("b", "463798", Decimal("0.5"))
    ]
    assert [n.name for n in not_ordered] == ["suolaa", "hiivaa", "ruisjauhoja", "vehnäjauhoja"]


@pytest.mark.usefixtures("recipes")
async def test_an_ingredient_without_an_amount_is_not_ordered(db):
    lines, not_ordered = await recipes.expand_lines(
        db, [recipe_line(recipe_ref={"recipe_id": CHAI, "portions": 10})]
    )

    [cinnamon] = [n for n in not_ordered if n.name == "kanelia"]
    assert cinnamon.quantity is None
    assert len(lines) == 1  # only the coffee milk is linked


@pytest.mark.usefixtures("recipes")
async def test_a_recipe_without_any_linked_ingredient_is_an_error(db):
    # Recipe 44115 links only lactose-free whipping cream; leave the catalogue without it.
    await db.execute(text("DELETE FROM recipe_product_links WHERE recipe_product_id = 1499"))
    with pytest.raises(InvalidRequestError, match="nothing to order"):
        await recipes.expand_lines(
            db, [recipe_line(recipe_ref={"recipe_id": "44115", "portions": 12})]
        )


@pytest.mark.usefixtures("recipes")
async def test_a_bad_ingredient_index_is_an_error(db):
    with pytest.raises(InvalidRequestError):
        await recipes.expand_lines(
            db,
            [recipe_line(recipe_ref={"recipe_id": BREAD, "portions": 6, "ingredient_index": 99})],
        )


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_a_plain_group_has_no_image(db, caller):
    line = LineRequest.model_validate(
        {
            "line_id": "m1",
            "text": "maito",
            "quantity": 20,
            "unit": "l",
            "needed_by": "2026-11-16",
            "group": "Juhlat",
        }
    )
    response = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[line]), now=T0)
    [group] = response.groups
    assert group.group == "Juhlat" and group.image_url is None


# --- One-off exclusions on a quote (#102) -----------------------------------------------

MILK_PRODUCTS = {"463373", "463798", "464306"}  # the bread's piimä and butter, and a milk


async def stored_input(db: AsyncSession, caller: Caller, quote_id: str) -> dict:
    return (await quotes._load(db, caller, quote_id)).engine_input


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_a_one_off_exclusion_applies_to_every_ingredient_of_a_recipe(db, caller):
    response = await quotes.build_quote(
        db,
        caller,
        BuildQuoteRequest(lines=[recipe_line()], exclusions=[Exclusion.milk_free]),
        now=T0,
    )

    # Neither milk ingredient is quoted. The piimä gets a safe product from the category
    # map as a question; the butter has none here and is rejected with a next step.
    assert not {line.product_id for line in response.lines} & MILK_PRODUCTS
    assert response.clarification is not None and response.clarification.line_id == "r1-0"
    offered = [option.product_id for option in response.clarification.options]
    assert offered and not set(offered) & MILK_PRODUCTS
    [rejection] = response.rejections
    assert (rejection.line_id, rejection.reason_code) == ("r1-3", "ALLERGEN_CONFLICT")
    assert rejection.next_step.en

    # Stored with the quote, apart from the kitchen profile, which is not changed.
    stored = await stored_input(db, caller, response.quote_id)
    assert stored["order_exclusions"] == ["milk_free"]
    assert stored["kitchen"]["exclusions"] == ["milk_free"]
    profile = await db.scalar(
        select(KitchenProfileRow.exclusions).where(
            KitchenProfileRow.company_id == caller.company_id
        )
    )
    assert profile == []


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_a_one_off_exclusion_stays_through_updates_until_it_is_cleared(db, caller):
    first = await quotes.build_quote(
        db,
        caller,
        BuildQuoteRequest(lines=[recipe_line()], exclusions=[Exclusion.milk_free]),
        now=T0,
    )
    oat = first.clarification.options[0].product_id
    asked = next(
        line
        for line in (await stored_input(db, caller, first.quote_id))["lines"]
        if line["line_id"] == "r1-0"
    )
    milk = {"line_id": "m", "product_id": "464306", "quantity": 2, "unit": "l", "needed_by": DAY}

    # The clarification answered and a milk added, with no exclusions sent: still milk-free.
    second = await quotes.update_quote(
        db,
        caller,
        UpdateQuoteRequest(
            quote_id=first.quote_id,
            lines=[LineRequest.model_validate({**asked, "product_id": oat}), milk],
        ),
        now=T0,
    )
    assert (await stored_input(db, caller, second.quote_id))["order_exclusions"] == ["milk_free"]
    assert [line.product_id for line in second.lines] == [oat]
    assert "m" in {r.line_id for r in second.rejections} | {
        second.clarification.line_id if second.clarification else None
    }

    # An empty list clears it: the milk can be quoted now.
    third = await quotes.update_quote(
        db,
        caller,
        UpdateQuoteRequest(quote_id=second.quote_id, lines=[milk], exclusions=[]),
        now=T0,
    )
    assert "order_exclusions" not in await stored_input(db, caller, third.quote_id)
    assert "464306" in {line.product_id for line in third.lines}


@pytest.mark.usefixtures("recipes", "borrowed_offers")
async def test_a_quote_without_one_off_exclusions_is_stored_as_before(db, caller):
    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(lines=[recipe_line()]), now=T0
    )

    stored = await stored_input(db, caller, response.quote_id)
    assert "order_exclusions" not in stored and stored["kitchen"]["exclusions"] == []
    assert {line.product_id for line in response.lines} == {"463373", "463798"}
