"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.models.audit import AuditEvent, RuleSetRow, StatusEvent
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
from app.models.confirmations import Confirmation, ConfirmationAcknowledgement, SmsMessage
from app.models.customers import Company, KitchenProfile, User
from app.models.oauth import OAuthClient, OAuthCode, OAuthRefreshToken, OAuthRequest
from app.models.ordering import OrderSession, Quote, QuoteLine
from app.models.orders import Order, OrderLine
from app.models.valio import ApiCache

__all__ = [
    "AccessToken",
    "ApiCache",
    "AllergenCode",
    "AuditEvent",
    "Base",
    "Category",
    "Company",
    "Confirmation",
    "ConfirmationAcknowledgement",
    "KitchenProfile",
    "OAuthClient",
    "OAuthCode",
    "OAuthRefreshToken",
    "OAuthRequest",
    "Order",
    "OrderLine",
    "OrderSession",
    "Product",
    "ProductAllergen",
    "ProductClaim",
    "ProductLabel",
    "ProductSubstitution",
    "ProductUnit",
    "ProductUnitConversion",
    "SmsMessage",
    "Quote",
    "QuoteLine",
    "RuleSetRow",
    "StatusEvent",
    "User",
    "WebSession",
]
