"""Recipe drafts: a recipe read from a photo, checked and confirmed by the buyer (#80).

The webshop chat reads the photo with our Gemini; a connector's own model reads it and calls
`propose_recipe`. Either way, only a draft the buyer has confirmed (`confirm_recipe`) can be
quoted with `build_quote(recipe_draft_id)`. The photo itself is never stored.
"""

from typing import Literal

from pydantic import Field, model_validator

from .common import JsonDecimal, Localized, StrictModel
from .tools import RecipeHit

RecipeSource = Literal["notebook", "dish_photo"]
DraftStatus = Literal["draft", "confirmed", "discarded"]

MAX_INGREDIENTS = 60


class DraftIngredient(StrictModel):
    """One ingredient as read from the recipe. Amounts are per the recipe as written."""

    index: int = Field(ge=0, le=999)
    text: str = Field(min_length=1, max_length=200)  # as read: "kermaa", "vehnäjauhoja"
    amount: JsonDecimal | None = Field(default=None, gt=0, le=100000)
    unit: str | None = Field(default=None, max_length=20)  # as read: "dl", "rkl", "g", "kpl"
    confidence: Literal["high", "low"] = "high"  # low is highlighted on the card
    note: str | None = Field(default=None, max_length=200)  # "hard to read", "guessed"
    order: bool = True  # the card's "order this" tick; water starts unticked
    # Only for an ingredient of our matched recipe that is linked to a product: the line
    # orders that product instead of searching by the text.
    product_id: str | None = None


def _unique_indexes(ingredients: list[DraftIngredient] | None) -> None:
    if ingredients is None:
        return
    indexes = [i.index for i in ingredients]
    if len(indexes) != len(set(indexes)):
        raise ValueError("each ingredient needs its own index")


class ProposeRecipeRequest(StrictModel):
    """A recipe the buyer showed, as read. Stored as a draft for the buyer to confirm."""

    dish: str = Field(min_length=1, max_length=120)
    portions: int = Field(ge=1, le=1000)  # what the buyer wants
    servings_on_source: int | None = Field(default=None, ge=1, le=1000)  # what the recipe makes
    ingredients: list[DraftIngredient] = Field(min_length=1, max_length=MAX_INGREDIENTS)
    source: RecipeSource

    @model_validator(mode="after")
    def _indexes(self) -> "ProposeRecipeRequest":
        _unique_indexes(self.ingredients)
        return self


class RecipeDraft(StrictModel):
    """A recipe draft as stored. `ingredients` are as edited, not scaled; `scaled` has the
    amounts for `portions`, which is what will be ordered."""

    draft_id: str
    status: DraftStatus
    source: RecipeSource
    is_guess: bool  # source == dish_photo
    dish: str
    portions: int
    servings_on_source: int | None
    ingredients: list[DraftIngredient]
    scaled: list[DraftIngredient]
    matched_recipe: RecipeHit | None  # for a dish photo, a recipe from our data
    # For a dish photo that matched a recipe: what the AI saw, behind the "Use what the AI
    # saw instead" switch. Null otherwise.
    ai_reading: list[DraftIngredient] | None = None
    speak: Localized


class ConfirmRecipeRequest(StrictModel):
    """Confirms a draft after the buyer said it is right, with their corrections. Leave out
    what didn't change."""

    draft_id: str
    portions: int | None = Field(default=None, ge=1, le=1000)
    # The full edited list, when edited.
    ingredients: list[DraftIngredient] | None = Field(
        default=None, min_length=1, max_length=MAX_INGREDIENTS
    )
    # Dish photo: keep what the AI saw instead of our matched recipe.
    use_ai_reading: bool = False

    @model_validator(mode="after")
    def _indexes(self) -> "ConfirmRecipeRequest":
        _unique_indexes(self.ingredients)
        return self


class ConfirmRecipeBody(StrictModel):
    """The body of `POST /recipe-drafts/{draft_id}/confirm`: the request without the id."""

    portions: int | None = Field(default=None, ge=1, le=1000)
    ingredients: list[DraftIngredient] | None = Field(
        default=None, min_length=1, max_length=MAX_INGREDIENTS
    )
    use_ai_reading: bool = False
