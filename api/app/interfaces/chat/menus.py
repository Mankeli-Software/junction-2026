"""The chat's local `show_menu` function (#57, plan §4.A step 5).

Like the relay's `end_call`, it sits next to the MCP tools and is not an MCP tool. The model
only arranges recipes on weekdays; every recipe id is checked against our recipe data and
unknown ones go back to the model as an error. The menu is kept in the conversation and the
`MenuWeek` card loads it from `GET /api/v1/chat/menus/{menu_id}`.
"""

import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.chat.conversations import Menu, MenuSlot
from app.interfaces.chat.schemas import ChatMenu, ChatMenuDay
from app.schemas import GetRecipeRequest
from app.services import recipes
from app.services.caller import Caller
from app.services.errors import ServiceError

SHOW_MENU = "show_menu"
DAYS = ("mon", "tue", "wed", "thu", "fri")

SHOW_MENU_DESCRIPTION = (
    "Show the buyer a weekly lunch menu as a card: Monday to Friday, one main dish a day. "
    "Use recipe ids from search_recipes only, with the buyer's portion count. The card lets "
    "the buyer swap a day or build the order; when they swap a day, call show_menu again "
    "with the new arrangement. Returns the menu_id."
)

SHOW_MENU_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "days": {
            "type": "array",
            "description": "One entry per weekday, Monday to Friday, at most one per day.",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "string", "enum": list(DAYS)},
                    "recipe_id": {"type": "string", "description": "From search_recipes"},
                    "portions": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "required": ["day", "recipe_id", "portions"],
            },
        }
    },
    "required": ["days"],
}


def parse_days(arguments: Any) -> list[MenuSlot] | str:
    """The menu's slots in weekday order, or what is wrong with them."""
    days = arguments.get("days") if isinstance(arguments, dict) else None
    if not isinstance(days, list) or not days:
        return "give days: a list of {day, recipe_id, portions}"
    slots: dict[str, MenuSlot] = {}
    for raw in days:
        if not isinstance(raw, dict):
            return "each day is {day, recipe_id, portions}"
        day, recipe_id, portions = raw.get("day"), raw.get("recipe_id"), raw.get("portions")
        if day not in DAYS:
            return f"unknown day {day!r}; use one of {', '.join(DAYS)}"
        if day in slots:
            return f"{day} is given twice; one dish per day"
        if isinstance(portions, float) and portions.is_integer():
            portions = int(portions)
        if not isinstance(portions, int) or isinstance(portions, bool) or not 1 <= portions <= 1000:
            return f"portions for {day} must be a whole number from 1 to 1000"
        slots[day] = MenuSlot(day=day, recipe_id=str(recipe_id or "").strip(), portions=portions)
    return [slots[d] for d in DAYS if d in slots]


async def show_menu(db: AsyncSession, arguments: Any) -> tuple[Menu | None, dict[str, Any]]:
    """A checked menu and the function response, or None and an error for the model."""
    slots = parse_days(arguments)
    if isinstance(slots, str):
        return None, {"error": slots}
    unknown = [s.recipe_id for s in slots if await recipes.recipe_hit(db, s.recipe_id) is None]
    if unknown:
        return None, {
            "error": f"unknown recipe ids: {', '.join(repr(u) for u in unknown)}. "
            "Use recipe ids that search_recipes returned."
        }
    menu = Menu(menu_id=f"menu-{secrets.token_hex(6)}", days=tuple(slots))
    return menu, {
        "output": {
            "menu_id": menu.menu_id,
            "days": [
                {"day": s.day, "recipe_id": s.recipe_id, "portions": s.portions} for s in slots
            ],
        }
    }


async def menu_view(db: AsyncSession, caller: Caller, menu: Menu) -> ChatMenu:
    days = []
    for slot in menu.days:
        hit = await recipes.recipe_hit(db, slot.recipe_id)
        linked = total = None
        if hit is not None:
            try:
                recipe = await recipes.get_recipe(
                    db, caller, GetRecipeRequest(recipe_id=slot.recipe_id, portions=slot.portions)
                )
            except ServiceError:
                recipe = None
            if recipe is not None:
                total = len(recipe.ingredients)
                linked = sum(1 for i in recipe.ingredients if i.product_id)
        days.append(
            ChatMenuDay(
                day=slot.day,  # type: ignore[arg-type]
                recipe_id=slot.recipe_id,
                name=hit.name if hit else slot.recipe_id,
                image_url=hit.image_url if hit else None,
                portions=slot.portions,
                linked_count=linked,
                ingredient_count=total,
            )
        )
    return ChatMenu(menu_id=menu.menu_id, days=days)


def describe(menu: Menu) -> str:
    """The menu in one line for the model, for the menu card's actions."""
    return "; ".join(f"{s.day} recipe {s.recipe_id} for {s.portions}" for s in menu.days)
