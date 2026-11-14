"""The recipe tools and recipe lines in build_quote (#34, technical-plan.md §5.4, vision §7).

- `search_recipes`: hybrid search (app.recipes.search) with the diet and occasion filters.
- `get_recipe`: `singlePortionAmounts` scaled to the portions, with a product id for each
  ingredient that recipe-product-map.json links to a catalogue product.
- `expand_lines`: before the quote service gathers candidates, a line for a whole recipe
  becomes one line per linked ingredient, and the ingredients without a link go to
  `not_ordered`. They don't go through normal product resolution (decided in #34), unless
  the buyer asked for them (`recipe_ref.order_unlinked`, #103): then each one with an
  amount is a line found by the ingredient's name, like any text line.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from math import ceil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.units import size_or_name
from app.models import Product, RecipeProductLink, RecipeTag
from app.models import Recipe as RecipeRow
from app.models import RecipeIngredient as IngredientRow
from app.recipes import search as recipe_search
from app.recipes.scaling import Pack, choose_pack, scale
from app.schemas import (
    GetRecipeRequest,
    LineRequest,
    Localized,
    NotOrdered,
    Recipe,
    RecipeHit,
    RecipeIngredient,
    RecipeRef,
    RequestedUnit,
    SearchRecipesRequest,
    SearchRecipesResponse,
)
from app.schemas.engine import MAX_LINES, MAX_QUANTITY, MAX_TEXT_LENGTH
from app.search.text import fold
from app.services import catalog
from app.services.caller import Caller
from app.services.errors import InvalidRequestError, NotFoundError

NOT_LINKED = Localized(
    fi="Ei linkitetty tuotteeseen, hanki muualta",
    en="Not linked to a product, get it elsewhere",
)
NO_AMOUNT = Localized(fi="Reseptissä ei ole määrää", en="The recipe gives no amount")
NOT_IN_CATALOGUE = Localized(
    fi="Linkitettyä tuotetta ei ole valikoimassa", en="The linked product is not in the catalogue"
)
LINE_ID_LENGTH = 40
GROUP_LENGTH = 80


# --- search_recipes ---------------------------------------------------------------------


async def search_recipes(
    db: AsyncSession, caller: Caller, request: SearchRecipesRequest
) -> SearchRecipesResponse:
    words, said_diets = recipe_search.split_query(request.q)
    diets = await _tag_values(db, ["diet"], request.diet, "diet")
    occasion = None
    if request.occasion is not None:
        [occasion] = await _tag_values(
            db, list(recipe_search.OCCASION_GROUPS), [request.occasion], "occasion"
        )
    query = recipe_search.RecipeQuery(
        text=words, diet=tuple(dict.fromkeys([*diets, *said_diets])), occasion=occasion
    )
    matches = await recipe_search.search(db, query, request.limit)
    ids = [m.recipe_id for m in matches]
    recipes = {r.id: r for r in await db.scalars(select(RecipeRow).where(RecipeRow.id.in_(ids)))}
    diet_tags = await _diet_tags(db, ids)
    return SearchRecipesResponse(
        results=[
            RecipeHit(
                recipe_id=str(i),
                name=recipes[i].name,
                image_url=recipes[i].image_url,
                default_portions=recipes[i].default_portions,
                diet_tags=diet_tags.get(i, []),
            )
            for i in ids
        ]
    )


async def recipe_hit(db: AsyncSession, recipe_id: str) -> RecipeHit | None:
    """One recipe as a search hit, or None. For a recipe draft's matched recipe (#80)."""
    recipe = await db.get(RecipeRow, int(recipe_id)) if recipe_id.isdigit() else None
    if recipe is None:
        return None
    return RecipeHit(
        recipe_id=str(recipe.id),
        name=recipe.name,
        image_url=recipe.image_url,
        default_portions=recipe.default_portions,
        diet_tags=(await _diet_tags(db, [recipe.id])).get(recipe.id, []),
    )


async def _tag_values(
    db: AsyncSession, groups: list[str], asked: list[str], what: str
) -> list[str]:
    """The tag values for what the agent passed: a value ("laktoositon"), a title
    ("Laktoositon"), or a claim, exclusion or English word ("lactose_free", "lunch").
    Unknown values are an error that lists the known ones, so the agent can correct
    itself."""
    if not asked:
        return []
    known = await recipe_search.known_tags(db, groups)
    aliases = recipe_search.DIET_WORDS if what == "diet" else recipe_search.OCCASION_WORDS
    known = {**{w: v for w, v in aliases.items() if v in known.values()}, **known}
    values = []
    for word in asked:
        folded = fold(word.strip())
        spellings = (folded, re.sub(r"\s+", "-", folded), re.sub(r"[\s-]+", "_", folded))
        value = next((known[s] for s in spellings if s in known), None)
        if value is None:
            choices = ", ".join(sorted(set(known.values())))
            raise InvalidRequestError(f"unknown {what} {word!r}; use one of: {choices}")
        values.append(value)
    return list(dict.fromkeys(values))


async def _diet_tags(db: AsyncSession, ids: list[int]) -> dict[int, list[str]]:
    rows = await db.execute(
        select(RecipeTag.recipe_id, RecipeTag.value)
        .where(RecipeTag.recipe_id.in_(ids), RecipeTag.tag_group == "diet")
        .order_by(RecipeTag.recipe_id, RecipeTag.tag)
    )
    out: dict[int, list[str]] = defaultdict(list)
    for recipe_id, value in rows:
        out[recipe_id].append(value)
    return out


# --- get_recipe -------------------------------------------------------------------------


@dataclass(frozen=True)
class Scaled:
    """One ingredient of a recipe at a portion count."""

    index: int
    name: str
    quantity: Decimal | None
    unit: str | None
    linked: bool  # the recipe data names a product for it
    pack: Pack | None  # the catalogue product picked for the amount; None when not linked


async def get_recipe(db: AsyncSession, caller: Caller, request: GetRecipeRequest) -> Recipe:
    recipe, ingredients = await _scaled_recipe(db, request.recipe_id, request.portions)
    return Recipe(
        recipe_id=str(recipe.id),
        name=recipe.name,
        image_url=recipe.image_url,
        portions=request.portions,
        ingredients=[
            RecipeIngredient(
                index=i.index,
                name=i.name,
                quantity=i.quantity,
                unit=i.unit,
                product_id=i.pack.product_id if i.pack else None,
            )
            for i in ingredients
        ],
    )


async def _scaled_recipe(
    db: AsyncSession, recipe_id: str, portions: int
) -> tuple[RecipeRow, list[Scaled]]:
    recipe = await db.get(RecipeRow, int(recipe_id)) if recipe_id.isdigit() else None
    if recipe is None:
        raise NotFoundError(f"recipe {recipe_id} not found")
    rows = list(
        await db.scalars(
            select(IngredientRow)
            .where(IngredientRow.recipe_id == recipe.id)
            .order_by(IngredientRow.position)
        )
    )
    packs = await _packs(db, {r.recipe_product_id for r in rows if r.recipe_product_id})
    scaled = []
    for row in rows:
        quantity = (
            scale(row.amount_per_portion, portions, row.unit)
            if row.amount_per_portion is not None
            else None
        )
        kilos = quantity if row.unit == "kg" else None
        options = packs.get(row.recipe_product_id, []) if row.recipe_product_id else []
        scaled.append(
            Scaled(
                index=row.position,
                name=row.name,
                quantity=quantity,
                unit=row.unit,
                linked=row.recipe_product_id is not None,
                pack=choose_pack(options, kilos),
            )
        )
    return recipe, scaled


async def _packs(db: AsyncSession, recipe_product_ids: set[int]) -> dict[int, list[Pack]]:
    """The linked packs that are in the catalogue, per recipe product."""
    if not recipe_product_ids:
        return {}
    rows = await db.execute(
        select(RecipeProductLink)
        .join(Product, Product.id == RecipeProductLink.product_id)
        .where(RecipeProductLink.recipe_product_id.in_(recipe_product_ids))
        .order_by(RecipeProductLink.recipe_product_id, RecipeProductLink.product_id)
    )
    out: dict[int, list[Pack]] = defaultdict(list)
    for (link,) in rows:
        out[link.recipe_product_id].append(
            Pack(link.product_id, link.units_per_sales_unit, link.net_weight_kg)
        )
    return out


# --- Recipe lines in build_quote --------------------------------------------------------


async def expand_lines(
    db: AsyncSession, lines: list[LineRequest]
) -> tuple[list[LineRequest], list[NotOrdered]]:
    """The lines the engine gets, and the recipe ingredients that are not ordered.

    - A line whose `recipe_ref` has no `ingredient_index` is the whole recipe at
      `recipe_ref.portions`: one line per linked ingredient, with the pack that fits the
      amount, named `<line_id>-<index>` and grouped under the line's group (the recipe name
      when it has none). Its own quantity and unit are not used.
    - A line for one ingredient stays as sent (an edit on the confirmation page may have
      changed its product or amount). Without a product id it gets the linked pack.
    - With `recipe_ref.order_unlinked` (#103), the ingredients without a product that
      have an amount are ordered too: a whole recipe adds a line found by the ingredient's
      name for each, `<line_id>-<index>` like the linked ones, and an ingredient line sent
      with the flag stays as sent. Their product comes from the normal text search.
    - Every recipe a line refers to lists the ingredients it doesn't order in
      `not_ordered`, also after an edit, when only the ingredient lines are sent again.
      Ingredients with the same name, unit and reason are added up, so a menu lists
      "suolaa" once.
    - Lines without a recipe stay as they are.
    """
    out: list[LineRequest] = []
    # Every recipe the lines refer to, (recipe, portions), in the order first referred to,
    # with its scaled ingredients and whether a line of it asked for the unlinked ones.
    referred: dict[tuple[str, int], tuple[RecipeRow, list[Scaled]]] = {}
    asked: set[tuple[str, int]] = set()
    ordered: set[tuple[str, int, int]] = set()  # (recipe, portions, index) with a line

    def reason_for(i: Scaled) -> Localized | None:
        if not i.linked:
            return NOT_LINKED
        if not i.quantity:
            return NO_AMOUNT
        if i.pack is None:
            return NOT_IN_CATALOGUE
        return None

    for line in lines:
        ref = line.recipe_ref
        if ref is None:
            out.append(line)
            continue
        key = (ref.recipe_id, ref.portions)
        if key not in referred:
            referred[key] = await _scaled_recipe(db, ref.recipe_id, ref.portions)
        recipe, ingredients = referred[key]
        if ref.order_unlinked:
            asked.add(key)
        group = line.group or recipe.name[:GROUP_LENGTH]
        if ref.ingredient_index is not None:
            if not 0 <= ref.ingredient_index < len(ingredients):
                raise InvalidRequestError(
                    f"recipe {ref.recipe_id} has no ingredient {ref.ingredient_index}"
                )
            wanted = ingredients[ref.ingredient_index]
            if reason_for(wanted) is None or line.product_id is not None:
                ordered.add((*key, wanted.index))
                product_id = line.product_id or (wanted.pack.product_id if wanted.pack else None)
                out.append(line.model_copy(update={"product_id": product_id, "group": group}))
            elif ref.order_unlinked:
                # Ordered by name (#103): kept as sent, an edit may have changed the amount.
                ordered.add((*key, wanted.index))
                text = line.text or wanted.name[:MAX_TEXT_LENGTH]
                out.append(line.model_copy(update={"text": text, "group": group}))
        else:
            for i in ingredients:
                if reason_for(i) is None:
                    ordered.add((*key, i.index))
                    out.append(await _ingredient_line(db, line, ref, i, group))
                elif ref.order_unlinked and (named := _named_line(line, ref, i, group)):
                    ordered.add((*key, i.index))
                    out.append(named)

    # Every ingredient of those recipes without a line, after all lines are in: a later
    # line may order one that an earlier line of the same recipe left out.
    not_ordered: list[tuple[str, Decimal | None, str | None, Localized]] = []
    for key, (_, ingredients) in referred.items():
        for i in ingredients:
            if (*key, i.index) in ordered or (reason := reason_for(i)) is None:
                continue
            if key in asked and not i.quantity:
                reason = NO_AMOUNT  # asked for, but nothing to order it by
            not_ordered.append((i.name, i.quantity, i.unit, reason))

    if len(out) > MAX_LINES:
        raise InvalidRequestError(
            f"the recipes make {len(out)} lines, over the limit of {MAX_LINES}; "
            "order fewer recipes at a time"
        )
    if not out and lines:
        if asked:
            raise InvalidRequestError(
                "none of the recipe's ingredients has an amount to order, so there is "
                "nothing to order; tell the buyer to get them elsewhere"
            )
        raise InvalidRequestError(
            "none of the recipe's ingredients is linked to a product, so there is nothing "
            "to order; tell the buyer to get them elsewhere, or, if they ask you to find "
            "products for them, send the recipe line again with recipe_ref.order_unlinked"
        )
    return out, _merged(not_ordered)


# The recipe data gives kilos, or pieces for a few counted ingredients.
NAMED_UNITS = {"kg": RequestedUnit.kg, "kpl": RequestedUnit.piece}


def _named_line(line: LineRequest, ref: RecipeRef, i: Scaled, group: str) -> LineRequest | None:
    """The order line for an ingredient without a product, found by its name (#103), or
    None when it has no amount the engine can order (salt "to taste")."""
    unit = NAMED_UNITS.get((i.unit or "").lower())
    if not i.quantity or unit is None or i.quantity > MAX_QUANTITY:
        return None
    suffix = f"-{i.index}"
    return LineRequest(
        line_id=line.line_id[: LINE_ID_LENGTH - len(suffix)] + suffix,
        text=i.name[:MAX_TEXT_LENGTH],
        claims=line.claims,
        quantity=i.quantity,
        unit=unit,
        needed_by=line.needed_by,
        recipe_ref=RecipeRef(
            recipe_id=ref.recipe_id,
            portions=ref.portions,
            ingredient_index=i.index,
            order_unlinked=True,
        ),
        group=group,
    )


async def _ingredient_line(
    db: AsyncSession, line: LineRequest, ref: RecipeRef, i: Scaled, group: str
) -> LineRequest:
    """The order line for one linked ingredient. The recipe gives kilos. A product sold by
    the litre is asked in litres (1 kg taken as 1 l, as recipe-product-map.json does for
    milk and cream); one with neither in its data is asked in whole sales units from the
    map's pack weight."""
    assert i.pack is not None and i.quantity is not None
    quantity, unit = i.quantity, RequestedUnit.kg
    [product] = await catalog.get_products(db, [i.pack.product_id]) or [None]
    if product is not None and i.unit == "kg":
        if size_or_name(product, product.sales_unit, "KG") is None:
            if size_or_name(product, product.sales_unit, "L") is not None:
                unit = RequestedUnit.l
            elif i.pack.sales_unit_kg:
                quantity = Decimal(ceil(i.quantity / i.pack.sales_unit_kg))
                unit = RequestedUnit.sales_unit
    suffix = f"-{i.index}"
    return LineRequest(
        line_id=line.line_id[: LINE_ID_LENGTH - len(suffix)] + suffix,
        product_id=i.pack.product_id,
        text=i.name[:MAX_TEXT_LENGTH],
        claims=line.claims,
        quantity=quantity,
        unit=unit,
        needed_by=line.needed_by,
        recipe_ref=RecipeRef(
            recipe_id=ref.recipe_id, portions=ref.portions, ingredient_index=i.index
        ),
        group=group,
    )


def _merged(rows: list[tuple[str, Decimal | None, str | None, Localized]]) -> list[NotOrdered]:
    merged: dict[tuple[str, str | None, str], list] = {}
    for name, quantity, unit, reason in rows:
        key = (name.casefold(), unit, reason.en)
        if key in merged:
            entry = merged[key]
            entry[1] = (
                entry[1] + quantity if entry[1] is not None and quantity is not None else None
            )
        else:
            merged[key] = [name, quantity, unit, reason]
    return [
        NotOrdered(name=name, quantity=quantity, unit=unit, reason=reason)
        for name, quantity, unit, reason in merged.values()
    ]
