"""Writes the contract files the web app builds on (#56), so the webshop can't drift.

- `web/src/lib/generated/agent-tools.json`: the agent tools exactly as `/mcp` lists them
  (name, description, input schema), each with its REST twin's method and path. The
  webshop registers these as its WebMCP tools and calls the twins with the session cookie.
- `web/src/lib/generated/openapi.json`: the OpenAPI document of `/api/v1`, from which
  `pnpm gen:api-types` in `web/` generates the TypeScript types (`openapi-typescript`).

Run after changing a tool, its description or any API schema:

    uv run python -m app.interfaces.web_contract

`tests/test_web_contract.py` fails while the committed files are out of date.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from app.interfaces.mcp.server import mcp
from app.interfaces.rest import tools as rest_tools
from app.main import app

WEB_GENERATED = Path(__file__).resolve().parents[3] / "web" / "src" / "lib" / "generated"
TOOLS_FILE = WEB_GENERATED / "agent-tools.json"
OPENAPI_FILE = WEB_GENERATED / "openapi.json"

# Where app.main mounts the REST twins.
REST_PREFIX = "/api/v1"


def _rest_twins() -> dict[str, dict[str, str]]:
    """Method and path of each REST twin, keyed by its route function's name (the tool's)."""
    twins: dict[str, dict[str, str]] = {}
    for route in rest_tools.router.routes:
        if isinstance(route, APIRoute):
            (method,) = route.methods
            twins[route.endpoint.__name__] = {"method": method, "path": REST_PREFIX + route.path}
    return twins


def agent_tools() -> list[dict[str, Any]]:
    """The tools `/mcp` lists, in its order, each with its REST twin."""
    twins = _rest_twins()
    tools = asyncio.run(mcp.list_tools())
    missing = [tool.name for tool in tools if tool.name not in twins]
    if missing:
        raise RuntimeError(f"agent tools without a REST twin: {missing}")
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "rest": twins[tool.name],
        }
        for tool in tools
    ]


def openapi() -> dict[str, Any]:
    return app.openapi()


def render(data: Any) -> str:
    return json.dumps(data, indent="\t", ensure_ascii=False) + "\n"


def expected() -> dict[Path, str]:
    return {TOOLS_FILE: render(agent_tools()), OPENAPI_FILE: render(openapi())}


def main() -> None:
    WEB_GENERATED.mkdir(parents=True, exist_ok=True)
    for path, content in expected().items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")
    print("Now run `pnpm gen:api-types` in web/ to update the TypeScript types.")


if __name__ == "__main__":
    main()
