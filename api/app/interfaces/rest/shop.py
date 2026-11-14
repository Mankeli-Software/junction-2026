"""The webshop's public catalogue (#118): no login, no prices or stock.

Prices and availability come only through the agent tools (#56), so these endpoints only
say what the shop shows: the category tree and a category's top products with images.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import ShopCatalogue, ShopProducts
from app.services import shop

router = APIRouter(prefix="/shop", tags=["shop"])

Db = Annotated[AsyncSession, Depends(get_session)]

# The catalogue changes only when it is reloaded.
CACHE = "public, max-age=300"


@router.get("/categories", response_model=ShopCatalogue)
async def get_categories(db: Db, response: Response) -> ShopCatalogue:
    """Sections > groups > categories, in the shop's order. Only categories with at least
    one product that has an image are listed."""
    response.headers["Cache-Control"] = CACHE
    return await shop.load_catalogue(db)


@router.get("/categories/{category_id}/products", response_model=ShopProducts)
async def get_category_products(category_id: str, db: Db, response: Response) -> ShopProducts:
    """The category's top 20 products with an image, best first. Unknown category: 404."""
    response.headers["Cache-Control"] = CACHE
    return await shop.load_products(db, category_id)
