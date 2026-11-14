"""FastAPI entry point. The real routes and the MCP server come in #43."""

from fastapi import FastAPI
from sqlalchemy import text

from app.db import get_engine

app = FastAPI(title="S.I.MO API", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs")


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {"status": "ok", "database": database}
