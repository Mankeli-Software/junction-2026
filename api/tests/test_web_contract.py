"""The webshop's WebMCP tools and API types come from files generated here (#56)."""

import json

import pytest

from app.agent.prompt import AGENT_TOOLS
from app.interfaces import web_contract

REGENERATE = "out of date: run `uv run python -m app.interfaces.web_contract` in api/"


@pytest.mark.parametrize("path", [web_contract.TOOLS_FILE, web_contract.OPENAPI_FILE])
def test_generated_file_is_up_to_date(path):
    expected = web_contract.expected()[path]
    assert path.exists(), f"{path.name} is missing: {REGENERATE}"
    assert path.read_text(encoding="utf-8") == expected, f"{path.name} is {REGENERATE}"


def test_tools_are_exactly_the_agent_tools():
    tools = json.loads(web_contract.TOOLS_FILE.read_text(encoding="utf-8"))
    assert [tool["name"] for tool in tools] == list(AGENT_TOOLS)


def test_each_rest_twin_is_in_the_openapi_document():
    tools = json.loads(web_contract.TOOLS_FILE.read_text(encoding="utf-8"))
    paths = json.loads(web_contract.OPENAPI_FILE.read_text(encoding="utf-8"))["paths"]
    for tool in tools:
        rest = tool["rest"]
        assert rest["method"].lower() in paths[rest["path"]], tool["name"]
