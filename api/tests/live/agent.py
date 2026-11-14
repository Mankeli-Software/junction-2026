"""The agent's side of a test script: tool calls over an MCP session, and reading a quote.

Nothing here knows where the server is. The live tests (#98) hand in a session over
streamable HTTP with a bearer token; an offline test hands in an in-memory one
(`mcp.shared.memory.create_connected_server_and_client_session(mcp)`), so the same script
runs in the regular suite against fixtures (#105).
"""

import re
from collections.abc import Callable
from typing import Any

from mcp import ClientSession
from mcp.types import TextContent


class ToolFailed(Exception):
    """The tool answered with an error (`isError`), as the model would hear it."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message


class Agent:
    """Calls the tools like an outside agent and keeps what it called, in order."""

    def __init__(
        self, session: ClientSession, *, on_call: Callable[[str], None] | None = None
    ) -> None:
        self.session = session
        self.on_call = on_call
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def tool_names(self) -> set[str]:
        return {tool.name for tool in (await self.session.list_tools()).tools}

    async def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        """The tool's structured result, or ToolFailed."""
        self.calls.append((name, arguments))
        if self.on_call is not None:
            self.on_call(name)
        result = await self.session.call_tool(name, arguments)
        if result.isError:
            text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
            raise ToolFailed(name, text or "the tool failed")
        return result.structuredContent or {}


# --- Reading a quote ------------------------------------------------------------------


def euros(cents: int | None) -> str:
    return "-" if cents is None else f"{cents / 100:.2f} €"


def describe_quote(quote: dict[str, Any], lang: str = "fi") -> str:
    """A quote in a few lines, as S.I.MO would have it in front of it."""
    out = [
        f"  quote {quote.get('quote_id', '?')[:8]} v{quote.get('version', '?')}: "
        f"{quote['decision']}, {euros(quote.get('total_cents'))}"
    ]
    for line in quote.get("lines", []):
        asked = line["asked"]
        words = asked.get("text") or "(by product or recipe)"
        out.append(
            f"    {line['line_id']}: {asked['quantity']} {asked['unit']} {words} -> "
            f"{line['quantity_sales_units']} x {line['name'][lang]} "
            f"[{line['product_id']}], {euros(line['line_total_cents'])}, "
            f"{line['delivery_date']}, {line['stock_status']}"
        )
    for flag in quote.get("flags", []):
        out.append(f"    flag {flag['code']} {flag['line_ids']}: {flag['text'][lang]}")
    if clarification := quote.get("clarification"):
        options = ", ".join(o["label"][lang] for o in clarification["options"])
        out.append(
            f"    asks ({clarification['line_id']}): {clarification['question'][lang]} [{options}]"
        )
    for rejection in quote.get("rejections", []):
        out.append(
            f"    rejected {rejection['line_id']} {rejection['reason_code']}: "
            f"{rejection['text'][lang]} Next: {rejection['next_step'][lang]}"
        )
    if not_ordered := quote.get("not_ordered"):
        out.append("    not ordered: " + ", ".join(n["name"] for n in not_ordered))
    if speak := quote.get("speak"):
        out.append(f"    says: {speak[lang]}")
    return "\n".join(out)


# A rough reading of product names, for kitchens that exclude milk. The engine decides on
# allergen data; this only catches a milk product by its name, so a person reads the
# printed lines too.
DAIRY = re.compile(
    r"maito|maido|milk|voi\b|butter|juusto|cheese|kerma|cream|jogurt|yogh?urt|rahka|piimä",
    re.IGNORECASE,
)
PLANT_BASED = re.compile(
    r"kaura|oat|soija|soy|kasvi|vegaan|vegan|maidoton|milk[- ]free|kookos|coconut|manteli|"
    r"almond|herne|pea\b|riisi|rice",
    re.IGNORECASE,
)


def dairy_lines(quote: dict[str, Any]) -> list[str]:
    """Names of quoted products that read as milk products and not as plant-based ones."""
    names = [f"{line['name']['fi']} / {line['name']['en']}" for line in quote.get("lines", [])]
    return [name for name in names if DAIRY.search(name) and not PLANT_BASED.search(name)]


def dead_ends(quote: dict[str, Any]) -> list[str]:
    """Rejections that give the buyer no next step (vision: never a dead end)."""
    return [
        f"{r['line_id']} {r['reason_code']}"
        for r in quote.get("rejections", [])
        if not (r["next_step"]["fi"].strip() and r["next_step"]["en"].strip())
    ]
