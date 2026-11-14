import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.settings import psycopg_url

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """A freshly migrated database of its own (`<name>_test`), so tests never touch the
    development data. Skipped without DATABASE_URL."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    url = make_url(psycopg_url(os.environ["DATABASE_URL"]))
    test_url = url.set(database=f"{url.database}_test")

    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{test_url.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    await admin.dispose()

    rendered = test_url.render_as_string(hide_password=False)
    env = {**os.environ, "DATABASE_URL": rendered, "MIGRATION_DATABASE_URL": ""}
    await asyncio.to_thread(
        subprocess.run, ["alembic", "upgrade", "head"], cwd=API_DIR, env=env, check=True
    )

    engine = create_async_engine(test_url)
    yield engine
    await engine.dispose()
