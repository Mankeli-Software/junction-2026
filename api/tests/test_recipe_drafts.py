"""Recipe drafts (#80): propose, confirm and lines.

The `to_lines` tests need no database; the rest need DATABASE_URL.
"""

import random
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.deps import DEV_CALLER
from app.models import AuditEvent, RecipeDraftRow
from app.schemas import (
    BuildQuoteRequest,
    ConfirmRecipeRequest,
    DraftIngredient,
    Exclusion,
    GetRecipeRequest,
    Localized,
    ProposeRecipeRequest,
    RecipeDraft,
    RequestedUnit,
)
from app.services import accounts, dev_caller, recipe_drafts, recipes
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError
from tests.conftest import write_audit

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
DAY = date(2026, 11, 16)  # the snapshot's offers are recorded for this day


def ingredient(index: int, text: str, amount=None, unit=None, **extra) -> DraftIngredient:
    return DraftIngredient(
        index=index,
        text=text,
        amount=Decimal(str(amount)) if amount is not None else None,
        unit=unit,
        **extra,
    )


def draft(*ingredients: DraftIngredient, portions=4, servings=None, dish="Puuro") -> RecipeDraft:
    return RecipeDraft(
        draft_id="d1",
        status="confirmed",
        source="notebook",
        is_guess=False,
        dish=dish,
        portions=portions,
        servings_on_source=servings,
        ingredients=list(ingredients),
        scaled=recipe_drafts.scale(list(ingredients), portions, servings),
        matched_recipe=None,
        speak=Localized(fi="", en=""),
    )


# --- to_lines (no database) -------------------------------------------------------------


def test_lines_are_scaled_by_portions_over_servings():
    lines, _ = recipe_drafts.to_lines(
        draft(ingredient(0, "kermaa", 2, "dl"), portions=40, servings=4), DAY
    )
    (line,) = lines
    assert (line.quantity, line.unit) == (Decimal("2.000000"), RequestedUnit.l)


def test_lines_are_taken_as_read_without_servings():
    lines, _ = recipe_drafts.to_lines(draft(ingredient(0, "kermaa", 2, "dl"), portions=40), DAY)
    assert lines[0].quantity == Decimal("0.2")


@pytest.mark.parametrize(
    ("unit", "amount", "quantity", "to"),
    [
        ("l", 2, "2", RequestedUnit.l),
        ("dl", 3, "0.3", RequestedUnit.l),
        ("cl", 5, "0.05", RequestedUnit.l),
        ("ml", 250, "0.25", RequestedUnit.l),
        ("rkl", 2, "0.03", RequestedUnit.l),
        ("tl", 1, "0.005", RequestedUnit.l),
        ("RKL.", 1, "0.015", RequestedUnit.l),
        ("kg", "1.5", "1.5", RequestedUnit.kg),
        ("g", 400, "0.4", RequestedUnit.kg),
        ("kpl", 3, "3", RequestedUnit.piece),
        ("pcs", 3, "3", RequestedUnit.piece),
        (None, 3, "3", RequestedUnit.piece),
    ],
)
def test_kitchen_measures_become_litres_kilos_or_pieces(unit, amount, quantity, to):
    (line,), _ = recipe_drafts.to_lines(draft(ingredient(0, "x", amount, unit)), DAY)
    assert line.unit == to
    assert line.quantity == Decimal(quantity)
    assert line.package_word is None


@pytest.mark.parametrize(
    ("amount", "unit", "word"),
    [(1, "ripaus", "ripaus"), (None, None, "?"), (None, "loraus", "loraus")],
)
def test_an_unknown_measure_asks_back(amount, unit, word):
    (line,), _ = recipe_drafts.to_lines(draft(ingredient(0, "suolaa", amount, unit)), DAY)
    assert (line.unit, line.package_word) == (RequestedUnit.package, word)


def test_unticked_rows_are_not_ordered_and_lines_carry_the_group():
    lines, not_ordered = recipe_drafts.to_lines(
        draft(
            ingredient(0, "maitoa", 1, "l"),
            ingredient(3, "vettä", 2, "dl", order=False),
            dish="Riisipuuro",
        ),
        DAY,
    )
    assert [(line.line_id, line.group, line.text, line.needed_by) for line in lines] == [
        ("p0", "Riisipuuro", "maitoa", DAY)
    ]
    (item,) = not_ordered
    assert (item.name, item.quantity, item.unit) == ("vettä", Decimal("2"), "dl")
    assert item.reason.en == "Not ordered: you unticked it"


def test_a_linked_ingredient_orders_its_product():
    (line,), _ = recipe_drafts.to_lines(
        draft(ingredient(0, "maitoa", 2, "l", product_id="464306")), DAY
    )
    assert (line.product_id, line.text) == ("464306", "maitoa")


def test_water_is_found_by_word():
    assert recipe_drafts._is_water("kylmää vettä")
    assert recipe_drafts._is_water("Water")
    assert not recipe_drafts._is_water("vesimeloni")


def test_build_quote_needs_lines_or_a_draft():
    with pytest.raises(ValueError, match="recipe_draft_id"):
        BuildQuoteRequest()
    assert BuildQuoteRequest(recipe_draft_id="x").lines == []


def test_ingredient_indexes_must_be_unique():
    with pytest.raises(ValueError, match="index"):
        ProposeRecipeRequest(
            dish="x",
            portions=1,
            ingredients=[ingredient(0, "a"), ingredient(0, "b")],
            source="notebook",
        )


# --- Services (database) ----------------------------------------------------------------


@pytest.fixture
async def caller(db: AsyncSession) -> Caller:
    """The dev caller (lactose-free kitchen), with its rows."""
    await dev_caller.ensure_rows(db, DEV_CALLER)
    return DEV_CALLER


async def other_caller(db: AsyncSession, exclusions: list[Exclusion] = ()) -> Caller:
    account = await accounts.create_demo_account(
        db, f"+35840{random.randrange(10**6, 10**7)}", exclusions, "en"
    )
    return Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=list(exclusions),
        lang="en",
        channel="web",
    )


def porridge(**overrides) -> ProposeRecipeRequest:
    data = {
        "dish": "Riisipuuro",
        "portions": 40,
        "servings_on_source": 4,
        "ingredients": [
            ingredient(0, "maitoa", 2, "l"),
            ingredient(1, "puuroriisiä", 2, "dl", confidence="low", note="hard to read"),
            ingredient(2, "vettä", 3, "dl"),
            ingredient(3, "suolaa", 1, "tl"),
        ],
        "source": "notebook",
    }
    return ProposeRecipeRequest.model_validate(data | overrides)


async def events(db: AsyncSession, type: str) -> list[AuditEvent]:
    await write_audit(db)
    return list(
        await db.scalars(select(AuditEvent).where(AuditEvent.type == type).order_by(AuditEvent.seq))
    )


async def test_propose_stores_a_draft_with_water_unticked(db, caller):
    proposed = await recipe_drafts.propose(db, caller, porridge(), image_sha256="ab" * 32, now=T0)

    assert proposed.status == "draft" and not proposed.is_guess
    assert [i.order for i in proposed.ingredients] == [True, True, False, True]
    assert proposed.scaled[0].amount == Decimal("20.000")  # 2 l for 4, scaled to 40
    assert proposed.speak.en.startswith("I read 4 ingredients for Riisipuuro")
    row = await db.get_one(RecipeDraftRow, uuid.UUID(proposed.draft_id))
    assert (row.version, row.company_id, row.image_sha256) == (1, caller.company_id, "ab" * 32)
    (read,) = await events(db, "recipe_read")
    assert read.session_id == row.session_id
    assert read.payload["ingredients"] == ["maitoa", "puuroriisiä", "vettä", "suolaa"]
    assert read.payload["low_confidence"] == ["puuroriisiä"]
    assert read.payload["image_sha256"] == "ab" * 32


async def test_confirm_with_edits_bumps_the_version_and_hashes_the_edits(db, caller):
    plain = await recipe_drafts.propose(db, caller, porridge(), now=T0)
    edited = await recipe_drafts.propose(db, caller, porridge(), now=T0)
    plain = await recipe_drafts.confirm(db, caller, ConfirmRecipeRequest(draft_id=plain.draft_id))
    changed = [
        *edited.ingredients[:1],
        edited.ingredients[1].model_copy(update={"amount": Decimal("3")}),
        edited.ingredients[2].model_copy(update={"order": True}),
    ]
    confirmed = await recipe_drafts.confirm(
        db,
        caller,
        ConfirmRecipeRequest(draft_id=edited.draft_id, portions=20, ingredients=changed),
        now=T0,
    )

    assert confirmed.status == "confirmed"
    assert confirmed.portions == 20 and len(confirmed.ingredients) == 3
    rows = {
        r.id: r
        for r in await db.scalars(
            select(RecipeDraftRow).where(
                RecipeDraftRow.id.in_([uuid.UUID(plain.draft_id), uuid.UUID(edited.draft_id)])
            )
        )
    }
    plain_row, edited_row = rows[uuid.UUID(plain.draft_id)], rows[uuid.UUID(edited.draft_id)]
    assert (plain_row.version, edited_row.version) == (1, 2)
    assert edited_row.confirmed_hash == recipe_drafts.confirmed_hash(edited_row)
    assert len(edited_row.confirmed_hash) == 64
    assert edited_row.confirmed_at == T0
    confirmed_events = await events(db, "recipe_confirmed")
    payload = confirmed_events[-1].payload
    assert payload["confirmed_hash"] == edited_row.confirmed_hash
    assert payload["portions_changed"] is True
    assert payload["edited"] == ["puuroriisiä"]
    assert payload["removed"] == ["suolaa"]
    assert payload["ticked"] == ["vettä"]
    assert payload["change_count"] == 4
    assert confirmed_events[-1].text_en == "The buyer confirmed the recipe, 4 changes"


async def test_confirming_twice_is_idempotent_and_then_frozen(db, caller):
    proposed = await recipe_drafts.propose(db, caller, porridge(), now=T0)
    request = ConfirmRecipeRequest(draft_id=proposed.draft_id, portions=10)

    first = await recipe_drafts.confirm(db, caller, request)
    again = await recipe_drafts.confirm(db, caller, request)
    bare = await recipe_drafts.confirm(db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id))

    assert first == again == bare
    assert len(await events(db, "recipe_confirmed")) == 1
    with pytest.raises(StateError, match="copy it as a new draft"):
        await recipe_drafts.confirm(
            db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id, portions=12)
        )


async def test_copy_as_new_makes_an_editable_draft(db, caller):
    proposed = await recipe_drafts.propose(db, caller, porridge(), now=T0)
    await recipe_drafts.confirm(db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id))

    copy = await recipe_drafts.copy_as_new(db, caller, proposed.draft_id)

    assert copy.draft_id != proposed.draft_id
    assert copy.status == "draft"
    assert copy.ingredients == proposed.ingredients
    row = await db.get_one(RecipeDraftRow, uuid.UUID(copy.draft_id))
    assert str(row.copied_from_id) == proposed.draft_id
    assert (await events(db, "recipe_read"))[-1].payload["copied_from"] == proposed.draft_id


async def test_a_discarded_draft_cant_be_confirmed(db, caller):
    proposed = await recipe_drafts.propose(db, caller, porridge(), now=T0)

    discarded = await recipe_drafts.discard(db, caller, proposed.draft_id)

    assert discarded.status == "discarded"
    assert len(await events(db, "recipe_discarded")) == 1
    with pytest.raises(StateError, match="discarded"):
        await recipe_drafts.confirm(db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id))


async def test_another_companys_draft_is_not_found(db, caller):
    proposed = await recipe_drafts.propose(db, caller, porridge(), now=T0)
    stranger = await other_caller(db)

    for call in (
        recipe_drafts.get(db, stranger, proposed.draft_id),
        recipe_drafts.discard(db, stranger, proposed.draft_id),
        recipe_drafts.confirm(db, stranger, ConfirmRecipeRequest(draft_id=proposed.draft_id)),
        recipe_drafts.get(db, caller, "nope"),
    ):
        with pytest.raises(NotFoundError):
            await call


@pytest.mark.usefixtures("recipes")
async def test_a_dish_photo_starts_from_our_matching_recipe(db, caller):
    seen = [ingredient(0, "lohta", 400, "g"), ingredient(1, "perunoita", 6, "kpl")]
    request = porridge(
        dish="Lohikeitto", source="dish_photo", servings_on_source=None, ingredients=seen
    )

    proposed = await recipe_drafts.propose(db, caller, request, now=T0)

    assert proposed.is_guess
    hit = proposed.matched_recipe
    assert hit is not None and "lohikeitto" in hit.name.lower()
    assert proposed.servings_on_source == hit.default_portions
    recipe = await recipes.get_recipe(
        db, caller, GetRecipeRequest(recipe_id=hit.recipe_id, portions=hit.default_portions)
    )
    assert [(i.text, i.product_id) for i in proposed.ingredients] == [
        (i.name, i.product_id) for i in recipe.ingredients
    ]
    assert proposed.ai_reading == seen
    assert proposed.speak.en.startswith("This is a guess from the picture")

    confirmed = await recipe_drafts.confirm(
        db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id, use_ai_reading=True)
    )
    assert confirmed.ingredients == seen
    assert confirmed.matched_recipe is None and confirmed.servings_on_source is None


@pytest.mark.usefixtures("recipes")
async def test_a_dish_photo_without_a_match_is_the_ai_guess(db, caller):
    request = porridge(dish="Zzyzx", source="dish_photo")
    proposed = await recipe_drafts.propose(db, caller, request, now=T0)
    assert proposed.matched_recipe is None and proposed.ai_reading is None
    assert proposed.speak.en.startswith("This is a guess from the picture: Zzyzx")


async def test_editing_a_linked_rows_text_drops_its_product(db, caller):
    linked = ingredient(0, "maitoa", 2, "l", product_id="464306")
    proposed = await recipe_drafts.propose(
        db, caller, porridge(ingredients=[linked, ingredient(1, "kermaa", 1, "dl")]), now=T0
    )
    kept, renamed = (
        proposed.ingredients[0],
        proposed.ingredients[0].model_copy(update={"text": "kauramaitoa"}),
    )
    assert kept.product_id == "464306"

    confirmed = await recipe_drafts.confirm(
        db,
        caller,
        ConfirmRecipeRequest(
            draft_id=proposed.draft_id, ingredients=[renamed, proposed.ingredients[1]]
        ),
    )
    assert confirmed.ingredients[0].product_id is None
