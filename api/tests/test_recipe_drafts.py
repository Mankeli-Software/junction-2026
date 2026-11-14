"""Recipe drafts (#80): propose, confirm, lines, quotes from a confirmed draft, and the
tools and routes.

The `to_lines` tests need no database; the rest need DATABASE_URL.
"""

import random
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import engine
from app.interfaces.deps import DEV_CALLER
from app.interfaces.mcp.server import mcp
from app.main import app
from app.models import AuditEvent, Quote, RecipeDraftRow
from app.schemas import (
    BuildQuoteRequest,
    ConfirmRecipeRequest,
    Decision,
    DraftIngredient,
    EngineInput,
    Exclusion,
    GetRecipeRequest,
    LineRequest,
    Localized,
    ProposeRecipeRequest,
    RecipeDraft,
    RequestedUnit,
    UpdateQuoteRequest,
)
from app.services import accounts, dev_caller, quotes, recipe_drafts, recipes, signing
from app.services.audit import load_rule_set_by_ref
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError
from app.services.policy import get_rule_set
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


def test_the_next_weekday_skips_the_weekend():
    rules = get_rule_set()  # business time is Thursday 2026-11-12
    assert quotes.next_weekday(rules) == date(2026, 11, 13)
    friday = rules.model_copy(
        update={
            "policy": rules.policy.model_copy(
                update={"business_time": datetime(2026, 11, 13, 9, tzinfo=UTC)}
            )
        }
    )
    assert quotes.next_weekday(friday) == date(2026, 11, 16)


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


# --- Quotes from a draft ----------------------------------------------------------------


def milk_recipe(**overrides) -> ProposeRecipeRequest:
    data = {
        "dish": "Maitokahvi",
        "portions": 40,
        "servings_on_source": 4,
        "ingredients": [ingredient(0, "maito", 2, "l"), ingredient(1, "vettä", 1, "l")],
        "source": "notebook",
    }
    return ProposeRecipeRequest.model_validate(data | overrides)


async def confirmed_draft(db, caller, request=None, **edits) -> RecipeDraft:
    proposed = await recipe_drafts.propose(db, caller, request or milk_recipe(), now=T0)
    return await recipe_drafts.confirm(
        db, caller, ConfirmRecipeRequest(draft_id=proposed.draft_id, **edits)
    )


async def test_an_unconfirmed_draft_cant_be_quoted(db, caller):
    proposed = await recipe_drafts.propose(db, caller, milk_recipe(), now=T0)
    with pytest.raises(StateError, match="confirm the recipe with the buyer first"):
        await quotes.build_quote(
            db, caller, BuildQuoteRequest(recipe_draft_id=proposed.draft_id, needed_by=DAY), now=T0
        )


async def test_a_confirmed_draft_is_quoted_scaled_labelled_and_replays(db, caller):
    confirmed = await confirmed_draft(db, caller)

    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(recipe_draft_id=confirmed.draft_id, needed_by=DAY), now=T0
    )

    assert response.decision == Decision.ready
    (line,) = response.lines
    assert (line.line_id, line.group, line.product_id) == ("p0", "Maitokahvi", "464306")
    assert line.asked.quantity == Decimal("20")  # 2 l for 4, for 40
    (group,) = response.groups
    assert (group.source, group.recipe_draft_id) == ("photo", confirmed.draft_id)
    assert [(n.name, n.reason.en) for n in response.not_ordered] == [
        ("vettä", "Not ordered: you unticked it")
    ]

    quote = await db.get_one(Quote, uuid.UUID(response.quote_id))
    row = await db.get_one(RecipeDraftRow, uuid.UUID(confirmed.draft_id))
    (ref,) = quote.engine_input["recipe_drafts"]
    assert (ref["draft_id"], ref["confirmed_hash"]) == (confirmed.draft_id, row.confirmed_hash)

    # Replay: the stored input gives the same output and the same quote hash.
    rules = await load_rule_set_by_ref(db, quote.rules_ref)
    replayed_input = EngineInput.model_validate({**quote.engine_input, "rules": rules})
    replayed = quotes.with_recipe_drafts(
        engine.decide(replayed_input), replayed_input.recipe_drafts
    )
    assert replayed.model_dump(mode="json") == quote.engine_output
    payload = quotes.quote_payload(
        quote.id,
        quote.version,
        quote.company_id,
        replayed,
        replayed_input.offers,
        issued_at=replayed_input.issued_at,
        expires_at=quote.expires_at,
        recipe_drafts=replayed_input.recipe_drafts,
    )
    assert payload["recipe_drafts"] == [
        {"draft_id": confirmed.draft_id, "confirmed_hash": row.confirmed_hash}
    ]
    assert signing.quote_hash(payload) == quote.quote_hash


async def test_edited_amounts_are_quoted(db, caller):
    proposed = await recipe_drafts.propose(db, caller, milk_recipe(), now=T0)
    edited = [proposed.ingredients[0].model_copy(update={"amount": Decimal("3")})]
    await recipe_drafts.confirm(
        db,
        caller,
        ConfirmRecipeRequest(draft_id=proposed.draft_id, portions=8, ingredients=edited),
    )

    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(recipe_draft_id=proposed.draft_id, needed_by=DAY), now=T0
    )

    assert response.lines[0].asked.quantity == Decimal("6")  # 3 l for 4, for 8
    assert response.not_ordered == []


async def test_other_lines_come_first_and_set_the_date(db, caller):
    confirmed = await confirmed_draft(db, caller)
    butter = LineRequest(line_id="l1", text="maito", quantity=Decimal(1), unit="l", needed_by=DAY)

    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(lines=[butter], recipe_draft_id=confirmed.draft_id), now=T0
    )

    assert [line.line_id for line in response.lines] == ["l1", "p0"]
    assert {line.asked.needed_by for line in response.lines} == {DAY}
    clash = butter.model_copy(update={"line_id": "p0"})
    with pytest.raises(StateError, match="p0"):
        await quotes.build_quote(
            db, caller, BuildQuoteRequest(lines=[clash], recipe_draft_id=confirmed.draft_id)
        )


async def test_an_unknown_measure_is_asked_back_by_the_engine(db, caller):
    request = milk_recipe(ingredients=[ingredient(0, "maito", 1, "ripaus")])
    confirmed = await confirmed_draft(db, caller, request)

    response = await quotes.build_quote(
        db, caller, BuildQuoteRequest(recipe_draft_id=confirmed.draft_id, needed_by=DAY), now=T0
    )

    assert response.decision == Decision.needs_clarification
    assert response.clarification is not None and response.clarification.line_id == "p0"


async def test_a_milk_free_kitchen_still_blocks_milk_from_a_photo(db):
    milk_free = await other_caller(db, [Exclusion.milk_free])
    confirmed = await confirmed_draft(db, milk_free)

    response = await quotes.build_quote(
        db, milk_free, BuildQuoteRequest(recipe_draft_id=confirmed.draft_id, needed_by=DAY), now=T0
    )

    # As for a milk line typed by an agent: no milk is priced; the oat drink has no offer
    # here, so the line ends in a callback request (see test_quotes).
    assert response.decision == Decision.rejected
    assert all(line.product_id != "464306" for line in response.lines)
    (rejection,) = response.rejections
    assert (rejection.line_id, rejection.reason_code) == ("p0", "CALLBACK_REQUESTED")


async def test_update_quote_keeps_the_photo_label(db, caller):
    confirmed = await confirmed_draft(db, caller)
    first = await quotes.build_quote(
        db, caller, BuildQuoteRequest(recipe_draft_id=confirmed.draft_id, needed_by=DAY), now=T0
    )
    quote = await db.get_one(Quote, uuid.UUID(first.quote_id))
    lines = [LineRequest.model_validate(raw) for raw in quote.engine_input["lines"]]

    second = await quotes.update_quote(
        db,
        caller,
        UpdateQuoteRequest(
            quote_id=first.quote_id, lines=[lines[0].model_copy(update={"quantity": Decimal(30)})]
        ),
        now=T0,
    )
    assert second.groups[0].source == "photo"
    assert second.groups[0].recipe_draft_id == confirmed.draft_id
    assert [n.name for n in second.not_ordered] == ["vettä"]

    regrouped = [lines[0].model_copy(update={"group": None})]
    third = await quotes.update_quote(
        db, caller, UpdateQuoteRequest(quote_id=second.quote_id, lines=regrouped), now=T0
    )
    assert third.groups == [] and third.not_ordered == []
    assert "recipe_drafts" not in (await db.get_one(Quote, uuid.UUID(third.quote_id))).engine_input


async def test_a_quote_without_a_draft_stores_no_draft_reference(db, caller):
    line = LineRequest(line_id="l1", text="maito", quantity=Decimal(20), unit="l", needed_by=DAY)
    response = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[line]), now=T0)
    quote = await db.get_one(Quote, uuid.UUID(response.quote_id))
    assert "recipe_drafts" not in quote.engine_input
    assert all(g.source is None for g in response.groups)


# --- Tools and routes -------------------------------------------------------------------

PROPOSAL = {
    "dish": "Maitokahvi",
    "portions": 40,
    "servings_on_source": 4,
    "ingredients": [
        {"index": 0, "text": "maito", "amount": 2, "unit": "l"},
        {"index": 1, "text": "vettä", "amount": 1, "unit": "l"},
    ],
    "source": "notebook",
}


@pytest.mark.usefixtures("dev_caller")
async def test_propose_and_confirm_over_mcp_then_quote(app_db: AsyncEngine):
    async with create_connected_server_and_client_session(mcp) as client:
        proposed = await client.call_tool("propose_recipe", PROPOSAL)
        draft_id = proposed.structuredContent["draft_id"]
        early = await client.call_tool(
            "build_quote", {"recipe_draft_id": draft_id, "needed_by": DAY.isoformat()}
        )
        confirmed = await client.call_tool("confirm_recipe", {"draft_id": draft_id})
        quote = await client.call_tool(
            "build_quote", {"recipe_draft_id": draft_id, "needed_by": DAY.isoformat()}
        )

    assert not proposed.isError, proposed.content
    assert proposed.structuredContent["ingredients"][1]["order"] is False
    assert early.isError and "confirm the recipe" in early.content[0].text
    assert confirmed.structuredContent["status"] == "confirmed"
    assert quote.structuredContent["groups"][0]["source"] == "photo"
    async with AsyncSession(app_db) as db:
        row = await db.get_one(RecipeDraftRow, uuid.UUID(draft_id))
        types = list(
            await db.scalars(
                select(AuditEvent.type)
                .where(AuditEvent.session_id == row.session_id)
                .order_by(AuditEvent.seq)
            )
        )
    assert types[:4] == ["session_started", "tool_called", "recipe_read", "tool_returned"]
    assert "recipe_confirmed" in types


@pytest.mark.usefixtures("app_db", "dev_caller")
def test_recipe_draft_routes():
    client = TestClient(app)

    proposed = client.post("/api/v1/recipe-drafts", json=PROPOSAL)
    assert proposed.status_code == 200, proposed.text
    draft_id = proposed.json()["draft_id"]
    assert client.get(f"/api/v1/recipe-drafts/{draft_id}").json() == proposed.json()

    edited = [PROPOSAL["ingredients"][0] | {"amount": 3}]
    confirmed = client.post(
        f"/api/v1/recipe-drafts/{draft_id}/confirm", json={"portions": 8, "ingredients": edited}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["scaled"][0]["amount"] == 6
    assert client.post(f"/api/v1/recipe-drafts/{draft_id}/confirm").status_code == 200
    assert client.post(f"/api/v1/recipe-drafts/{draft_id}/discard").status_code == 409

    quote = client.post(
        "/api/v1/quotes", json={"recipe_draft_id": draft_id, "needed_by": DAY.isoformat()}
    )
    assert quote.status_code == 200, quote.text
    assert quote.json()["groups"][0]["recipe_draft_id"] == draft_id

    copy = client.post(f"/api/v1/recipe-drafts/{draft_id}/copy").json()
    assert copy["status"] == "draft" and copy["draft_id"] != draft_id
    discarded = client.post(f"/api/v1/recipe-drafts/{copy['draft_id']}/discard").json()
    assert discarded["status"] == "discarded"
    assert client.get("/api/v1/recipe-drafts/nope").status_code == 404
    assert client.post("/api/v1/quotes", json={}).status_code == 422
