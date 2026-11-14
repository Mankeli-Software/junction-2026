"""The phone call of #99, replayed tool call by tool call (#105).

In that call a recipe quote (cheese and milk) was followed by an `update_quote` with six
lines, five of them invalid: the result was a `ready` quote with one product, the cheese
and milk were gone, and the agent could not repair it. The caller had also asked for
milk-free twice and got regular milk.

This plays the same sequence through the script agent of the live tests (#98) over an
in-memory MCP session, against the test database and the recorded Valio answers, and
checks what the contract decided in #101, #102 and #106 says must happen. The fixtures
have no macaroni casserole with linked products, so the rye bread recipe stands in: two
linked milk products (piimä and butter) and four ingredients that are not ordered.
Needs DATABASE_URL.
"""

import uuid

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import engine
from app.interfaces.deps import DEV_CALLER
from app.interfaces.mcp.server import mcp
from app.models import AuditEvent, Quote
from app.models import KitchenProfile as KitchenProfileRow
from app.schemas import EngineInput
from app.services import dev_caller as dev_caller_rows
from app.services import quotes
from app.services.audit import load_rule_set_by_ref
from app.services.dashboard import orders
from tests.live.agent import Agent, ToolFailed, dairy_lines, dead_ends
from tests.test_recipes import BREAD, borrowed_offers  # noqa: F401 (a fixture)

DAY = "2026-11-16"
PORTIONS = 60
PIIMA, BUTTER, ARLA = "463373", "463798", "463047"
MILK_PRODUCTS = {PIIMA, BUTTER, ARLA}

RECIPE_LINE = {
    "line_id": "1",
    "quantity": PORTIONS,
    "unit": "piece",
    "needed_by": DAY,
    "recipe_ref": {"recipe_id": BREAD, "portions": PORTIONS},
    "group": "Rukiinen piimäleipä",
}


def text_line(line_id: str, text: str, quantity: float, unit: str, **more) -> dict:
    return {
        "line_id": line_id,
        "text": text,
        "quantity": quantity,
        "unit": unit,
        "needed_by": DAY,
        **more,
    }


# The update of the call: the recipe's missing ingredients as five lines with
# `unit: "package"` and no `package_word`, and one line that is fine.
BROKEN = [
    text_line("2", "ruisjauho", 5, "package"),
    text_line("3", "vehnäjauho", 11, "package"),
    text_line("4", "hiiva", 1, "package"),
    text_line("5", "suola", 1, "package"),
    text_line("6", "siirappi", 1, "package"),
]
FINE = text_line("7", "arla", 3, "l")


def quoted(quote: dict) -> list[tuple[str, str]]:
    return [(line["line_id"], line["product_id"]) for line in quote["lines"]]


async def kitchen_without_exclusions(app_db: AsyncEngine) -> None:
    """The dev caller's kitchen is lactose-free; the caller of #99 had no exclusions."""
    async with AsyncSession(app_db) as db:
        await dev_caller_rows.ensure_rows(db, DEV_CALLER)
        await db.execute(
            update(KitchenProfileRow)
            .where(KitchenProfileRow.company_id == DEV_CALLER.company_id)
            .values(exclusions=[])
        )
        await db.commit()


@pytest.mark.usefixtures("recipes", "borrowed_offers", "dev_caller")
async def test_the_recipe_call_of_issue_99_no_longer_loses_the_order(app_db: AsyncEngine):
    await kitchen_without_exclusions(app_db)

    async with create_connected_server_and_client_session(mcp) as session:
        agent = Agent(session)

        # 1. "Add the recipe's ingredients to my order": one recipe line.
        first = await agent.call("build_quote", lines=[RECIPE_LINE])
        assert first["decision"] == "ready"
        assert quoted(first) == [("1-0", PIIMA), ("1-3", BUTTER)]
        assert [n["name"] for n in first["not_ordered"]] == [
            "suolaa",
            "hiivaa",
            "ruisjauhoja",
            "vehnäjauhoja",
        ]

        # 2. "Yes, add those as well": six lines, five of them invalid. The whole update
        # is refused, every bad line is named with its field, and nothing is stored.
        with pytest.raises(ToolFailed) as refused:
            await agent.call("update_quote", quote_id=first["quote_id"], lines=[*BROKEN, FINE])
        message = refused.value.message
        for line in BROKEN:
            assert f"line {line['line_id']}, PACKAGE_WORD_MISSING" in message
        assert "line 7" not in message and "package_word" in message
        assert f"The current quote {first['quote_id']} is unchanged." in message
        status = await agent.call("get_order_status", quote_id=first["quote_id"])
        assert (status["status"], status["replaced_by_quote_id"]) == ("ready", None)

        # 3. "Can you retry?": the agent fixes the field and sends the same lines again,
        # without asking the caller. The cheese and milk of the recipe are still there.
        fixed = [{**line, "package_word": "pussi"} for line in BROKEN]
        second = await agent.call("update_quote", quote_id=first["quote_id"], lines=[*fixed, FINE])
        assert (second["version"], second["parent_quote_id"]) == (2, first["quote_id"])
        assert quoted(second) == [("1-0", PIIMA), ("1-3", BUTTER), ("7", ARLA)]
        assert not dead_ends(second)
        # The fixture catalogue has no flour or yeast: the engine asks about the first one.
        assert second["decision"] == "needs_clarification"
        assert second["clarification"]["line_id"] == "2"

        # 4. "What's my order right now?" The caller drops what can't be found.
        third = await agent.call(
            "update_quote", quote_id=second["quote_id"], remove_line_ids=["2", "3", "4", "5", "6"]
        )
        assert third["decision"] == "ready" and third["version"] == 3
        assert quoted(third) == quoted(second)

        # 5. "And milk-free": for this order only, on every line and recipe ingredient.
        fourth = await agent.call(
            "update_quote", quote_id=third["quote_id"], exclusions=["milk_free"]
        )
        assert not dairy_lines(fourth)
        assert not {product for _, product in quoted(fourth)} & MILK_PRODUCTS
        assert not dead_ends(fourth)
        # The piimä gets a safe product as a question (one question per turn; the Arla
        # milk waits for its own), and the butter, with no safe product, a next step.
        assert fourth["decision"] == "needs_clarification"
        assert fourth["clarification"]["line_id"] == "1-0"
        oat = fourth["clarification"]["options"][0]
        assert oat["product_id"] not in MILK_PRODUCTS
        assert [(r["line_id"], r["reason_code"]) for r in fourth["rejections"]] == [
            ("1-3", "ALLERGEN_CONFLICT")
        ]

        # 6. The caller takes the oat drink. The order is still milk-free, without
        # sending the exclusion again, and the rejected lines are told apart.
        answer = {
            "line_id": "1-0",
            "product_id": oat["product_id"],
            "quantity": 6,
            "unit": "l",
            "needed_by": DAY,
            "group": RECIPE_LINE["group"],
        }
        fifth = await agent.call("update_quote", quote_id=fourth["quote_id"], lines=[answer])
        assert quoted(fifth) == [("1-0", oat["product_id"])]
        assert fifth["version"] == 5 and not dairy_lines(fifth)
        waiting = {r["line_id"] for r in fifth["rejections"]}
        if fifth["clarification"]:
            waiting.add(fifth["clarification"]["line_id"])
        assert waiting == {"1-3", "7"} and not dead_ends(fifth)

    assert [name for name, _ in agent.calls] == [
        "build_quote",
        "update_quote",
        "get_order_status",
        "update_quote",
        "update_quote",
        "update_quote",
        "update_quote",
    ]

    async with AsyncSession(app_db) as db:
        rows = (await db.scalars(select(Quote).order_by(Quote.version))).all()
        # One chain: every version points at the one before, only the last one is live.
        assert [row.version for row in rows] == [1, 2, 3, 4, 5]
        assert [row.parent_quote_id for row in rows] == [None, *(row.id for row in rows[:-1])]
        assert [row.status for row in rows[:-1]] == ["void"] * 4
        assert rows[-1].id == uuid.UUID(fifth["quote_id"])
        # The one-off exclusion is on the quotes from where it was asked, not before.
        assert [row.engine_input.get("order_exclusions") for row in rows] == [
            None,
            None,
            None,
            ["milk_free"],
            ["milk_free"],
        ]
        # Every stored quote replays to the same decision from its own input.
        for row in rows:
            rules = await load_rule_set_by_ref(db, row.rules_ref)
            stored = EngineInput.model_validate({**row.engine_input, "rules": rules})
            # The recipe drafts and the group images are the service's, added after the engine.
            replayed = await quotes.with_group_images(
                db,
                quotes.with_recipe_drafts(engine.decide(stored), stored.recipe_drafts),
                stored.lines,
                stored.recipe_drafts,
            )
            assert replayed.model_dump(mode="json") == row.engine_output, row.version

        # The audit trail: the refused update is on record as a failed tool call, with no
        # quote behind it, and the chain verifies.
        events = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.session_id == rows[0].session_id)
                .order_by(AuditEvent.seq)
            )
        ).all()
        types = [event.type for event in events]
        assert types.count("quote_voided") == 4 and types.count("quote_edited") == 4
        failed = [e for e in events if e.type == "tool_returned" and "error" in (e.payload or {})]
        assert len(failed) == 1 and "PACKAGE_WORD_MISSING" in failed[0].payload["error"]
        check = await orders.verify(db, str(rows[0].session_id))
        assert check.ok, check
