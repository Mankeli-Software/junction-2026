"""The chat agent's turn (#57, plan §4.A steps 3 to 7): Genkit for Python with the A2UI
`Surfaces` middleware and our catalog, Gemini through our own model adapter (`gemini.py`),
and our own MCP server for the tools.

One turn:

1. The tools come from `/mcp` with the conversation's `web_chat` caller token (the voice
   bridge's `McpTools`), so every call gets MCP's own `tool_called`/`tool_returned` audit
   events and the chat's session, like any other client. `show_menu` is the chat's own.
2. Genkit runs the model and the tool loop and streams the reply. The `Surfaces` middleware
   turns the model's ```a2ui fences into A2UI v0.9 envelopes.
3. Text goes out as `text` events with any confirmation link taken out, envelopes as `a2ui`
   events with only catalog components and ids, tool calls as `tool` events (name and
   status only).
4. At the end, the server adds the cards the tools called for and the model didn't draw,
   writes `agent_said`, and sends `done`.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from genkit import FinishReason, Genkit, Message, Part, Role, Tool
from genkit_a2ui import Surfaces, a2ui_part, envelopes_from_parts, is_a2ui_part, load_catalog_file
from mcp.types import Tool as McpTool

from app.agent import END_CALL
from app.db import get_sessionmaker
from app.interfaces.chat import gemini, menus, surfaces
from app.interfaces.chat.conversations import Conversation
from app.interfaces.voice import bridge
from app.interfaces.voice.text import guess_language
from app.schemas import Localized
from app.services import audit, voice_calls
from app.services.dashboard.redact import redact_text
from app.settings import get_settings

log = logging.getLogger(__name__)

QUOTE_TOOLS = frozenset({"build_quote", "update_quote"})
PROPOSE_RECIPE = "propose_recipe"
REQUEST_CONFIRMATION = "request_confirmation"
# The model loop: tool rounds per turn before Genkit stops it.
MAX_TURNS = 12

Event = tuple[str, dict[str, Any]]
ToolsFactory = Callable[[str], AbstractAsyncContextManager[bridge.Tools]]


def _open_tools(token: str) -> AbstractAsyncContextManager[bridge.Tools]:
    return bridge.McpTools(get_settings().voice_mcp_url, token)


# Swapped out by the tests.
open_tools: ToolsFactory = _open_tools


@cache
def get_ai() -> Genkit:
    """The process's Genkit with our catalog. Models are registered by `chat_model()`."""
    ai = Genkit()
    load_catalog_file(ai, str(surfaces.CATALOG_PATH))
    return ai


_registered_models: set[str] = set()


def chat_model(model_id: str) -> str:
    """The Genkit model name for `CHAT_MODEL`. A Gemini id is registered on first use as
    `gemini/<id>` (`gemini.py`); a name with a slash is taken as already registered (the
    tests' fake model)."""
    if "/" in model_id:
        return model_id
    name = f"gemini/{model_id}"
    if name not in _registered_models:
        stream = gemini.client_stream(get_settings().gemini_api_key)
        get_ai().define_model(name=name, fn=gemini.gemini_model(model_id, stream))
        _registered_models.add(name)
    return name


# --- What a card action means ---------------------------------------------------------------


def _ctx(action: Mapping[str, Any], key: str) -> str:
    value = (action.get("context") or {}).get(key)
    return str(value)[:100] if value is not None else "?"


def action_sentence(action: Mapping[str, Any], conversation: Conversation) -> str:
    """A card's action as a plain sentence the model understands (plan §4.A step 4)."""
    name = str(action.get("name", ""))
    c = lambda key: _ctx(action, key)  # noqa: E731
    match name:
        case "recipe_confirmed":
            portions = (action.get("context") or {}).get("portions")
            at = f" for {c('portions')} portions" if portions is not None else ""
            return (
                f"The buyer confirmed recipe draft {c('draftId')}{at} on the card. Build the "
                "quote from it with build_quote and recipe_draft_id."
            )
        case "recipe_edit_as_new":
            return (
                f"The buyer copied confirmed recipe draft {c('copiedFrom')} into a new draft "
                f"{c('draftId')} to edit it again. The card shows it; wait for recipe_confirmed "
                "before quoting it."
            )
        case "rejection_next_step":
            return (
                f"The buyer tapped the next step of the rejection on line {c('lineId')} of quote "
                f"{c('quoteId')}. Do that next step: usually update_quote without that line or "
                "with the change the rejection suggests."
            )
        case "recipe_discarded":
            return f"The buyer discarded recipe draft {c('draftId')} and wants to start over."
        case "clarification_answered":
            return (
                f"The buyer answered the question on quote {c('quoteId')}: line {c('lineId')} "
                f"is product {c('productId')}. Call update_quote with that product_id."
            )
        case "send_for_confirmation":
            return (
                f"The buyer tapped Send to my phone for quote {c('quoteId')}. That is their yes: "
                "call request_confirmation for it."
            )
        case "recipe_selected":
            return f"The buyer chose recipe {c('recipeId')} for {c('portions')} portions."
        case "recipe_swap":
            return f"The buyer wants another recipe instead of recipe {c('recipeId')}."
        case "menu_swap_day":
            menu = conversation.menus.get(c("menuId"))
            where = f" (the menu is: {menus.describe(menu)})" if menu else ""
            return (
                f"The buyer wants another dish for {c('day')} in menu {c('menuId')}{where}. "
                "Offer one and call show_menu again with the new arrangement."
            )
        case "menu_build":
            menu = conversation.menus.get(c("menuId"))
            if menu is None:
                return f"The buyer wants to order menu {c('menuId')}, which is no longer known."
            return (
                f"The buyer wants to order menu {menu.menu_id}: {menus.describe(menu)}. Build one "
                "quote with one recipe line per day, needed by that weekday."
            )
        case _:
            return f'The buyer tapped "{name[:64]}".'


_DAY_WORDS = {
    "mon": ("maanantaille", "Monday"),
    "tue": ("tiistaille", "Tuesday"),
    "wed": ("keskiviikolle", "Wednesday"),
    "thu": ("torstaille", "Thursday"),
    "fri": ("perjantaille", "Friday"),
}


def action_plain(action: Mapping[str, Any], lang: str) -> str:
    """The action as the buyer's turn in the audit log (public on the dashboard): a short
    plain sentence in the conversation's language, with no ids."""
    name = str(action.get("name", ""))
    context = action.get("context") or {}
    portions = context.get("portions")
    count = int(portions) if isinstance(portions, int | float) and 0 < portions <= 1000 else None
    day = _DAY_WORDS.get(str(context.get("day")), ("toiselle päivälle", "another day"))
    texts: dict[str, tuple[str, str]] = {
        "recipe_confirmed": (
            f"Vahvistin reseptin{f' {count} annokselle' if count else ''}.",
            f"I confirmed the recipe{f' for {count} portions' if count else ''}.",
        ),
        "recipe_discarded": ("Aloitan reseptin alusta.", "I'm starting the recipe over."),
        "recipe_edit_as_new": (
            "Muokkaan vahvistettua reseptiä uutena luonnoksena.",
            "I'm editing the confirmed recipe as a new draft.",
        ),
        "clarification_answered": ("Valitsin vaihtoehdon.", "I picked an option."),
        "send_for_confirmation": ("Lähetä puhelimeeni.", "Send it to my phone."),
        "recipe_selected": (
            f"Valitsin tämän reseptin{f' {count} annokselle' if count else ''}.",
            f"I'll take this recipe{f' for {count} portions' if count else ''}.",
        ),
        "recipe_swap": ("Haluan toisen reseptin.", "I'd like another recipe."),
        "menu_swap_day": (f"Vaihda ruoka {day[0]}.", f"Swap the dish for {day[1]}."),
        "menu_build": ("Tee tilaus tästä menusta.", "Build the order from this menu."),
        "rejection_next_step": ("Tehdään ehdotettu seuraava vaihe.", "Let's do the next step."),
    }
    fi, en = texts.get(name, (f"Napautin: {name[:64]}", f"I tapped: {name[:64]}"))
    return fi if lang == "fi" else en


# --- One turn -------------------------------------------------------------------------------


@dataclass
class ChatMode:
    """What a turn may do. The webshop chat has every agent tool, `show_menu` and the domain
    cards. The confirmation page's chat has only `update_quote`, answered by the page's own
    edit path, and text only: no domain cards."""

    tool_names: frozenset[str] | None = None  # None: every agent tool
    show_menu: bool = True
    # Tools the chat answers itself instead of /mcp, with their own tool_called and
    # tool_returned events.
    local: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = field(
        default_factory=dict
    )
    cards: bool = True


@dataclass
class Turn:
    conversation: Conversation
    session_id: uuid.UUID
    mode: ChatMode
    tools: bridge.Tools | None = None
    cards: surfaces.TurnCards = field(default_factory=surfaces.TurnCards)
    queue: asyncio.Queue[Event | None] = field(default_factory=asyncio.Queue)

    async def call(self, name: str, arguments: Any) -> dict[str, Any]:
        args = dict(arguments) if isinstance(arguments, Mapping) else {}
        self.queue.put_nowait(("tool", {"name": name, "status": "started"}))
        try:
            if name == menus.SHOW_MENU:
                response = await self._show_menu(args)
            elif name in self.mode.local:
                response = await self.mode.local[name](args)
                async with get_sessionmaker()() as db:
                    await voice_calls.record_local_tool(db, self.session_id, name, args, response)
                    await db.commit()
            else:
                assert self.tools is not None
                response = await self.tools.call_tool(name, args)
            await self._note(name, response)
        finally:
            self.queue.put_nowait(("tool", {"name": name, "status": "done"}))
        return response

    async def _note(self, name: str, response: dict[str, Any]) -> None:
        output = response.get("output")
        if not isinstance(output, dict):
            return
        if name in QUOTE_TOOLS and output.get("quote_id"):
            quote_id = str(output["quote_id"])
            self.conversation.latest_quote_id = quote_id
            self.cards.expect("QuoteCard", quote_id, slot="quote")
        elif name == PROPOSE_RECIPE and output.get("draft_id"):
            self.cards.expect("RecipeDraftCard", str(output["draft_id"]))
        elif name == REQUEST_CONFIRMATION:
            self.cards.expect("SentNotice")
        elif name == menus.SHOW_MENU and output.get("menu_id"):
            self.cards.expect("MenuWeek", str(output["menu_id"]))

    async def _show_menu(self, args: dict[str, Any]) -> dict[str, Any]:
        async with get_sessionmaker()() as db:
            menu, response = await menus.show_menu(db, args)
            await voice_calls.record_local_tool(
                db, self.session_id, menus.SHOW_MENU, args, response
            )
            await db.commit()
        if menu is not None:
            self.conversation.menus[menu.menu_id] = menu
        return response


def genkit_tool(turn: Turn, name: str, description: str, schema: dict[str, Any]) -> Tool:
    async def run(arguments: Any) -> Any:
        return await turn.call(name, arguments)

    return Tool(run, name=name, description=description, input_schema=schema)


def chat_tools(turn: Turn, listed: list[McpTool]) -> list[Tool]:
    """The MCP tools this chat may use as Genkit tools, then `show_menu`."""
    allowed = turn.mode.tool_names
    out = [
        genkit_tool(turn, t.name, t.description or "", bridge.inline_refs(t.inputSchema))
        for t in listed
        if t.name != END_CALL and (allowed is None or t.name in allowed)
    ]
    if turn.mode.show_menu:
        out.append(
            genkit_tool(turn, menus.SHOW_MENU, menus.SHOW_MENU_DESCRIPTION, menus.SHOW_MENU_SCHEMA)
        )
    return out


def user_message(text: str, action: Mapping[str, Any] | None = None) -> Message:
    """The buyer's turn: the text, and for a card action the action as an A2UI data part."""
    content = [Part.from_text(text)]
    if action is not None:
        content.append(a2ui_part([{"action": dict(action)}]))
    return Message(role=Role.USER, content=content)


async def record_said(session_id: uuid.UUID, who: str, text: str, lang: str | None) -> None:
    """`buyer_said` or `agent_said` for a chat turn: `{text, lang, transcript: false}`, with
    phone numbers and emails masked, like the phone's transcripts."""
    text = redact_text(text)
    if not text:
        return
    buyer = who == "buyer"
    async with get_sessionmaker()() as db:
        await audit.record(
            db,
            type="buyer_said" if buyer else "agent_said",
            actor="buyer" if buyer else "agent",
            session_id=session_id,
            payload={"text": text, "lang": lang, "transcript": False},
            text=Localized(fi=text, en=text),
        )
        await db.commit()


def turn_language(conversation: Conversation, text: str) -> str:
    lang = guess_language(text)
    if lang:
        conversation.lang = lang
    return conversation.lang


async def run_turn(
    conversation: Conversation,
    message: Message,
    *,
    session_id: uuid.UUID,
    token: str,
    mode: ChatMode,
    expect_draft: str | None = None,
) -> AsyncIterator[Event]:
    """The turn's `text`, `a2ui` and `tool` events, then `done` or `error`."""
    settings = get_settings()
    turn = Turn(
        conversation=conversation,
        session_id=session_id,
        mode=mode,
        cards=surfaces.TurnCards(domain=mode.cards),
    )
    if expect_draft:
        turn.cards.expect("RecipeDraftCard", expect_draft)
    scrubber = surfaces.LinkScrubber()
    failed = False

    async with open_tools(token) as tools:
        turn.tools = tools
        result = get_ai().generate_stream(
            model=chat_model(settings.chat_model),
            system=conversation.system_prompt
            + ("" if mode.cards else "\n\n" + surfaces.text_only_instructions()),
            messages=[*conversation.history, message],
            tools=chat_tools(turn, await tools.list_tools()),
            # Text only: our reduced instructions instead of the whole catalog's.
            use=[
                Surfaces(
                    catalog=surfaces.catalog_id(),
                    instructions="system" if mode.cards else "none",
                )
            ],
            max_turns=MAX_TURNS,
        )

        async def pump() -> None:
            try:
                async for chunk in result.stream:
                    turn.queue.put_nowait(("chunk", {"chunk": chunk}))
            finally:
                turn.queue.put_nowait(None)

        pumping = asyncio.create_task(pump())
        try:
            while (item := await turn.queue.get()) is not None:
                kind, data = item
                if kind != "chunk":
                    yield kind, data
                    continue
                chunk = data["chunk"]
                if chunk.role not in (Role.MODEL, None, "model"):
                    continue
                for part in chunk.content or []:
                    if is_a2ui_part(part):
                        envelopes = turn.cards.filter(envelopes_from_parts([part]))
                        if envelopes:
                            yield "a2ui", {"envelopes": envelopes}
                    elif part.text:
                        delta = scrubber.feed(part.text)
                        if delta:
                            yield "text", {"delta": delta}
            final = await result.response
        finally:
            if not pumping.done():
                pumping.cancel()
                await result.aclose()
            await asyncio.gather(pumping, return_exceptions=True)

    if final.finish_reason == FinishReason.FAILED or final.message is None:
        log.error("Chat turn failed: %s", final.error)
        failed = True
    else:
        conversation.history = [m for m in final.messages if m.role != Role.SYSTEM]

    tail = scrubber.flush()
    if tail:
        yield "text", {"delta": tail}
    missing = turn.cards.missing()
    if missing:
        yield "a2ui", {"envelopes": missing}
        if not failed and conversation.history:
            last = conversation.history[-1]
            conversation.history[-1] = last.model_copy(
                update={"content": [*last.content, a2ui_part(missing)]}
            )
    if scrubber.text:
        await record_said(session_id, "agent", scrubber.text, conversation.lang)
    if failed:
        yield "error", {"code": "failed", "message": "S.I.MO could not answer. Try again."}
        return
    yield "done", {"quote_id": conversation.latest_quote_id}
