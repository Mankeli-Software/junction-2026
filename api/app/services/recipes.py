"""Recipe search and scaling on the two fixture recipes. The real recipe data replaces it."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.schemas import (
    GetRecipeRequest,
    Recipe,
    RecipeHit,
    RecipeIngredient,
    SearchRecipesRequest,
    SearchRecipesResponse,
)
from app.services.caller import Caller
from app.services.errors import NotFoundError
from app.services.fixtures import load


def _recipes() -> list[dict[str, Any]]:
    return load("recipes.json")["recipes"]


def _product_map() -> dict[str, str]:
    return load("recipes.json")["product_map"]


def _tags(recipe: dict[str, Any], group: str) -> list[str]:
    """Taxonomy values without the prefix: "erityisruokavaliot=laktoositon" is "laktoositon"."""
    return [value.split("=", 1)[-1] for value in recipe["taxonomies"].get(group, [])]


def _image_url(recipe: dict[str, Any]) -> str | None:
    image = recipe.get("image")
    return image["sizes"][0]["url"] if image and image["sizes"] else None


def search_recipes(caller: Caller, request: SearchRecipesRequest) -> SearchRecipesResponse:
    """Case-insensitive substring match on the name, then the diet and occasion filters."""
    q = request.q.casefold()
    hits = [r for r in _recipes() if q in r["name"].casefold()]
    hits = [r for r in hits if set(request.diet) <= set(_tags(r, "diet"))]
    if request.occasion is not None:
        hits = [r for r in hits if request.occasion in _tags(r, "occasion")]
    return SearchRecipesResponse(
        results=[
            RecipeHit(
                recipe_id=str(r["id"]),
                name=r["name"],
                image_url=_image_url(r),
                default_portions=r["defaultPortions"],
                diet_tags=_tags(r, "diet"),
            )
            for r in hits[: request.limit]
        ]
    )


def _unit(portion_format: str | None) -> str | None:
    """The unit of a portion format such as "%s kg" (the data has a no-break space there)."""
    if not portion_format:
        return None
    return portion_format.replace("%s", "").replace("\xa0", " ").strip() or None


def _ingredient(index: int, raw: dict[str, Any], portions: int) -> RecipeIngredient:
    amounts = raw.get("singlePortionAmounts") or []
    quantity = None
    if amounts:
        scaled = Decimal(str(amounts[0])) * portions
        quantity = scaled.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    product_id = raw.get("productId")
    return RecipeIngredient(
        index=index,
        name=raw["name"],
        quantity=quantity,
        unit=_unit(raw.get("portionFormat")),
        product_id=_product_map().get(str(product_id)) if product_id is not None else None,
    )


def get_recipe(caller: Caller, request: GetRecipeRequest) -> Recipe:
    """Scales `singlePortionAmounts` by the portions."""
    recipe = next((r for r in _recipes() if str(r["id"]) == request.recipe_id), None)
    if recipe is None:
        raise NotFoundError("recipe not found")
    raw_ingredients = [
        i for segment in recipe["ingredientSegments"] for i in segment["ingredients"]
    ]
    return Recipe(
        recipe_id=str(recipe["id"]),
        name=recipe["name"],
        image_url=_image_url(recipe),
        portions=request.portions,
        ingredients=[
            _ingredient(index, raw, request.portions) for index, raw in enumerate(raw_ingredients)
        ],
    )
