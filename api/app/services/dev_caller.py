"""Database rows for the DEV_FAKE_CALLER demo customer (tests and local dev only).

The fixed dev caller (`app.interfaces.deps.DEV_CALLER`) has fixed UUIDs but no rows, and
sessions and quotes have foreign keys to `users` and `companies`. The tool-call wrapper
calls `ensure_rows()` only when the request was resolved to the dev caller, which happens
only with DEV_FAKE_CALLER=true or, on /mcp, MCP_AUTH_REQUIRED=false (#48), so production
paths with auth on never write these rows.
"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, KitchenProfile, User
from app.services.caller import Caller

# Never sent anything: SMS is off and only allowlisted numbers get one (technical-plan §8.2).
DEV_PHONE_E164 = "+358400000012"


async def ensure_rows(db: AsyncSession, caller: Caller) -> None:
    """Idempotent: insert the caller's company, kitchen profile and user if missing."""
    await db.execute(
        insert(Company)
        .values(id=caller.company_id, name=caller.company_name, phone_e164=DEV_PHONE_E164)
        .on_conflict_do_nothing()
    )
    if await db.get(Company, caller.company_id) is None:
        raise RuntimeError(
            f"the dev company's name {caller.company_name!r} or number is taken by another "
            "company; remove that company from the development database"
        )
    await db.execute(
        insert(KitchenProfile)
        .values(company_id=caller.company_id, exclusions=[e.value for e in caller.exclusions])
        .on_conflict_do_nothing()
    )
    await db.execute(
        insert(User)
        .values(
            id=caller.user_id,
            company_id=caller.company_id,
            phone_e164=DEV_PHONE_E164,
            lang=caller.lang,
        )
        .on_conflict_do_nothing()
    )
