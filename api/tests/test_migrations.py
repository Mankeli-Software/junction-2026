"""Needs a migrated Postgres (`uv run alembic upgrade head`). Skipped without DATABASE_URL."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
)


async def test_first_migration_enables_extensions():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT extname FROM pg_extension"))
        installed = {row[0] for row in result}
    await engine.dispose()

    assert {"vector", "pg_trgm", "unaccent"} <= installed
