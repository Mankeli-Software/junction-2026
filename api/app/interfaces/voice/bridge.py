"""The tool bridge: the call's agent tools come from our own MCP server (technical-plan.md §7.1).

At call start the relay lists the MCP tools as the caller, with a short-lived phone caller
token, and turns their JSON Schemas into Gemini function declarations. Gemini's tool calls
go back to `/mcp` with the same token, so the phone is just another MCP client (vision §2)
and every call gets MCP's own `tool_called` and `tool_returned` audit events.
"""

import copy
import logging
from collections.abc import Mapping
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Protocol

from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared._httpx_utils import McpHttpClientFactory, create_mcp_http_client
from mcp.types import CallToolResult, TextContent, Tool

from app.agent import END_CALL

log = logging.getLogger(__name__)

TOOL_TIMEOUT = timedelta(seconds=45)

END_CALL_DESCRIPTION = (
    "Hang up the call. Call it after your goodbye, once the confirmation link has been "
    "requested or when the caller says they are done. Never in the middle of an order."
)


class Tools(Protocol):
    """What the relay needs from the MCP server."""

    async def list_tools(self) -> list[Tool]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def inline_refs(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The schema with every local `#/$defs/...` reference replaced by its definition.

    The MCP tool schemas come from Pydantic and use `$ref`; the #53 prompt runs only tried
    self-contained schemas with Gemini, so the declarations get those.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any, seen: tuple[str, ...]) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                if name in seen:
                    raise ValueError(f"recursive schema reference {name}")
                target = walk(copy.deepcopy(defs[name]), (*seen, name))
                rest = {k: walk(v, seen) for k, v in node.items() if k != "$ref"}
                return {**target, **rest}
            return {k: walk(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v, seen) for v in node]
        return node

    return walk(dict(schema), ())


def declaration(tool: Tool) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters_json_schema=inline_refs(tool.inputSchema),
    )


def end_call_declaration() -> types.FunctionDeclaration:
    """The relay's own function next to the MCP tools; not an MCP tool (§7.1)."""
    return types.FunctionDeclaration(
        name=END_CALL,
        description=END_CALL_DESCRIPTION,
        parameters_json_schema={"type": "object", "properties": {}},
    )


def declarations(tools: list[Tool]) -> list[types.FunctionDeclaration]:
    return [declaration(tool) for tool in tools if tool.name != END_CALL] + [end_call_declaration()]


def tool_response(result: CallToolResult) -> dict[str, Any]:
    """An MCP result as a Gemini function response: `{"output": ...}` or `{"error": ...}`."""
    text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
    if result.isError:
        return {"error": text or "the tool failed"}
    if result.structuredContent is not None:
        return {"output": result.structuredContent}
    return {"output": text}


class McpTools:
    """An MCP client session to `/mcp` as one caller. Use it as an async context manager,
    entered and left in the same task."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        http_client_factory: McpHttpClientFactory = create_mcp_http_client,
    ) -> None:
        self.url = url
        self.token = token
        self.http_client_factory = http_client_factory
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "McpTools":
        try:
            read, write, _ = await self._stack.enter_async_context(
                streamablehttp_client(
                    self.url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    httpx_client_factory=self.http_client_factory,
                )
            )
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            await self._stack.aclose()
            raise
        self._session = session
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._session = None
        await self._stack.aclose()

    async def list_tools(self) -> list[Tool]:
        assert self._session is not None
        return (await self._session.list_tools()).tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None
        try:
            result = await self._session.call_tool(
                name, arguments, read_timeout_seconds=TOOL_TIMEOUT
            )
        except Exception as error:  # noqa: BLE001 - the model hears it as a tool error
            log.exception("MCP call %s failed", name)
            return {"error": f"{name} could not be reached: {type(error).__name__}"}
        return tool_response(result)
