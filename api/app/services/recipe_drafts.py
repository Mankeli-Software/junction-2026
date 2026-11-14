"""Recipe drafts (#80, docs/plans/80-recipe-photo.md §5): a recipe read from a photo, which
the buyer checks, edits and confirms before it becomes order lines.

- `propose` stores a draft from the webshop's photo reading or a connector's
  `propose_recipe`. A dish photo whose name matches one of our recipes starts from that
  recipe, with what the AI saw kept beside it. Water starts unticked.
- `confirm` applies the buyer's corrections and freezes the draft, with `confirmed_hash`
  over exactly what was confirmed. `copy_as_new` is "Edit as new draft".
- `to_lines` turns a confirmed draft into `LineRequest`s for `quotes.build_quote`: ticked
  ingredients become lines, unticked ones `NotOrdered`.

Every function takes the request's `AsyncSession` and only flushes; the caller commits.
"""

import hashlib
import re
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import rfc8785
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderSession, RecipeDraftRow
from app.schemas import (
    ConfirmRecipeRequest,
    DraftIngredient,
    GetRecipeRequest,
    LineRequest,
    Localized,
    NotOrdered,
    ProposeRecipeRequest,
    RecipeDraft,
    RecipeDraftRef,
    RequestedUnit,
    SearchRecipesRequest,
)
from app.schemas.engine import MAX_LINES, MAX_QUANTITY
from app.search.text import fold
from app.services import audit, recipes, sessions
from app.services.caller import Caller
from app.services.errors import NotFoundError, StateError

# Kitchen measures as read, to the unit the engine takes and how many of it one is.
# Volume goes to litres and weight to kilos; the engine converts litres to kilos for a
# product sold by weight once it has a density for the words (plan §5.1).
UNITS: dict[str, tuple[RequestedUnit, Decimal]] = {
    "l": (RequestedUnit.l, Decimal(1)),
    "ltr": (RequestedUnit.l, Decimal(1)),
    "litra": (RequestedUnit.l, Decimal(1)),
    "litraa": (RequestedUnit.l, Decimal(1)),
    "dl": (RequestedUnit.l, Decimal("0.1")),
    "cl": (RequestedUnit.l, Decimal("0.01")),
    "ml": (RequestedUnit.l, Decimal("0.001")),
    "rkl": (RequestedUnit.l, Decimal("0.015")),  # ruokalusikka, 15 ml
    "tbsp": (RequestedUnit.l, Decimal("0.015")),
    "tl": (RequestedUnit.l, Decimal("0.005")),  # teelusikka, 5 ml
    "tsp": (RequestedUnit.l, Decimal("0.005")),
    "kg": (RequestedUnit.kg, Decimal(1)),
    "g": (RequestedUnit.kg, Decimal("0.001")),
    "kpl": (RequestedUnit.piece, Decimal(1)),
    "pcs": (RequestedUnit.piece, Decimal(1)),
    "pc": (RequestedUnit.piece, Decimal(1)),
}

# Water starts unticked on the card (decision 9): one of these words in the ingredient.
WATER_WORDS = {"vesi", "vettä", "vedellä", "veteen", "water"}

# Amounts on the card, like `get_recipe`.
AMOUNT_STEP = Decimal("0.001")
# Line quantities: exact for every kitchen measure of an amount on the card.
QUANTITY_STEP = Decimal("0.000001")

# Line ids of a draft's ingredients, "p" for photo.
LINE_PREFIX = "p"
# `LineRequest.group` is at most this long.
MAX_GROUP = 80

UNTICKED = Localized(fi="Ei tilattu: poistit valinnan", en="Not ordered: you unticked it")
TOO_MUCH = Localized(fi="Ei tilattu: määrä on liian suuri", en="Not ordered: the amount is too big")
# The package word for an ingredient read without an amount or unit: the engine asks back.
UNKNOWN_MEASURE = "?"


# --- Services ---------------------------------------------------------------------------


async def propose(
    db: AsyncSession,
    caller: Caller,
    request: ProposeRecipeRequest,
    *,
    image_sha256: str | None = None,
    now: datetime | None = None,
) -> RecipeDraft:
    """Store a new draft in the caller's current session and write `recipe_read`."""
    now = now or datetime.now(UTC)
    session = await sessions.current_session(db, caller, now=now)
    read = [_with_water_unticked(i) for i in request.ingredients]
    ingredients, servings = read, request.servings_on_source
    ai_reading = matched_id = None
    if request.source == "dish_photo":
        match = await _matched_recipe(db, caller, request.dish)
        if match is not None:
            matched_id, ingredients, servings = match
            ai_reading = {
                "servings_on_source": request.servings_on_source,
                "ingredients": _dump(read),
            }
    row = RecipeDraftRow(
        id=uuid.uuid4(),
        session_id=session.id,
        company_id=caller.company_id,
        user_id=caller.user_id,
        source=request.source,
        status="draft",
        dish=request.dish,
        portions=request.portions,
        servings_on_source=servings,
        ingredients=_dump(ingredients),
        ai_reading=ai_reading,
        matched_recipe_id=matched_id,
        image_sha256=image_sha256,
        version=1,
    )
    db.add(row)
    await db.flush()
    await _record_read(db, row, read, copied_from=None)
    return await _response(db, row)


async def confirm(
    db: AsyncSession, caller: Caller, request: ConfirmRecipeRequest, *, now: datetime | None = None
) -> RecipeDraft:
    """Apply the buyer's corrections, mark the draft confirmed and write `recipe_confirmed`.

    Confirming again without changes returns the confirmed draft; a confirmed draft can't be
    changed (copy it as a new draft) and a discarded one can't be confirmed.
    """
    now = now or datetime.now(UTC)
    row = await _load(db, caller, request.draft_id, for_update=True)
    before = _content(row)
    after = _edited(row, request)
    if row.status == "confirmed":
        if after != before:
            raise StateError(
                "the recipe is already confirmed and can't be changed; "
                "copy it as a new draft to edit it"
            )
        return await _response(db, row)
    if row.status == "discarded":
        raise StateError("the recipe draft was discarded; propose the recipe again")

    changes = _changes(before, after, used_ai_reading=request.use_ai_reading)
    if after != before:
        row.portions = after["portions"]
        row.servings_on_source = after["servings_on_source"]
        row.ingredients = after["ingredients"]
        row.matched_recipe_id = after["matched_recipe_id"]
        row.version += 1
    row.status = "confirmed"
    row.confirmed_at = now
    row.confirmed_hash = confirmed_hash(row)
    await db.flush()
    await _touch(db, row, now)
    count = changes["change_count"]
    await _record(
        db,
        "recipe_confirmed",
        row,
        {
            "draft_id": str(row.id),
            "version": row.version,
            "confirmed_hash": row.confirmed_hash,
            "dish": row.dish,
            "portions": row.portions,
            **changes,
        },
        Localized(
            fi=f"Ostaja vahvisti reseptin, {count} {'muutos' if count == 1 else 'muutosta'}",
            en=f"The buyer confirmed the recipe, {count} {'change' if count == 1 else 'changes'}",
        ),
    )
    return await _response(db, row)


async def get(db: AsyncSession, caller: Caller, draft_id: str) -> RecipeDraft:
    return await _response(db, await _load(db, caller, draft_id))


async def discard(
    db: AsyncSession, caller: Caller, draft_id: str, *, now: datetime | None = None
) -> RecipeDraft:
    """The card's "Start over". A confirmed draft can't be discarded; discarding twice is
    a no-op."""
    now = now or datetime.now(UTC)
    row = await _load(db, caller, draft_id, for_update=True)
    if row.status == "discarded":
        return await _response(db, row)
    if row.status == "confirmed":
        raise StateError("the recipe is already confirmed; copy it as a new draft instead")
    row.status = "discarded"
    await db.flush()
    await _touch(db, row, now)
    await _record(
        db,
        "recipe_discarded",
        row,
        {"draft_id": str(row.id), "version": row.version, "dish": row.dish},
        Localized(fi="Reseptiluonnos hylättiin", en="The recipe draft was discarded"),
    )
    return await _response(db, row)


async def copy_as_new(
    db: AsyncSession, caller: Caller, draft_id: str, *, now: datetime | None = None
) -> RecipeDraft:
    """The card's "Edit as new draft": a new draft with the same content, in the current
    session, to edit and confirm again. Writes `recipe_read` with `copied_from`."""
    now = now or datetime.now(UTC)
    source = await _load(db, caller, draft_id)
    session = await sessions.current_session(db, caller, now=now)
    row = RecipeDraftRow(
        id=uuid.uuid4(),
        session_id=session.id,
        company_id=caller.company_id,
        user_id=caller.user_id,
        source=source.source,
        status="draft",
        dish=source.dish,
        portions=source.portions,
        servings_on_source=source.servings_on_source,
        ingredients=source.ingredients,
        ai_reading=source.ai_reading,
        matched_recipe_id=source.matched_recipe_id,
        image_sha256=source.image_sha256,
        copied_from_id=source.id,
        version=1,
    )
    db.add(row)
    await db.flush()
    await _record_read(db, row, _ingredients(row.ingredients), copied_from=source.id)
    return await _response(db, row)


async def quote_lines(
    db: AsyncSession,
    caller: Caller,
    draft_id: str,
    other_lines: list[LineRequest],
    needed_by: date,
) -> tuple[list[LineRequest], RecipeDraftRef]:
    """The lines of a quote with a confirmed draft: the other lines, then the draft's.

    Raises `StateError` for a draft the buyer hasn't confirmed, and `NotFoundError` for
    another company's draft.
    """
    row = await _load(db, caller, draft_id)
    if row.status != "confirmed" or row.confirmed_hash is None:
        raise StateError(
            "the recipe draft is not confirmed; confirm the recipe with the buyer first"
        )
    draft = await _response(db, row)
    lines, not_ordered = to_lines(draft, needed_by)
    taken = {line.line_id for line in other_lines} & {line.line_id for line in lines}
    if taken:
        raise StateError(
            f"line ids {', '.join(sorted(taken))} are used by the recipe draft; "
            f"use ids that don't start with {LINE_PREFIX}"
        )
    combined = [*other_lines, *lines]
    if len(combined) > MAX_LINES:
        raise StateError(f"a quote can have at most {MAX_LINES} lines")
    if not combined:
        raise StateError("nothing to order: every ingredient of the recipe is unticked")
    ref = RecipeDraftRef(
        draft_id=draft.draft_id,
        confirmed_hash=row.confirmed_hash,
        group=group_name(draft.dish),
        not_ordered=not_ordered,
    )
    return combined, ref


# --- Lines ------------------------------------------------------------------------------


def to_lines(draft: RecipeDraft, needed_by: date) -> tuple[list[LineRequest], list[NotOrdered]]:
    """One line per ticked ingredient, scaled to the draft's portions; unticked ones (and an
    amount too big to order) become `NotOrdered`.

    Kitchen measures become litres, kilos or pieces. Anything else ("ripaus", or no amount
    at all) is sent as a `package` with the measure as the word, so the engine asks the
    buyer back instead of guessing (vision §6).
    """
    lines: list[LineRequest] = []
    not_ordered: list[NotOrdered] = []
    group = group_name(draft.dish)
    for ingredient in draft.scaled:
        if not ingredient.order:
            not_ordered.append(_not_ordered(ingredient, UNTICKED))
            continue
        quantity, unit, package_word = _measure(ingredient)
        if quantity > MAX_QUANTITY:
            not_ordered.append(_not_ordered(ingredient, TOO_MUCH))
            continue
        lines.append(
            LineRequest(
                line_id=f"{LINE_PREFIX}{ingredient.index}",
                product_id=ingredient.product_id,
                text=ingredient.text,
                quantity=quantity,
                unit=unit,
                package_word=package_word,
                needed_by=needed_by,
                group=group,
            )
        )
    return lines, not_ordered


def scale(
    ingredients: list[DraftIngredient], portions: int, servings: int | None
) -> list[DraftIngredient]:
    """Amounts for `portions` when the recipe says how many servings it makes, else as read."""
    if servings is None:
        return list(ingredients)
    factor = Decimal(portions) / Decimal(servings)
    return [
        i.model_copy(update={"amount": _amount(i.amount * factor)}) if i.amount else i
        for i in ingredients
    ]


def group_name(dish: str) -> str:
    return dish.strip()[:MAX_GROUP]


def confirmed_hash(row: RecipeDraftRow) -> str:
    """SHA-256 over the RFC 8785 canonical JSON of what the buyer confirmed."""
    content = {"draft_id": str(row.id), "source": row.source, "dish": row.dish, **_content(row)}
    content["ingredients"] = [
        {**i, "amount": _exact(None if i.get("amount") is None else Decimal(str(i["amount"])))}
        for i in content["ingredients"]
    ]
    return hashlib.sha256(rfc8785.dumps(content)).hexdigest()


def _measure(ingredient: DraftIngredient) -> tuple[Decimal, RequestedUnit, str | None]:
    unit = _unit_key(ingredient.unit)
    if ingredient.amount is None:
        return Decimal(1), RequestedUnit.package, (ingredient.unit or "").strip() or UNKNOWN_MEASURE
    if unit is None:
        return ingredient.amount, RequestedUnit.piece, None
    if unit in UNITS:
        to, factor = UNITS[unit]
        quantity = (ingredient.amount * factor).quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)
        return max(quantity, QUANTITY_STEP), to, None
    return ingredient.amount, RequestedUnit.package, (ingredient.unit or "").strip()


def _unit_key(unit: str | None) -> str | None:
    if unit is None or not unit.strip():
        return None
    return unit.strip().casefold().rstrip(".")


def _not_ordered(ingredient: DraftIngredient, reason: Localized) -> NotOrdered:
    return NotOrdered(
        name=ingredient.text, quantity=ingredient.amount, unit=ingredient.unit, reason=reason
    )


def _amount(value: Decimal) -> Decimal:
    return max(value.quantize(AMOUNT_STEP, rounding=ROUND_HALF_UP), AMOUNT_STEP)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(text)) if len(w) > 2}


def _is_water(text: str) -> bool:
    return bool(set(re.findall(r"\w+", text.casefold())) & WATER_WORDS)


def _with_water_unticked(ingredient: DraftIngredient) -> DraftIngredient:
    return (
        ingredient.model_copy(update={"order": False}) if _is_water(ingredient.text) else ingredient
    )


async def _matched_recipe(
    db: AsyncSession, caller: Caller, dish: str
) -> tuple[str, list[DraftIngredient], int] | None:
    """Our recipe for a dish photo, as draft ingredients for its default portions. An
    ingredient linked to a product keeps its product id (decision 17).

    The best search hit counts only when its name shares a word with the dish, so a
    search by meaning never passes off an unrelated recipe as the dish.
    """
    hits = (
        await recipes.search_recipes(db, caller, SearchRecipesRequest(q=dish.strip(), limit=1))
    ).results
    if not hits or not _words(hits[0].name) & _words(dish):
        return None
    hit = hits[0]
    recipe = await recipes.get_recipe(
        db, caller, GetRecipeRequest(recipe_id=hit.recipe_id, portions=hit.default_portions)
    )
    ingredients = [
        _with_water_unticked(
            DraftIngredient(
                index=i.index,
                text=i.name[:200],
                amount=i.quantity if i.quantity else None,
                unit=i.unit,
                product_id=i.product_id,
            )
        )
        for i in recipe.ingredients
    ]
    return hit.recipe_id, ingredients, hit.default_portions


# --- Editing ----------------------------------------------------------------------------


def _content(row: RecipeDraftRow) -> dict[str, Any]:
    return {
        "portions": row.portions,
        "servings_on_source": row.servings_on_source,
        "ingredients": row.ingredients,
        "matched_recipe_id": row.matched_recipe_id,
    }


def _edited(row: RecipeDraftRow, request: ConfirmRecipeRequest) -> dict[str, Any]:
    """The draft's content after the request's corrections."""
    content = _content(row)
    if request.use_ai_reading:
        if row.ai_reading is None:
            raise StateError("this draft has no separate AI reading to use")
        content["ingredients"] = row.ai_reading["ingredients"]
        content["servings_on_source"] = row.ai_reading["servings_on_source"]
        content["matched_recipe_id"] = None
    if request.portions is not None:
        content["portions"] = request.portions
    if request.ingredients is not None:
        # A product link stays only on a row whose text the buyer left as it was.
        old = {i["index"]: i["text"] for i in content["ingredients"]}
        content["ingredients"] = _dump(
            [
                i.model_copy(update={"product_id": None})
                if i.product_id is not None and old.get(i.index) != i.text
                else i
                for i in request.ingredients
            ]
        )
    return content


def _changes(
    before: dict[str, Any], after: dict[str, Any], *, used_ai_reading: bool
) -> dict[str, Any]:
    """What the buyer changed, for `recipe_confirmed`. Ingredient texts are data."""
    old = {i["index"]: i for i in before["ingredients"]}
    new = {i["index"]: i for i in after["ingredients"]}
    fields = ("text", "amount", "unit")
    changes = {
        "portions_changed": before["portions"] != after["portions"],
        "used_ai_reading": used_ai_reading,
        "added": [new[i]["text"] for i in new if i not in old],
        "removed": [old[i]["text"] for i in old if i not in new],
        "edited": [
            new[i]["text"]
            for i in new
            if i in old and any(old[i].get(f) != new[i].get(f) for f in fields)
        ],
        "unticked": [
            new[i]["text"] for i in new if i in old and old[i]["order"] and not new[i]["order"]
        ],
        "ticked": [
            new[i]["text"] for i in new if i in old and not old[i]["order"] and new[i]["order"]
        ],
    }
    if used_ai_reading:
        # The whole list was swapped; count it as one change, not one per row.
        count = 1 + changes["portions_changed"]
    else:
        count = changes["portions_changed"] + sum(
            len(changes[k]) for k in ("added", "removed", "edited", "unticked", "ticked")
        )
    return {**changes, "change_count": int(count)}


# --- Responses and storage --------------------------------------------------------------


async def _response(db: AsyncSession, row: RecipeDraftRow) -> RecipeDraft:
    ingredients = _ingredients(row.ingredients)
    matched = await recipes.recipe_hit(db, row.matched_recipe_id) if row.matched_recipe_id else None
    ai_reading = _ingredients(row.ai_reading["ingredients"]) if row.ai_reading else None
    return RecipeDraft(
        draft_id=str(row.id),
        status=row.status,
        source=row.source,
        is_guess=row.source == "dish_photo",
        dish=row.dish,
        portions=row.portions,
        servings_on_source=row.servings_on_source,
        ingredients=ingredients,
        scaled=scale(ingredients, row.portions, row.servings_on_source),
        matched_recipe=matched,
        ai_reading=ai_reading,
        speak=_speak(row, len(ingredients), matched.name if matched else None),
    )


def _speak(row: RecipeDraftRow, count: int, matched: str | None) -> Localized:
    if row.status == "confirmed":
        return Localized(
            fi=f"Resepti {row.dish} on vahvistettu, {row.portions} annosta. "
            "Seuraavaksi teen siitä tarjouksen.",
            en=f"The recipe {row.dish} is confirmed for {row.portions} portions. "
            "Next I'll build the quote from it.",
        )
    if row.status == "discarded":
        return Localized(fi="Reseptiluonnos hylättiin.", en="The recipe draft was discarded.")
    if matched is not None:
        fi = (
            f"Tämä on arvaus kuvasta: {row.dish}. Löysin reseptin {matched} ja aloitin siitä, "
            f"{count} ainesosaa."
        )
        en = (
            f"This is a guess from the picture: {row.dish}. I found our recipe {matched} and "
            f"started from it, {count} ingredients."
        )
    elif row.source == "dish_photo":
        fi = f"Tämä on arvaus kuvasta: {row.dish}, {count} ainesosaa."
        en = f"This is a guess from the picture: {row.dish}, {count} ingredients."
    else:
        fi = f"Luin reseptistä {row.dish} {count} ainesosaa."
        en = f"I read {count} ingredients for {row.dish}."
    return Localized(
        fi=f"{fi} Tarkista lista ja vahvista se ennen tilausta.",
        en=f"{en} Please check the list and confirm it before ordering.",
    )


def _dump(ingredients: list[DraftIngredient]) -> list[dict[str, Any]]:
    """As stored in JSONB: amounts as exact strings."""
    return [{**i.model_dump(mode="json"), "amount": _exact(i.amount)} for i in ingredients]


def _exact(amount: Decimal | None) -> str | None:
    """The amount as "2", never "2.0" or "2E+0", so it always compares and hashes equal."""
    return None if amount is None else format(amount.normalize(), "f")


def _ingredients(stored: list[dict[str, Any]]) -> list[DraftIngredient]:
    return [DraftIngredient.model_validate(i) for i in stored]


async def _load(
    db: AsyncSession, caller: Caller, draft_id: str, *, for_update: bool = False
) -> RecipeDraftRow:
    """The caller's company's draft, or NotFoundError (also for another company's draft)."""
    draft_uuid = sessions.parse_uuid(draft_id)
    if draft_uuid is None:
        raise NotFoundError("recipe draft not found")
    query = select(RecipeDraftRow).where(
        RecipeDraftRow.id == draft_uuid, RecipeDraftRow.company_id == caller.company_id
    )
    if for_update:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None:
        raise NotFoundError("recipe draft not found")
    return row


async def _touch(db: AsyncSession, row: RecipeDraftRow, now: datetime) -> None:
    session = await db.get_one(OrderSession, row.session_id, with_for_update=True)
    sessions.touch(session, now)
    await db.flush()


async def _record_read(
    db: AsyncSession,
    row: RecipeDraftRow,
    read: list[DraftIngredient],
    *,
    copied_from: uuid.UUID | None,
) -> None:
    payload = {
        "draft_id": str(row.id),
        "source": row.source,
        "dish": row.dish,
        "portions": row.portions,
        "servings_on_source": row.servings_on_source,
        "ingredient_count": len(read),
        # As read, data only: shown as text on the dashboard, never followed.
        "ingredients": [i.text for i in read],
        "low_confidence": [i.text for i in read if i.confidence == "low"],
        "matched_recipe_id": row.matched_recipe_id,
        "image_sha256": row.image_sha256,
        "copied_from": str(copied_from) if copied_from else None,
    }
    if copied_from is not None:
        text = Localized(
            fi=f"Resepti {row.dish} kopioitiin uudeksi luonnokseksi",
            en=f"The recipe {row.dish} was copied into a new draft",
        )
    else:
        text = Localized(
            fi=f"Luettiin resepti: {row.dish}, {len(read)} ainesosaa",
            en=f"Read a recipe: {row.dish}, {len(read)} ingredients",
        )
    await _record(db, "recipe_read", row, payload, text)


async def _record(
    db: AsyncSession, type: str, row: RecipeDraftRow, payload: dict[str, Any], text: Localized
) -> None:
    try:
        await audit.record(
            db,
            type=type,
            actor="service",
            session_id=row.session_id,
            quote_id=None,
            payload=payload,
            text=text,
        )
    except audit.PersonalDataError as error:
        raise StateError(
            "the recipe seems to contain personal data such as a phone number or an email; "
            "remove it and try again"
        ) from error
