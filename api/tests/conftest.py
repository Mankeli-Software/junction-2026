"""Shared fixtures. Database tests run only when DATABASE_URL is exported (CLAUDE.md)."""

import asyncio
import json
import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import app.db
from app.loaders.catalogue import ALLERGEN_CODE_FILE, CATEGORY_FILE, load
from app.loaders.product_file import read_allergen_codes, read_categories

# Tests never call the Gemini API: search is text-only here (no product vectors in the
# test database anyway). Environment variables win over .env.
os.environ["SEARCH_VECTORS"] = "off"

from app.main import app as fastapi_app
from app.settings import get_settings, psycopg_url

API_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

# The test catalogue (#29, #30): the loader sample (the milk shortlist of
# valio-api-analysis.md §11, whose prices and availability are recorded in data/snapshots/)
# plus the search sample (distractors and an oat drink).
CATALOGUE_SAMPLES = ("products_sample.json", "products_search_sample.json")

# What the HTTP-level tests write, emptied after each of them.
ACCOUNT_TABLES = (
    "sms_messages",
    "confirmations",
    "quote_lines",
    "quotes",
    "sessions",
    "oauth_refresh_tokens",
    "oauth_codes",
    "oauth_requests",
    "oauth_clients",
    "access_tokens",
    "web_sessions",
    "users",
    "kitchen_profiles",
    "companies",
)

# Append-only (#41): their triggers refuse TRUNCATE, so tests switch them off to empty them.
AUDIT_TABLES = ("status_events", "audit_events", "rule_sets")


async def empty_audit_tables(conn: AsyncConnection) -> None:
    """Empty the append-only audit tables in the caller's transaction (tests only)."""
    for table in AUDIT_TABLES:
        await conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
    await conn.execute(text(f"TRUNCATE {', '.join(AUDIT_TABLES)}"))
    for table in AUDIT_TABLES:
        await conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))


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


@cache
def catalogue_products() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for name in CATALOGUE_SAMPLES:
        products += json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return products


@pytest.fixture
async def catalogue(db_engine: AsyncEngine) -> AsyncEngine:
    """The test catalogue in the test database, committed. Loaded again only when the
    stored products differ, for example after the loader tests."""
    products = catalogue_products()
    async with db_engine.connect() as conn:
        stored = sorted((await conn.scalars(text("SELECT id FROM products"))).all())
    if stored != sorted(p["id"] for p in products):
        if stored:
            async with db_engine.begin() as conn:
                await conn.execute(text("DELETE FROM products"))
        await load(
            db_engine,
            products,
            read_categories(CATEGORY_FILE),
            read_allergen_codes(ALLERGEN_CODE_FILE),
        )
    return db_engine


@pytest.fixture
async def db(db_engine: AsyncEngine, catalogue: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test, with the test
    catalogue loaded.

    Commits in the code under test become savepoints, so nothing is left behind.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


def _set_fake_caller(monkeypatch: pytest.MonkeyPatch, on: bool):
    monkeypatch.setenv("DEV_FAKE_CALLER", "true" if on else "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def dev_caller(monkeypatch: pytest.MonkeyPatch):
    """Requests act as the fixed demo customer (DEV_FAKE_CALLER=true)."""
    yield from _set_fake_caller(monkeypatch, True)


@pytest.fixture
def no_caller(monkeypatch: pytest.MonkeyPatch):
    """Nobody is signed in (DEV_FAKE_CALLER=false)."""
    yield from _set_fake_caller(monkeypatch, False)


@pytest.fixture
async def app_db(
    db_engine: AsyncEngine, catalogue: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    """Point the app's own database sessions at the test database, for HTTP-level tests,
    with the test catalogue loaded.

    The app commits for real, so the tables it writes are emptied after the test, leaving
    them clean for the `db` tests. NullPool, because TestClient runs requests in other
    event loops.
    """
    engine = create_async_engine(db_engine.url, poolclass=NullPool)
    monkeypatch.setattr(app.db, "get_engine", lambda: engine)
    app.db.get_sessionmaker.cache_clear()
    try:
        yield engine
    finally:
        app.db.get_sessionmaker.cache_clear()
        async with engine.begin() as conn:
            await empty_audit_tables(conn)
            await conn.execute(text(f"TRUNCATE {', '.join(ACCOUNT_TABLES)} CASCADE"))
        await engine.dispose()


@pytest.fixture(scope="session")
def live_client() -> Iterator[TestClient]:
    """A client with the app's lifespan running, which `/mcp` needs.

    The MCP session manager can run only once per process, so every test that calls `/mcp`
    over HTTP shares this one.
    """
    with TestClient(fastapi_app, base_url="http://localhost") as client:
        yield client
