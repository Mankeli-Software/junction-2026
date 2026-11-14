"""The script agent of the live tests (#98), offline: the same `Agent` over an in-memory
MCP session against the test database and the recorded Valio answers. A regression test
that replays a tool sequence (#105) starts from here. Needs DATABASE_URL.
"""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.interfaces.mcp.server import mcp
from tests.live.agent import Agent, ToolFailed, dairy_lines, dead_ends, describe_quote

MILK = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


@pytest.mark.usefixtures("app_db", "dev_caller")
async def test_a_script_runs_offline_through_the_same_agent():
    async with create_connected_server_and_client_session(mcp) as session:
        agent = Agent(session)
        first = await agent.call("build_quote", lines=[MILK])
        second = await agent.call(
            "update_quote", quote_id=first["quote_id"], lines=[{**MILK, "quantity": 30}]
        )
        with pytest.raises(ToolFailed, match="quote not found"):
            await agent.call("get_order_status", quote_id="nope")

    assert [name for name, _ in agent.calls] == ["build_quote", "update_quote", "get_order_status"]
    assert first["decision"] == "ready" and second["parent_quote_id"] == first["quote_id"]
    assert "464306" in describe_quote(second) and "v2" in describe_quote(second)
    assert dairy_lines(second) and not dead_ends(second)


def test_reading_a_quote_tells_milk_products_from_plant_based_ones():
    def quote(*names: str, rejections=()) -> dict:
        lines = [{"name": {"fi": name, "en": name}} for name in names]
        return {"lines": lines, "rejections": list(rejections)}

    assert dairy_lines(quote("Arla Pro laktoositon kirkastettu voi", "Oatly kaurajuoma")) == [
        "Arla Pro laktoositon kirkastettu voi / Arla Pro laktoositon kirkastettu voi"
    ]
    assert not dairy_lines(quote("Keiju kasvirasvalevite", "Porkkana 10 kg", "Voileipäkeksi"))
    assert len(dairy_lines(quote("PECORINO ROMANO JUUSTORAASTE", "Valio kevytmaito 1 l"))) == 2

    step = {"fi": "Asiakaspalvelu soittaa.", "en": "Customer service calls."}
    blank = {"fi": "", "en": ""}
    rejected = [
        {"line_id": "a", "reason_code": "CALLBACK_REQUESTED", "next_step": step},
        {"line_id": "b", "reason_code": "PRODUCT_NOT_FOUND", "next_step": blank},
    ]
    assert dead_ends(quote(rejections=rejected)) == ["b PRODUCT_NOT_FOUND"]
