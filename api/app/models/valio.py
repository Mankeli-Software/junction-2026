"""Cache of Valio API responses (#31). One row per endpoint, product and requested date."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApiCache(Base):
    __tablename__ = "api_cache"

    endpoint: Mapped[str] = mapped_column(Text, primary_key=True)  # "price" or "availability"
    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    requested_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # This product's entry from the API response, as returned.
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
