"""The webshop chat over HTTP (#57), with the model faked and the tools going through the
real `/mcp` as a `web_chat` caller. Needs DATABASE_URL."""

import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.interfaces.chat import agent
from app.interfaces.chat.conversations import store
from app.interfaces.voice.bridge import McpTools
from app.main import app
from app.models import AuditEvent, OrderSession, Quote
from app.settings import get_settings
from tests import chat_fakes as fx
from tests.phones import new_number
from tests.test_confirmation_page import Page
from tests.test_recipe_drafts import PROPOSAL

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


def asgi_client(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
    """The chat's MCP client, talking to this app in process (live_client runs its lifespan)."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
        headers=headers,
        timeout=timeout,
        auth=auth,
    )


@pytest.fixture
def chat(live_client: TestClient, app_db: AsyncEngine, no_caller, monkeypatch):
    model = fx.install()
    monkeypatch.setenv("CHAT_MODEL", fx.MODEL)
    get_settings.cache_clear()
    monkeypatch.setattr(
        agent,
        "open_tools",
        lambda token: McpTools("http://localhost/mcp", token, http_client_factory=asgi_client),
    )
    store.clear()
    live_client.cookies.clear()
    sign_in(live_client)
    yield model
    live_client.cookies.clear()
    store.clear()
    get_settings.cache_clear()


def sign_in(client: TestClient, lang: str = "en") -> None:
    phone = new_number()  # never a vegan catering number: these orders are milk
    response = client.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": lang}
    )
    assert response.status_code == 201, response.text
    # The orders here are milk: a kitchen with an exclusion (a vegan catering number gets
    # Vegan by default, #81) would refuse them.
    assert response.json()["exclusions"] == [], response.json()


def send(client: TestClient, url: str = "/api/v1/chat", **body) -> list:
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    pairs = fx.events(response.text)
    assert pairs[0][0] == "start"
    return pairs


async def session_events(engine: AsyncEngine, session_id) -> list[AuditEvent]:
    async with AsyncSession(engine) as db:
        return list(
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.session_id == session_id)
                .order_by(AuditEvent.seq)
            )
        )


async def quote_session(engine: AsyncEngine, quote_id: str) -> OrderSession:
    async with AsyncSession(engine) as db:
        quote = await db.get_one(Quote, uuid.UUID(quote_id))
        return await db.get_one(OrderSession, quote.session_id)


async def test_a_text_order_gives_a_quote_card_and_audits_the_turns(chat, live_client, app_db):
    chat.reset(
        fx.call("build_quote", {"lines": [LINE]}),
        fx.text("Your quote is ready. Shall I send it to your phone?"),
    )

    pairs = send(live_client, message="20 l maitoa maanantaiksi")

    tools = [d for k, d in pairs if k == "tool"]
    assert tools == [
        {"name": "build_quote", "status": "started"},
        {"name": "build_quote", "status": "done"},
    ]
    kind, done = pairs[-1]
    assert kind == "done" and done["quote_id"]
    assert fx.cards(pairs) == [
        {"id": "root", "component": "QuoteCard", "quoteId": done["quote_id"]}
    ]
    assert fx.streamed_text(pairs) == "Your quote is ready. Shall I send it to your phone?"
    # The page loads the card's quote with the same cookie.
    assert live_client.get(f"/api/v1/quotes/{done['quote_id']}").status_code == 200

    # The tool went through /mcp as the chat: its own session and dashboard client.
    session = await quote_session(app_db, done["quote_id"])
    assert (session.channel, session.client_name) == ("web_chat", "S.I.MO chat")
    events = await session_events(app_db, session.id)
    types = [e.type for e in events]
    assert types.index("buyer_said") < types.index("tool_called") < types.index("tool_returned")
    assert types[-1] == "agent_said"
    buyer = next(e for e in events if e.type == "buyer_said")
    agent_said = events[-1]
    assert buyer.payload == {"text": "20 l maitoa maanantaiksi", "lang": "fi", "transcript": False}
    assert agent_said.payload["text"] == "Your quote is ready. Shall I send it to your phone?"
    assert agent_said.payload["transcript"] is False


async def test_send_to_my_phone_gives_the_notice_and_never_the_link(chat, live_client, app_db):
    built = live_client.post("/api/v1/quotes", json={"lines": [LINE]}).json()
    quote_id = built["quote_id"]
    chat.reset(
        fx.call("request_confirmation", {"quote_id": quote_id}),
        fx.text("Sent! Open http://localhost:5173/c/AbCdEf123 on your phone to confirm."),
    )

    response = live_client.post(
        "/api/v1/chat",
        json={
            "action": {
                "name": "send_for_confirmation",
                "surfaceId": "s1",
                "sourceComponentId": "send",
                "timestamp": "2026-11-14T10:00:00Z",
                "context": {"quoteId": quote_id},
            }
        },
    )

    assert "/c/" not in response.text and "AbCdEf123" not in response.text
    pairs = fx.events(response.text)
    assert [c["component"] for c in fx.cards(pairs)] == ["SentNotice"]
    assert "request_confirmation" in chat.user_texts(0)[-1]
    # The link went to this browser's inbox; the notice has no real SMS while Twilio is off.
    [message] = live_client.get("/api/v1/private/inbox").json()
    assert "/c/" in message["link"]
    sent = live_client.get("/api/v1/chat/sent/latest").json()
    assert sent["delivery_status"] == "off" and sent["inbox"] is True
    assert (sent["status"], sent["order_number"]) == ("waiting", None)
    assert "*" in sent["sent_to_masked"]
    async with AsyncSession(app_db) as db:
        said = list(await db.scalars(select(AuditEvent).where(AuditEvent.type == "agent_said")))
    assert said and all("/c/" not in e.payload["text"] for e in said)
    assert said[-1].payload["text"] == "Sent! Open on your phone to confirm."


async def test_show_menu_rejects_unknown_recipes_and_serves_the_menu(
    chat, live_client, app_db, recipes
):
    async with AsyncSession(app_db) as db:
        ids = [str(i) for i in (await db.scalars(text("SELECT id FROM recipes LIMIT 2"))).all()]
    days = [
        {"day": "mon", "recipe_id": ids[0], "portions": 80},
        {"day": "tue", "recipe_id": ids[1], "portions": 80},
    ]
    chat.reset(
        fx.call("show_menu", {"days": [{"day": "mon", "recipe_id": "999999", "portions": 80}]}),
        fx.call("show_menu", {"days": days}),
        fx.text("Here is a menu for next week."),
    )

    pairs = send(live_client, message="Plan a lunch menu for next week, 80 people")

    [rejected] = chat.tool_results(1)
    assert "unknown recipe ids" in rejected["error"] and "999999" in rejected["error"]
    [card] = fx.cards(pairs)
    assert card["component"] == "MenuWeek"
    menu = live_client.get(f"/api/v1/chat/menus/{card['menuId']}")
    assert menu.status_code == 200, menu.text
    body = menu.json()
    assert [d["day"] for d in body["days"]] == ["mon", "tue"]
    assert [d["recipe_id"] for d in body["days"]] == ids
    assert all(d["name"] and d["portions"] == 80 for d in body["days"])
    assert all(d["ingredient_count"] >= d["linked_count"] >= 0 for d in body["days"])

    # Another browser can't read it.
    other = TestClient(app)
    sign_in(other)
    assert other.get(f"/api/v1/chat/menus/{card['menuId']}").status_code == 404

    # Building the order from the card names the days for the model.
    chat.reset(fx.text("Building it."))
    send(
        live_client,
        conversation_id=pairs[0][1]["conversation_id"],
        action={"name": "menu_build", "context": {"menuId": card["menuId"]}},
    )
    assert f"mon recipe {ids[0]} for 80" in chat.user_texts(0)[-1]


async def test_the_conversation_survives_messages_and_is_dropped_after_idling(
    chat, live_client, monkeypatch
):
    chat.reset(fx.text("Hi! What can I get you?"))
    first = send(live_client, message="hello")
    conversation_id = first[0][1]["conversation_id"]

    chat.reset(fx.text("Got it."))
    second = send(live_client, conversation_id=conversation_id, message="20 l milk")
    assert second[0][1]["conversation_id"] == conversation_id
    assert chat.user_texts(0) == ["hello", "20 l milk"]

    clock = store.clock
    monkeypatch.setattr(store, "clock", lambda: clock() + timedelta(minutes=31).total_seconds())
    chat.reset(fx.text("Hi again!"))
    third = send(live_client, conversation_id=conversation_id, message="still there?")
    assert third[0][1]["conversation_id"] != conversation_id
    assert chat.user_texts(0) == ["still there?"]


async def test_one_message_at_a_time(chat, live_client):
    chat.reset(fx.text("Hi!"))
    conversation_id = send(live_client, message="hello")[0][1]["conversation_id"]
    [conversation] = [c for c in store._items.values() if c.id == conversation_id]
    conversation.busy = True
    response = live_client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conversation_id,
            "message": "again",
            "action": None,
            "attachment_draft_id": None,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "busy"
    conversation.busy = False


async def test_the_confirmation_page_chat_can_only_update_the_links_quote(
    chat, live_client, app_db
):
    built = live_client.post("/api/v1/quotes", json={"lines": [LINE]}).json()
    live_client.post(f"/api/v1/quotes/{built['quote_id']}/confirmation-request")
    [message] = live_client.get("/api/v1/private/inbox").json()
    token = message["link"].rsplit("/c/", 1)[1]
    page = TestClient(app)  # the page's server: no cookie, the link is the authorisation

    def update(request):
        assert [t.name for t in request.tools] == ["update_quote"]
        return fx.call(
            "update_quote", {"quote_id": "not-this-one", "lines": [{**LINE, "quantity": 30}]}
        )

    drawn = fx.fence(
        {"id": "root", "component": "Column", "children": ["q", "t"]},
        {"id": "q", "component": "QuoteCard", "quoteId": "anything"},
        {"id": "t", "component": "Text", "text": "Changed."},
    )
    chat.reset(update, fx.text("Done: 30 litres now." + drawn))

    pairs = send(page, f"/api/v1/confirmations/{token}/chat", message="Make it 30 litres")

    done = pairs[-1][1]
    assert done["quote_id"] and done["quote_id"] != built["quote_id"]
    # Text only: no domain card is offered, drawn or added.
    assert [c["component"] for c in fx.cards(pairs)] == ["Column", "Text"]
    system = "".join(p.text or "" for p in chat.requests[0].messages[0].content)
    assert built["quote_id"] in system and '"maito"' in system
    assert "Notice" in system and "QuoteCard" not in system and "RecipeDraftCard" not in system
    view = page.get(f"/api/v1/confirmations/{token}").json()
    assert view["state"] == "ready"
    assert view["quote"]["quote_id"] == done["quote_id"]
    session = await quote_session(app_db, done["quote_id"])
    assert session.state == "link_opened"

    assert page.post("/api/v1/confirmations/unknown/chat", json={"message": "x"}).status_code == 404


async def test_the_confirmation_page_chat_changes_one_line_and_keeps_the_others(
    chat, live_client, app_db
):
    arla = {**LINE, "line_id": "l2", "text": "arla", "quantity": 5}
    built = live_client.post("/api/v1/quotes", json={"lines": [LINE, arla]}).json()
    live_client.post(f"/api/v1/quotes/{built['quote_id']}/confirmation-request")
    token = live_client.get("/api/v1/private/inbox").json()[-1]["link"].rsplit("/c/", 1)[1]
    page = TestClient(app)

    # Only the changed line is sent (#101): the milk is not, and stays.
    chat.reset(
        lambda request: fx.call("update_quote", {"lines": [{**arla, "quantity": 7}]}),
        fx.text("Seven litres now."),
    )
    send(page, f"/api/v1/confirmations/{token}/chat", message="Make the Arla 7 litres")
    view = page.get(f"/api/v1/confirmations/{token}").json()
    assert [(ln["line_id"], ln["quantity_sales_units"]) for ln in view["lines"]] == [
        (LINE["line_id"], LINE["quantity"]),
        ("l2", 7),
    ]

    chat.reset(
        lambda request: fx.call("update_quote", {"remove_line_ids": ["l2"]}),
        fx.text("Removed."),
    )
    send(page, f"/api/v1/confirmations/{token}/chat", message="Drop the Arla")
    view = page.get(f"/api/v1/confirmations/{token}").json()
    assert [ln["line_id"] for ln in view["lines"]] == [LINE["line_id"]]


@pytest.mark.usefixtures("app_db", "no_caller")
def test_the_chat_takes_the_cookie_and_a_model(monkeypatch):
    client = TestClient(app)
    sign_in(client)
    assert client.get("/api/v1/chat/sent/latest").status_code == 404
    client = TestClient(app)
    assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 401
    sign_in(client)
    monkeypatch.setenv("CHAT_MODEL", "")
    get_settings.cache_clear()
    response = client.post("/api/v1/chat", json={"message": "hi"})
    assert response.status_code == 503
    assert response.json() == {"detail": "chat not configured"}
    assert (
        client.post("/api/v1/chat", json={"message": "hi", "action": {"name": "x"}}).status_code
        == 422
    )
    get_settings.cache_clear()


async def confirmation_link(client: TestClient) -> tuple[dict, str]:
    built = client.post("/api/v1/quotes", json={"lines": [LINE]}).json()
    client.post(f"/api/v1/quotes/{built['quote_id']}/confirmation-request")
    [message] = client.get("/api/v1/private/inbox").json()
    return built, message["link"].rsplit("/c/", 1)[1]


async def test_the_confirmation_page_chat_refuses_a_change_that_needs_a_question(
    chat, live_client, app_db
):
    built, token = await confirmation_link(live_client)
    page = TestClient(app)
    chat.reset(
        fx.call(
            "update_quote", {"quote_id": built["quote_id"], "lines": [{**LINE, "text": "zzz"}]}
        ),
        fx.text("Which product did you mean?"),
    )

    pairs = send(page, f"/api/v1/confirmations/{token}/chat", message="Make it zzz")

    [result] = chat.tool_results(1)
    assert result["error"].startswith("Not changed")
    assert "Ask the buyer this question in words" in result["error"]
    assert pairs[-1] == ("done", {"quote_id": built["quote_id"]})
    view = page.get(f"/api/v1/confirmations/{token}").json()
    assert view["state"] == "ready" and view["quote"]["quote_id"] == built["quote_id"]
    async with AsyncSession(app_db) as db:
        children = (
            await db.scalars(
                select(Quote).where(Quote.parent_quote_id == uuid.UUID(built["quote_id"]))
            )
        ).all()
        original = await db.get_one(Quote, uuid.UUID(built["quote_id"]))
    assert children == [] and original.status == "pending_confirmation"
    # The refused call is still in the log, as the chat's own tool call.
    session = await quote_session(app_db, built["quote_id"])
    types = [e.type for e in await session_events(app_db, session.id)]
    assert "tool_called" in types and "tool_returned" in types


async def test_a_recipe_photo_turn_shows_its_draft_card(chat, live_client, app_db):
    proposed = live_client.post("/api/v1/recipe-drafts", json=PROPOSAL)
    assert proposed.status_code == 200, proposed.text
    draft_id = proposed.json()["draft_id"]
    chat.reset(fx.text("I read your recipe. Check it and confirm."))

    pairs = send(
        live_client,
        conversation_id=None,
        message="Here is my recipe",
        action=None,
        attachment_draft_id=draft_id,
    )

    assert fx.cards(pairs) == [{"id": "root", "component": "RecipeDraftCard", "draftId": draft_id}]
    assert f"recipe draft {draft_id}" in chat.user_texts(0)[-1]
    assert pairs[-1][0] == "done"

    # Another user's draft is refused.
    other = TestClient(app)
    sign_in(other)
    other_draft = other.post("/api/v1/recipe-drafts", json=PROPOSAL).json()["draft_id"]
    refused = send(live_client, message="mine?", attachment_draft_id=other_draft)
    assert refused[-1][0] == "error"


async def test_an_action_is_logged_in_plain_words(chat, live_client, app_db):
    chat.reset(fx.text("Ok."))
    send(
        live_client,
        action={"name": "recipe_confirmed", "context": {"draftId": "d-1", "portions": 80}},
    )
    async with AsyncSession(app_db) as db:
        [said] = (await db.scalars(select(AuditEvent).where(AuditEvent.type == "buyer_said"))).all()
    assert said.payload["text"] == "I confirmed the recipe for 80 portions."
    assert "d-1" not in said.payload["text"]


# --- After the order is confirmed or cancelled on the phone ------------------------------


def system_text(model: fx.FakeModel, index: int = 0) -> str:
    return "".join(p.text or "" for p in model.requests[index].messages[0].content)


def chat_quote_and_send(chat, client: TestClient) -> tuple[str, str, str]:
    """A quote built in the chat and sent to the phone from it. Returns the conversation
    id, the quote id and the link's token."""
    chat.reset(fx.call("build_quote", {"lines": [LINE]}), fx.text("Here it is."))
    first = send(client, message="20 l maitoa")
    conversation_id, quote_id = first[0][1]["conversation_id"], first[-1][1]["quote_id"]
    chat.reset(fx.call("request_confirmation", {"quote_id": quote_id}), fx.text("Sent."))
    sent = send(
        client,
        conversation_id=conversation_id,
        action={"name": "send_for_confirmation", "context": {"quoteId": quote_id}},
    )
    assert sent[-1] == ("done", {"quote_id": quote_id})  # waiting on the phone: still open
    [message] = client.get("/api/v1/private/inbox").json()
    return conversation_id, quote_id, message["link"].rsplit("/c/", 1)[1]


def confirm_on_the_phone(token: str) -> str:
    page = Page(token)
    view = page.view()
    quote_hash = view["quote"]["quote_hash"]
    for flag in view["flags"]:
        if flag["requires_ack"]:
            assert page.ack(quote_hash, flag["flag_key"]).status_code == 204
    response = page.post("confirm", {"quote_hash": quote_hash})
    assert response.status_code == 200, response.text
    return response.json()["order_number"]


async def test_after_the_order_is_confirmed_the_chat_starts_a_new_quote(chat, live_client):
    conversation_id, old, token = chat_quote_and_send(chat, live_client)
    number = confirm_on_the_phone(token)

    sent = live_client.get("/api/v1/chat/sent/latest").json()
    assert (sent["status"], sent["order_number"]) == ("confirmed", number)

    # The buyer writes again. The model is told the order is closed; one that still tries
    # to change it gets /mcp's refusal, and no card for the closed quote appears.
    chat.reset(
        fx.call("update_quote", {"quote_id": old, "lines": [{**LINE, "quantity": 30}]}),
        fx.text(
            "That order is already confirmed."
            + fx.fence({"id": "root", "component": "QuoteCard", "quoteId": old})
        ),
    )
    pairs = send(live_client, conversation_id=conversation_id, message="Make it 30 l")
    system = system_text(chat)
    assert "# The previous order" in system and f"order number {number}" in system
    assert "start a new quote with `build_quote`" in system
    [refused] = chat.tool_results(1)
    assert "can no longer be changed" in refused["error"]
    assert fx.cards(pairs) == []
    assert pairs[-1] == ("done", {"quote_id": None})

    # Still closed on the next message, until a new quote comes.
    chat.reset(fx.call("build_quote", {"lines": [{**LINE, "quantity": 30}]}), fx.text("New one."))
    pairs = send(live_client, conversation_id=conversation_id, message="A new order, 30 l")
    assert "# The previous order" in system_text(chat)
    new = pairs[-1][1]["quote_id"]
    assert new and new != old
    assert [c["quoteId"] for c in fx.cards(pairs)] == [new]

    # The new quote is the latest: no more note about the old one.
    chat.reset(fx.text("Anything else?"))
    pairs = send(live_client, conversation_id=conversation_id, message="thanks")
    assert "# The previous order" not in system_text(chat)
    assert pairs[-1] == ("done", {"quote_id": new})


async def test_a_cancelled_order_is_closed_too_and_gets_no_notice_again(chat, live_client):
    conversation_id, old, token = chat_quote_and_send(chat, live_client)
    page = Page(token)
    assert (
        page.post("cancel", {"quote_hash": page.view()["quote"]["quote_hash"]}).status_code == 204
    )
    assert live_client.get("/api/v1/chat/sent/latest").json()["status"] == "cancelled"

    # A model that still sends it again gets the refusal, and no SentNotice is added.
    chat.reset(fx.call("request_confirmation", {"quote_id": old}), fx.text("Hmm."))
    pairs = send(live_client, conversation_id=conversation_id, message="send it again")
    assert "cancelled by the buyer" in system_text(chat)
    assert "error" in chat.tool_results(1)[0]
    assert fx.cards(pairs) == []
    assert pairs[-1] == ("done", {"quote_id": None})
