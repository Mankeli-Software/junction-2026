"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.models.auth import AccessToken, WebSession
from app.models.base import Base
from app.models.catalogue import (
    AllergenCode,
    Category,
    Product,
    ProductAllergen,
    ProductClaim,
    ProductLabel,
    ProductSubstitution,
    ProductUnit,
    ProductUnitConversion,
)
from app.models.customers import Company, KitchenProfile, User

__all__ = [
    "AccessToken",
    "AllergenCode",
    "Base",
    "Category",
    "Company",
    "KitchenProfile",
    "Product",
    "ProductAllergen",
    "ProductClaim",
    "ProductLabel",
    "ProductSubstitution",
    "ProductUnit",
    "ProductUnitConversion",
    "User",
    "WebSession",
]
