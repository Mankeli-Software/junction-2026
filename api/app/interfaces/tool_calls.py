"""Runs one agent tool call for the MCP tools and their REST twins (#45).

Every tool call is one database transaction: whatever the service writes (session, quote,
audit events) commits or rolls back together.
"""

import inspect
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.interfaces.deps import DEV_CALLER
from app.services import dev_caller
from app.services.caller import Caller
from app.settings import get_settings

# A service is either `fn(caller[, request])`, or async `fn(db, caller[, request])` when it
# needs the database.
Service = Callable[..., Any]


async def run_tool(
    name: str, caller: Caller, service: Service, request: BaseModel | None
) -> BaseModel:
    async with get_sessionmaker()() as db, db.begin():
        if _is_dev_caller(caller):
            await dev_caller.ensure_rows(db, caller)
        return await _call(service, db, caller, request)


async def _call(
    service: Service, db: AsyncSession, caller: Caller, request: BaseModel | None
) -> BaseModel:
    args = (caller,) if request is None else (caller, request)
    if inspect.iscoroutinefunction(service):
        return await service(db, *args)
    return service(*args)


def _is_dev_caller(caller: Caller) -> bool:
    return get_settings().dev_fake_caller and caller.user_id == DEV_CALLER.user_id
