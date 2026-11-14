import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from app.interfaces.mcp.server import mcp
from app.main import app

TOOL_NAMES = {
    "search_products",
    "get_customer_context",
    "search_recipes",
    "get_recipe",
    "build_quote",
    "update_quote",
    "request_confirmation",
    "get_order_status",
}

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


@pytest.mark.usefixtures("dev_caller")
async def test_lists_exactly_the_eight_tools():
    async with create_connected_server_and_client_session(mcp) as session:
        tools = (await session.list_tools()).tools

    assert {tool.name for tool in tools} == TOOL_NAMES
    for tool in tools:
        assert tool.description
        assert tool.outputSchema is not None
        assert tool.inputSchema.get("additionalProperties") is False


@pytest.mark.usefixtures("dev_caller")
async def test_build_quote_is_ready():
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("build_quote", {"lines": [LINE]})

    assert not result.isError, result.content
    assert result.structuredContent["decision"] == "ready"
    assert result.structuredContent["lines"][0]["product_id"] == "464306"


@pytest.mark.usefixtures("dev_caller")
async def test_unknown_quote_is_a_tool_error():
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("get_order_status", {"quote_id": "nope"})

    assert result.isError
    assert "quote not found" in result.content[0].text


@pytest.mark.usefixtures("dev_caller")
async def test_unknown_argument_is_a_tool_error():
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("build_quote", {"lines": [LINE], "discount": 50})

    assert result.isError
    assert "discount" in result.content[0].text


def _initialize(client: TestClient, path: str):
    return client.post(
        path,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers={"Accept": "application/json, text/event-stream"},
        follow_redirects=False,
    )


@pytest.mark.usefixtures("dev_caller")
def test_mcp_answers_with_and_without_trailing_slash():
    # The session manager runs once per process, so both paths share one lifespan.
    with TestClient(app) as client:
        for path in ("/mcp", "/mcp/"):
            response = _initialize(client, path)
            assert response.status_code == 200, (path, response.status_code)
            assert '"serverInfo"' in response.text


@pytest.mark.usefixtures("no_caller")
def test_mcp_without_caller_is_401():
    assert _initialize(TestClient(app), "/mcp").status_code == 401
