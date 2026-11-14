"""The webshop chat agent's parts without a database (#57): catalog, cards, link scan, tool
schemas, actions, show_menu's checks, conversations, and a whole turn with the model and the
MCP tools faked."""

import json
import uuid
from pathlib import Path

import pytest
from genkit import Message, Part, Role
from genkit.model import ToolResponse
from google.genai import types
from pydantic import ValidationError

from app.interfaces.chat import agent, gemini, menus, surfaces
from app.interfaces.chat.conversations import Conversation, ConversationStore, Menu, MenuSlot
from app.interfaces.chat.schemas import ChatRequest
from app.interfaces.voice import bridge
from app.settings import get_settings
from tests import chat_fakes as fx
from tests import voice_fakes as vfx

WEB_CATALOG = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "a2ui" / "catalog.json"


# --- Catalog ---------------------------------------------------------------------------------


def test_the_api_catalog_is_the_web_catalog():
    if not WEB_CATALOG.exists():
        pytest.skip("no web/ next to api/")
    web = json.loads(WEB_CATALOG.read_text(encoding="utf-8"))
    ours = surfaces.catalog()
    assert ours["id"] == web["id"]
    by_name = lambda c: {x["name"]: x for x in c["components"]}  # noqa: E731
    assert by_name(ours) == by_name(web), (
        "api/app/interfaces/chat/catalog.json differs from web/src/lib/a2ui/catalog.json"
    )


def test_every_catalog_component_has_its_props_and_cards_have_ids():
    names = {c["name"] for c in surfaces.catalog()["components"]}
    assert names == set(surfaces.ALLOWED_PROPS)
    for card, prop in surfaces.CARD_ID.items():
        assert prop is None or prop in surfaces.ALLOWED_PROPS[card]


# --- Link scan --------------------------------------------------------------------------------


def test_the_link_never_comes_through_even_split_across_deltas():
    scrubber = surfaces.LinkScrubber()
    deltas = ["Sent! Open ", "http://localhost:51", "73/c/AbC", "dEf123 to confirm", "."]
    out = "".join(scrubber.feed(d) for d in deltas) + scrubber.flush()
    assert "/c/" not in out
    assert "AbC" not in out and "dEf123" not in out
    assert out.startswith("Sent! Open ") and out.endswith("to confirm.")
    assert scrubber.text == "Sent! Open to confirm."


def test_text_without_a_link_streams_unchanged():
    scrubber = surfaces.LinkScrubber()
    out = "".join(scrubber.feed(d) for d in ["Hei, Hassu ", "Hauki Oy!\nMitä ", "saisi olla?"])
    assert out + scrubber.flush() == "Hei, Hassu Hauki Oy!\nMitä saisi olla?"


# --- Cards ------------------------------------------------------------------------------------


def surface(surface_id: str, *components: dict) -> list[dict]:
    return [
        {"createSurface": {"surfaceId": surface_id, "catalogId": surfaces.catalog_id()}},
        {"updateComponents": {"surfaceId": surface_id, "components": list(components)}},
    ]


def test_cards_keep_only_their_ids_and_unknown_components_go():
    cards = surfaces.TurnCards()
    out = cards.filter(
        surface(
            "s1",
            {"id": "root", "component": "Column", "children": ["q", "x", "t"]},
            {"id": "q", "component": "QuoteCard", "quoteId": "q-1", "total": "41,90 €"},
            {"id": "x", "component": "Html", "html": "<script>"},
            {"id": "t", "component": "Text", "text": "Here it is", "price": 4190},
        )
    )
    components = out[1]["updateComponents"]["components"]
    assert components == [
        {"id": "root", "component": "Column", "children": ["q", "t"]},
        {"id": "q", "component": "QuoteCard", "quoteId": "q-1"},
        {"id": "t", "component": "Text", "text": "Here it is"},
    ]


def test_genkits_button_and_heading_variants_become_ours():
    out = surfaces.TurnCards().filter(
        surface(
            "s1",
            {"id": "root", "component": "Column", "children": ["t", "b"]},
            {"id": "t", "component": "Text", "text": "Menu", "variant": "h2"},
            {"id": "b", "component": "Button", "label": "Go", "variant": "primary", "action": {}},
        )
    )
    _, t, b = out[1]["updateComponents"]["components"]
    assert t["variant"] == "heading"
    assert b["primary"] is True and "variant" not in b


def test_a_second_card_for_the_same_id_is_dropped_with_its_surface():
    cards = surfaces.TurnCards()
    first = cards.filter(surface("s1", {"id": "root", "component": "QuoteCard", "quoteId": "q"}))
    again = cards.filter(surface("s2", {"id": "root", "component": "QuoteCard", "quoteId": "q"}))
    other = cards.filter(surface("s3", {"id": "root", "component": "QuoteCard", "quoteId": "q2"}))
    assert len(first) == 2 and again == [] and len(other) == 2


def test_an_envelope_with_the_link_is_dropped():
    cards = surfaces.TurnCards()
    out = cards.filter(
        surface("s1", {"id": "root", "component": "Text", "text": "http://x/c/token"})
    )
    assert out == [surface("s1")[0]] or out == []
    assert not surfaces.has_link(out)


def test_gap_filling_adds_only_what_the_model_did_not_draw():
    cards = surfaces.TurnCards()
    cards.expect("QuoteCard", "q-old", slot="quote")
    cards.expect("QuoteCard", "q-new", slot="quote")  # the latest quote only
    cards.expect("MenuWeek", "m-1")
    cards.expect("SentNotice")
    cards.filter(surface("s1", {"id": "root", "component": "MenuWeek", "menuId": "m-1"}))
    missing = cards.missing()
    roots = [e["updateComponents"]["components"][0] for e in missing if "updateComponents" in e]
    assert roots == [
        {"id": "root", "component": "QuoteCard", "quoteId": "q-new"},
        {"id": "root", "component": "SentNotice"},
    ]
    assert all(e["version"] == "v0.9" for e in missing)
    assert missing[0]["createSurface"]["catalogId"] == surfaces.catalog_id()
    assert cards.missing() == []


# --- Gemini through our own adapter -----------------------------------------------------------


def gemini_response(*parts: types.Part, finish: str | None = None):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=list(parts)),
                finish_reason=finish,
            )
        ]
    )


class FakeGemini:
    """`google-genai`'s streamed generate_content: one list of responses per call."""

    def __init__(self, *calls: list) -> None:
        self.calls = list(calls)
        self.requests: list[tuple[str, list, types.GenerateContentConfig]] = []

    async def __call__(self, model, contents, config):
        self.requests.append((model, contents, config))
        for response in self.calls.pop(0):
            yield response


async def test_mcp_tools_reach_gemini_with_their_whole_schema(fake_turn, monkeypatch):
    model, tools, said = fake_turn
    signature = b"sig-1"
    fake = FakeGemini(
        [
            gemini_response(
                types.Part(
                    function_call=types.FunctionCall(
                        id="call-1", name="build_quote", args={"lines": [{"text": "maito"}]}
                    ),
                    thought_signature=signature,
                )
            )
        ],
        [
            gemini_response(types.Part(text="Total ")),
            gemini_response(types.Part(thought=True, text="(thinking)")),
            gemini_response(types.Part(text="41,90 €."), finish="STOP"),
        ],
    )
    monkeypatch.setattr(gemini, "client_stream", lambda key: fake)
    monkeypatch.setenv("CHAT_MODEL", f"test-gemini-{uuid.uuid4().hex[:6]}")
    get_settings.cache_clear()

    events = await turn(conversation(system_prompt="You are S.I.MO"), "1000 l maitoa")

    assert fx.streamed_text(events) == "Total 41,90 €."
    assert fx.cards(events) == [{"id": "root", "component": "QuoteCard", "quoteId": "q-1"}]
    _, first_contents, config = fake.requests[0]
    assert config.system_instruction.startswith("You are S.I.MO")
    assert "QuoteCard" in config.system_instruction  # the catalog's instructions
    [declared] = [d for d in config.tools[0].function_declarations if d.name == "build_quote"]
    assert declared.parameters_json_schema == bridge.inline_refs(vfx.QUOTE_SCHEMA)
    assert first_contents[0].parts[0].text.startswith("1000 l maitoa")
    # The second call sends the call back with its signature, and the tool's answer.
    _, second_contents, _ = fake.requests[1]
    call, answer = second_contents[-2], second_contents[-1]
    assert call.parts[0].function_call.name == "build_quote"
    assert call.parts[0].thought_signature == signature
    assert answer.parts[0].function_response.response == {
        "output": {"quote_id": "q-1", "decision": "ready", "total_cents": 4190}
    }


def test_genkit_messages_become_gemini_contents():
    system, contents = gemini.to_contents(
        [
            Message(role=Role.SYSTEM, content=[Part.from_text("rules")]),
            Message(role=Role.USER, content=[Part.from_text("hei")]),
            Message(
                role=Role.MODEL,
                content=[
                    Part.from_tool_request(
                        name="get_recipe",
                        input={"recipe_id": "1"},
                        ref="r1",
                        metadata={gemini.SIGNATURE: "c2ln"},
                    )
                ],
            ),
            Message(
                role=Role.TOOL,
                content=[Part(tool_response=ToolResponse(name="get_recipe", ref="r1", output="x"))],
            ),
        ]
    )
    assert system == "rules"
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].thought_signature == b"sig"
    assert contents[2].parts[0].function_response.response == {"output": "x"}


# --- Actions ----------------------------------------------------------------------------------


def conversation(**extra) -> Conversation:
    return Conversation(id="c", user_id=uuid.uuid4(), scope="shop", lang="fi", last_used=0, **extra)


def test_actions_become_plain_sentences():
    conv = conversation()
    conv.menus["m"] = Menu("m", (MenuSlot("mon", "40728", 80), MenuSlot("tue", "123", 80)))

    def say(name, **context):
        return agent.action_sentence({"name": name, "context": context}, conv)

    assert "confirmed recipe draft d-1" in say("recipe_confirmed", draftId="d-1")
    assert "request_confirmation" in say("send_for_confirmation", quoteId="q-1")
    assert "line 2 is product 600" in say(
        "clarification_answered", quoteId="q", lineId="2", productId="600"
    )
    built = say("menu_build", menuId="m")
    assert "mon recipe 40728 for 80" in built and "tue recipe 123 for 80" in built
    assert "no longer known" in say("menu_build", menuId="gone")
    assert "for 120 portions" in say("recipe_confirmed", draftId="d-1", portions=120)
    assert "new draft d-2" in say("recipe_edit_as_new", draftId="d-2", copiedFrom="d-1")
    assert "line 3 of quote q" in say("rejection_next_step", quoteId="q", lineId="3")
    assert say("something_else") == 'The buyer tapped "something_else".'


def test_chat_request_takes_exactly_one_of_message_and_action():
    ChatRequest(message="1000 l maitoa")
    ChatRequest(action={"name": "send_for_confirmation", "context": {"quoteId": "q"}})
    for bad in ({}, {"message": "  "}, {"message": "x", "action": {"name": "a"}}):
        with pytest.raises(ValidationError):
            ChatRequest(**bad)
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 2001)


# --- show_menu --------------------------------------------------------------------------------


def test_show_menu_checks_the_days():
    ok = menus.parse_days(
        {
            "days": [
                {"day": "tue", "recipe_id": "2", "portions": 80},
                {"day": "mon", "recipe_id": "1", "portions": 80.0},
            ]
        }
    )
    assert ok == [MenuSlot("mon", "1", 80), MenuSlot("tue", "2", 80)]
    assert "twice" in menus.parse_days(
        {"days": [{"day": "mon", "recipe_id": "1", "portions": 1}] * 2}
    )
    assert "unknown day" in menus.parse_days(
        {"days": [{"day": "sat", "recipe_id": "1", "portions": 1}]}
    )
    assert "portions" in menus.parse_days(
        {"days": [{"day": "mon", "recipe_id": "1", "portions": 0}]}
    )
    assert "days" in menus.parse_days({})


# --- Conversations ----------------------------------------------------------------------------


def test_conversations_are_kept_per_user_and_dropped_after_idling():
    now = [0.0]
    store = ConversationStore(clock=lambda: now[0], idle_s=1800)
    user, other = uuid.uuid4(), uuid.uuid4()
    conv, new = store.open(user, "shop", None, "fi")
    assert new
    conv.menus["m"] = Menu("m", ())
    now[0] = 1000
    assert store.open(user, "shop", conv.id, "fi") == (conv, False)
    assert store.open(other, "shop", conv.id, "fi")[0] is not conv
    assert store.find_menu(user, "m") is not None and store.find_menu(other, "m") is None
    now[0] = 1000 + 1801
    again, new = store.open(user, "shop", conv.id, "fi")
    assert new and again is not conv
    assert store.find_menu(user, "m") is None


# --- A whole turn, without a database ----------------------------------------------------------


@pytest.fixture
def fake_turn(monkeypatch):
    model = fx.install()
    tools = vfx.FakeTools()
    said: list[tuple[str, str]] = []

    async def record_said(session_id, who, text, lang):
        said.append((who, text))

    monkeypatch.setattr(agent, "open_tools", tools.open)
    monkeypatch.setattr(agent, "record_said", record_said)
    monkeypatch.setenv("CHAT_MODEL", fx.MODEL)
    get_settings.cache_clear()
    yield model, tools, said
    get_settings.cache_clear()


async def turn(conv: Conversation, text: str, mode: agent.ChatMode | None = None) -> list:
    out = []
    async for event in agent.run_turn(
        conv,
        agent.user_message(text),
        session_id=uuid.uuid4(),
        token="t",
        mode=mode or agent.ChatMode(show_menu=False),
    ):
        out.append(event)
    return out


async def test_a_quote_gets_its_card_and_the_link_never_streams(fake_turn):
    model, tools, said = fake_turn
    model.reset(
        fx.call("build_quote", {"lines": [{"text": "maito"}]}),
        fx.text("Total 41,90 €. Send it?"),
    )
    conv = conversation(system_prompt="You are S.I.MO")
    first = await turn(conv, "1000 l maitoa")

    assert [e for e in first if e[0] == "tool"] == [
        ("tool", {"name": "build_quote", "status": "started"}),
        ("tool", {"name": "build_quote", "status": "done"}),
    ]
    assert fx.cards(first) == [{"id": "root", "component": "QuoteCard", "quoteId": "q-1"}]
    assert first[-1] == ("done", {"quote_id": "q-1"})
    assert fx.streamed_text(first) == "Total 41,90 €. Send it?"
    assert said == [("agent", "Total 41,90 €. Send it?")]
    assert model.tool_names() == ["build_quote", "request_confirmation", "get_customer_context"]

    # The model draws the notice itself and writes the link: the notice once, no link.
    model.reset(
        fx.call("request_confirmation", {"quote_id": "q-1"}),
        fx.text(
            "Sent: http://localhost:5173/c/secret-token open it."
            + fx.fence({"id": "root", "component": "SentNotice"})
        ),
    )
    second = await turn(conv, "yes")
    body = json.dumps(second)
    assert "/c/" not in body and "secret-token" not in body
    assert [c["component"] for c in fx.cards(second)] == ["SentNotice"]
    assert "secret-token" not in said[-1][1]
    # The history goes back to the model on the next turn, with the earlier card.
    assert len(conv.history) == 8
    assert model.user_texts(0)[0].startswith("1000 l maitoa")


async def test_a_failed_model_turn_is_an_error_and_keeps_the_history(fake_turn):
    model, tools, said = fake_turn
    model.reset()  # no step: the fake model raises
    conv = conversation(system_prompt="x")
    events = await turn(conv, "hei")
    assert events[-1][0] == "error" and events[-1][1]["code"] == "failed"
    assert conv.history == []


async def test_the_model_only_sees_the_tools_of_its_mode(fake_turn):
    model, tools, said = fake_turn
    model.reset(fx.text("ok"))

    await turn(
        conversation(system_prompt="x"),
        "hei",
        agent.ChatMode(tool_names=frozenset({"build_quote"})),
    )
    assert model.tool_names() == ["build_quote", "show_menu"]
