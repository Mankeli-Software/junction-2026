"""The confirmation page's endpoints over HTTP (#47): view, acknowledge, edit, confirm,
cancel and the order record. Needs DATABASE_URL.

Quotes come from the fixture catalogue and the recorded Valio snapshots, so the products
are known: "maito" 20 l is Valio Arki semi skimmed milk 1 l (stock unverified, so it has a
flag to tick) and "arla" 5 l is Arla fat free milk 1 l (verified).
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.adapters import valio
from app.main import app
from app.models import AuditEvent, Confirmation, Order, OrderLine, OrderSession, Quote
from app.services import confirmation_page
from tests.phones import new_number

pytestmark = pytest.mark.usefixtures("app_db", "no_caller")

LINES = [
    {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"},
    {"line_id": "l2", "text": "arla", "quantity": 5, "unit": "l", "needed_by": "2026-11-16"},
]
STOCK_FLAG = "AVAILABILITY_UNVERIFIED:l1"
VALIO_MEDIA = "https://api.valioaimo.fi/medias/"


class Page:
    """The confirmation page's server: no cookie, only the token in the path."""

    def __init__(self, token: str):
        self.client = TestClient(app)
        self.url = f"/api/v1/confirmations/{token}"

    def view(self) -> dict:
        response = self.client.get(self.url)
        assert response.status_code == 200, response.text
        return response.json()

    def post(self, action: str, body: dict):
        return self.client.post(f"{self.url}/{action}", json=body)

    def ack(self, quote_hash: str, flag_key: str, option_id: str | None = None):
        body = {"quote_hash": quote_hash, "flag_key": flag_key, "option_id": option_id}
        return self.post("acknowledgements", body)


def ordered(lang: str = "en") -> tuple[TestClient, dict, str]:
    """A signed-in browser, its quote sent for confirmation, and the token from its inbox."""
    browser = TestClient(app)
    phone = new_number()
    response = browser.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": lang}
    )
    assert response.status_code == 201, response.text
    quote = browser.post("/api/v1/quotes", json={"lines": LINES}).json()
    assert quote["decision"] == "ready", quote
    sent = browser.post(f"/api/v1/quotes/{quote['quote_id']}/confirmation-request")
    assert sent.status_code == 200, sent.text
    [message] = browser.get("/api/v1/private/inbox").json()
    return browser, quote, message["link"].rsplit("/c/", 1)[1]


def flag(view: dict, key: str) -> dict:
    return next(f for f in view["flags"] if f["flag_key"] == key)


def line(view: dict, line_id: str) -> dict:
    return next(x for x in view["lines"] if x["line_id"] == line_id)


async def events(engine: AsyncEngine, session_id) -> list[AuditEvent]:
    async with AsyncSession(engine) as db:
        rows = await db.scalars(
            select(AuditEvent).where(AuditEvent.session_id == session_id).order_by(AuditEvent.seq)
        )
        return list(rows)


async def test_build_send_open_acknowledge_edit_confirm_creates_the_order(app_db: AsyncEngine):
    browser, quote, token = ordered()
    page = Page(token)

    view = page.view()
    assert view["state"] == "ready"
    assert view["lang"] == "en"
    assert view["session"]["channel"] == "webmcp"
    assert view["quote"]["quote_id"] == quote["quote_id"]
    assert view["quote"]["quote_hash"] == quote["quote_hash"]
    assert [x["product_id"] for x in view["lines"]] == ["464306", "462775"]
    # Valio's own image URLs from the catalogue (#108).
    assert all(x["image_url"].startswith(VALIO_MEDIA) for x in view["lines"])
    stock = flag(view, STOCK_FLAG)
    assert stock["requires_ack"] is True
    assert stock["acknowledged_at"] is None
    assert stock["is_new"] is False
    assert view["change"] is None and view["order"] is None
    assert token not in str(view)

    # Acknowledge, then edit: the tick carries over to the new quote.
    assert page.ack(view["quote"]["quote_hash"], STOCK_FLAG).status_code == 204
    edit = {"quote_hash": view["quote"]["quote_hash"], "op": "set_quantity", "line_id": "l2"}
    assert page.post("edits", {**edit, "quantity": 6}).status_code == 204

    view = page.view()
    assert view["quote"]["version"] == 2
    assert view["quote"]["quote_hash"] != quote["quote_hash"]
    assert line(view, "l2")["quantity_sales_units"] == 6
    assert line(view, "l2")["asked"]["quantity"] == 6  # still in litres
    assert flag(view, STOCK_FLAG)["acknowledged_at"] is not None
    assert view["change"] == {
        "reason": "edit",
        "previous_total_cents": quote["total_cents"],
        "line_ids": ["l2"],
        "text": None,
    }
    assert view["quote"]["total_cents"] == quote["total_cents"] + 292

    response = page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]})
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert re.fullmatch(r"D-\d{4,}", receipt["order_number"])

    # A double tap gives the same order, not a second one.
    again = page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]})
    assert again.json() == receipt

    # The link stays readable as the receipt.
    done = page.view()
    assert done["state"] == "confirmed"
    assert done["order"]["order_number"] == receipt["order_number"]
    assert [a["flag_key"] for a in done["order"]["acknowledged"]] == [STOCK_FLAG]
    assert done["quote"]["quote_id"] == view["quote"]["quote_id"]
    assert done["change"] is None

    status = browser.get(f"/api/v1/quotes/{view['quote']['quote_id']}/status").json()
    assert status["status"] == "confirmed"
    assert status["order_number"] == receipt["order_number"]

    async with AsyncSession(app_db) as db:
        [order] = (await db.scalars(select(Order))).all()
        lines = (await db.scalars(select(OrderLine).order_by(OrderLine.line_id))).all()
        session = await db.get_one(OrderSession, order.session_id)
        confirmation = await db.scalar(select(Confirmation))
    assert order.order_number == receipt["order_number"]
    assert order.quote_hash == view["quote"]["quote_hash"]
    assert order.total_cents == view["quote"]["total_cents"]
    assert [(x.line_id, x.product_id, x.quantity_sales_units) for x in lines] == [
        ("l1", "464306", 20),
        ("l2", "462775", 6),
    ]
    assert session.state == "confirmed"
    assert confirmation.opened_at is not None and confirmation.used_at is not None
    assert confirmation.quote_id == view["quote"]["quote_id"]
    assert confirmation.original_quote_id == quote["quote_id"]

    types = [e.type for e in await events(app_db, order.session_id)]
    page_steps = [
        t
        for t in types
        if t
        in {
            "link_opened",
            "flags_acknowledged",
            "quote_voided",
            "quote_edited",
            "stock_rechecked",
            "order_confirmed",
        }
    ]
    assert page_steps == [
        "link_opened",
        "flags_acknowledged",
        "quote_voided",
        "quote_edited",
        "stock_rechecked",
        "order_confirmed",
    ]
    assert types.count("quote_built") == 2  # the agent's quote and the edit's


async def test_ordering_the_same_again_flags_a_possible_duplicate(app_db: AsyncEngine):
    # A confirmed order reaches the engine's history, so the same products quoted again
    # within two hours need an acknowledgement (#42).
    browser, quote, token = ordered()
    assert not [f for f in quote["flags"] if f["code"] == "DUPLICATE_ORDER"]
    page = Page(token)
    view = page.view()
    page.ack(view["quote"]["quote_hash"], STOCK_FLAG)
    assert page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]}).status_code == 200

    again = browser.post("/api/v1/quotes", json={"lines": LINES}).json()

    duplicates = [f for f in again["flags"] if f["code"] == "DUPLICATE_ORDER"]
    assert [f["flag_key"] for f in duplicates] == ["DUPLICATE_ORDER:l1", "DUPLICATE_ORDER:l2"]
    assert again["decision"] == "ready"


async def test_no_event_holds_the_token_or_the_link(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    view = page.view()
    page.ack(view["quote"]["quote_hash"], STOCK_FLAG)
    page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]})

    async with AsyncSession(app_db) as db:
        rows = (await db.scalars(select(AuditEvent))).all()
    dumped = " ".join(f"{e.payload} {e.text_fi} {e.text_en}" for e in rows)
    assert token not in dumped
    assert confirmation_page.hash_token(token) not in dumped
    assert "/c/" not in dumped


async def test_opening_twice_writes_one_link_opened(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    first = page.view()
    second = page.view()
    assert first == second
    async with AsyncSession(app_db) as db:
        q = await db.get_one(Quote, uuid.UUID(quote["quote_id"]))
        session = await db.get_one(OrderSession, q.session_id)
    assert session.state == "link_opened"
    types = [e.type for e in await events(app_db, q.session_id)]
    assert types.count("link_opened") == 1


async def test_a_stale_hash_is_refused_with_409(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    old = page.view()["quote"]["quote_hash"]
    page.ack(old, STOCK_FLAG)
    page.post("edits", {"quote_hash": old, "op": "remove", "line_id": "l2"})

    for action, body in [
        ("confirm", {"quote_hash": old}),
        ("cancel", {"quote_hash": old}),
        ("edits", {"quote_hash": old, "op": "remove", "line_id": "l1"}),
        ("acknowledgements", {"quote_hash": old, "flag_key": STOCK_FLAG}),
    ]:
        response = page.post(action, body)
        assert response.status_code == 409, action
        assert response.json() == {
            "detail": {
                "text": {
                    "fi": "Tilaus muuttui toisessa ikkunassa. Tämä on uusin versio.",
                    "en": "The order changed in another window. This is the latest version.",
                },
                "line_id": None,
            }
        }
    async with AsyncSession(app_db) as db:
        assert await db.scalar(select(func.count()).select_from(Order)) == 0
    assert page.view()["state"] == "ready"


async def test_an_unacknowledged_flag_is_refused_with_422(app_db: AsyncEngine):
    _, _, token = ordered()
    page = Page(token)
    view = page.view()

    response = page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]})

    assert response.status_code == 422
    assert response.json()["detail"]["text"]["en"] == "Check the flagged items first."
    async with AsyncSession(app_db) as db:
        assert await db.scalar(select(func.count()).select_from(Order)) == 0


async def test_worse_availability_at_confirm_shows_a_new_quote(app_db: AsyncEngine, monkeypatch):
    _, quote, token = ordered()
    page = Page(token)
    view = page.view()
    page.ack(view["quote"]["quote_hash"], STOCK_FLAG)

    # The milk on line 1 sold out after the quote.
    real = valio.get_offers

    async def sold_out(ids, needed_by):
        offers = await real(ids, needed_by)
        return [
            o.model_copy(update={"schedule": []}) if o.product_id == "464306" else o for o in offers
        ]

    monkeypatch.setattr(valio, "get_offers", sold_out)

    response = page.post("confirm", {"quote_hash": view["quote"]["quote_hash"]})

    assert response.status_code == 409
    assert response.json()["detail"]["text"]["en"] == (
        "Stock changed since the quote. Here is the updated order."
    )
    requoted = page.view()
    assert requoted["state"] == "requote_needed"
    assert requoted["quote"]["version"] == 2
    assert line(requoted, "l1")["product_id"] != "464306"
    assert requoted["change"]["reason"] == "requote"
    assert requoted["change"]["line_ids"] == ["l1"]
    assert requoted["change"]["previous_total_cents"] == quote["total_cents"]
    assert requoted["change"]["text"]["en"].startswith("Stock changed")
    async with AsyncSession(app_db) as db:
        old = await db.get_one(Quote, uuid.UUID(quote["quote_id"]))
        new = await db.get_one(Quote, uuid.UUID(requoted["quote"]["quote_id"]))
        assert await db.scalar(select(func.count()).select_from(Order)) == 0
    assert (old.status, new.status) == ("void", "pending_confirmation")

    # The new product's own stock flag is new and needs a tick before confirming.
    new_flags = [f for f in requoted["flags"] if f["requires_ack"] and not f["acknowledged_at"]]
    for f in new_flags:
        assert f["is_new"] is True
        page.ack(requoted["quote"]["quote_hash"], f["flag_key"])
    confirmed = page.post("confirm", {"quote_hash": requoted["quote"]["quote_hash"]})
    assert confirmed.status_code == 200, confirmed.text
    assert page.view()["state"] == "confirmed"

    types = [e.type for e in await events(app_db, old.session_id)]
    assert types.index("stock_rechecked") < types.index("requote_needed")
    assert "order_confirmed" in types


async def test_cancel_uses_the_link_up_and_orders_nothing(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    quote_hash = page.view()["quote"]["quote_hash"]

    assert page.post("cancel", {"quote_hash": quote_hash}).status_code == 204
    assert page.post("cancel", {"quote_hash": quote_hash}).status_code == 204  # double tap

    view = page.view()
    assert view["state"] == "cancelled"
    assert view["order"] is None
    assert page.ack(quote_hash, STOCK_FLAG).status_code == 409
    assert page.post("confirm", {"quote_hash": quote_hash}).status_code == 409
    async with AsyncSession(app_db) as db:
        q = await db.get_one(Quote, uuid.UUID(quote["quote_id"]))
        confirmation = await db.scalar(select(Confirmation))
        assert await db.scalar(select(func.count()).select_from(Order)) == 0
    assert q.status == "cancelled"
    assert confirmation.used_at is not None
    types = [e.type for e in await events(app_db, q.session_id)]
    assert types.count("order_cancelled") == 1


async def test_a_confirmed_order_cannot_be_cancelled(app_db: AsyncEngine):
    _, _, token = ordered()
    page = Page(token)
    quote_hash = page.view()["quote"]["quote_hash"]
    page.ack(quote_hash, STOCK_FLAG)
    assert page.post("confirm", {"quote_hash": quote_hash}).status_code == 200

    response = page.post("cancel", {"quote_hash": quote_hash})

    assert response.status_code == 409
    assert response.json()["detail"]["text"]["en"] == "This order is already closed."
    assert page.view()["state"] == "confirmed"


async def test_orders_are_numbered_in_sequence(app_db: AsyncEngine):
    numbers = []
    for _ in range(2):
        _, _, token = ordered()
        page = Page(token)
        quote_hash = page.view()["quote"]["quote_hash"]
        page.ack(quote_hash, STOCK_FLAG)
        numbers.append(page.post("confirm", {"quote_hash": quote_hash}).json()["order_number"])
    first, second = (int(n.removeprefix("D-")) for n in numbers)
    assert second == first + 1


async def test_edits_that_cant_be_done_are_refused_and_change_nothing(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    quote_hash = page.view()["quote"]["quote_hash"]
    edit = {"quote_hash": quote_hash}

    not_offered = page.post(
        "edits", {**edit, "op": "choose_alternative", "line_id": "l2", "alternative_id": "464306"}
    )
    assert not_offered.status_code == 422
    assert not_offered.json()["detail"]["line_id"] == "l2"

    unknown_line = page.post("edits", {**edit, "op": "remove", "line_id": "l9"})
    assert unknown_line.status_code == 422

    zero = page.post("edits", {**edit, "op": "set_quantity", "line_id": "l1", "quantity": 0})
    assert zero.status_code == 422  # the body's own check

    assert page.post("edits", {**edit, "op": "remove", "line_id": "l2"}).status_code == 204
    view = page.view()
    last = page.post(
        "edits", {"quote_hash": view["quote"]["quote_hash"], "op": "remove", "line_id": "l1"}
    )
    assert last.status_code == 422
    assert last.json()["detail"]["text"]["en"].startswith("This is the only line.")
    assert page.view()["quote"]["version"] == 2


async def test_choosing_an_alternative_makes_a_new_quote(app_db: AsyncEngine):
    _, quote, token = ordered()
    page = Page(token)
    view = page.view()
    [alternative, _] = line(view, "l1")["alternatives"]

    response = page.post(
        "edits",
        {
            "quote_hash": view["quote"]["quote_hash"],
            "op": "choose_alternative",
            "line_id": "l1",
            "alternative_id": alternative["product_id"],
        },
    )

    assert response.status_code == 204, response.text
    new = page.view()
    assert line(new, "l1")["product_id"] == alternative["product_id"]
    assert line(new, "l1")["line_total_cents"] == alternative["line_total_cents"]
    assert new["change"]["line_ids"] == ["l1"]


async def test_a_choose_flag_takes_an_option(app_db: AsyncEngine):
    """The engine doesn't emit `choose` flags yet, so this one is put on the stored quote."""
    _, quote, token = ordered()
    choose = {
        "flag_key": "ROUNDED_UP:l2",
        "code": "ROUNDED_UP",
        "line_ids": ["l2"],
        "kind": "choose",
        "text": {"fi": "Pyöristin.", "en": "I rounded up."},
        "options": [
            {"option_id": "keep", "label": {"fi": "Pidä", "en": "Keep"}, "line_total_cents": 1460},
            {
                "option_id": "exact:463380",
                "label": {"fi": "Tasan", "en": "Exactly"},
                "line_total_cents": 1505,
            },
        ],
    }
    async with AsyncSession(app_db) as db:
        q = await db.get_one(Quote, uuid.UUID(quote["quote_id"]))
        output = {**q.engine_output, "flags": [*q.engine_output["flags"], choose]}
        await db.execute(update(Quote).where(Quote.id == q.id).values(engine_output=output))
        await db.commit()
    page = Page(token)
    view = page.view()
    rounded = flag(view, "ROUNDED_UP:l2")
    assert rounded["requires_ack"] is True
    assert rounded["current_option_id"] == "keep"

    # An unknown option is refused; "keep" just ticks it.
    assert page.ack(view["quote"]["quote_hash"], "ROUNDED_UP:l2", "nope").status_code == 422
    assert page.ack(view["quote"]["quote_hash"], "ROUNDED_UP:l2", "keep").status_code == 204
    assert flag(page.view(), "ROUNDED_UP:l2")["acknowledged_at"] is not None

    # The other option changes the order: a new quote with that product on the line.
    response = page.ack(view["quote"]["quote_hash"], "ROUNDED_UP:l2", "exact:463380")
    assert response.status_code == 204, response.text
    new = page.view()
    assert new["quote"]["version"] == 2
    assert line(new, "l2")["product_id"] == "463380"
    assert new["change"]["reason"] == "edit"


async def test_an_unknown_link_is_404(app_db: AsyncEngine):
    page = Page("not-a-real-token")
    assert page.client.get(page.url).status_code == 404
    assert page.post("confirm", {"quote_hash": "x"}).status_code == 404
    assert page.post("cancel", {"quote_hash": "x"}).status_code == 404


async def test_the_view_is_not_cached(app_db: AsyncEngine):
    _, _, token = ordered()
    response = Page(token).client.get(f"/api/v1/confirmations/{token}")
    assert response.headers["cache-control"] == "no-store"
