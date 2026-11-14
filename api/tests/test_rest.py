import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.policy import get_rule_set

client = TestClient(app)

LINE = {"line_id": "l1", "text": "maito", "quantity": 20, "unit": "l", "needed_by": "2026-11-16"}


def build(**extra) -> dict:
    response = client.post("/api/v1/quotes", json={"lines": [LINE], **extra})
    assert response.status_code == 200, response.text
    return response.json()


# Every tool call writes its audit events, so these need the database.
@pytest.mark.usefixtures("app_db", "dev_caller")
class TestWithCaller:
    def test_build_quote_is_ready(self):
        quote = build()

        assert quote["decision"] == "ready"
        assert quote["status"] == "ready"
        assert quote["version"] == 1
        assert quote["parent_quote_id"] is None
        assert quote["rules_ref"] == get_rule_set().ref
        assert quote["lines"][0]["product_id"] == "464306"

    def test_update_quote_makes_version_2_and_voids_the_old_one(self):
        old = build()

        response = client.post(
            f"/api/v1/quotes/{old['quote_id']}/update",
            json={"lines": [{**LINE, "quantity": 40}]},
        )

        assert response.status_code == 200, response.text
        new = response.json()
        assert new["version"] == 2
        assert new["parent_quote_id"] == old["quote_id"]
        status = client.get(f"/api/v1/quotes/{old['quote_id']}/status").json()
        assert status["status"] == "void"
        assert status["replaced_by_quote_id"] == new["quote_id"]

    def test_request_confirmation_on_a_quote_that_is_not_ready_is_a_conflict(self):
        # A product id that doesn't exist is a hard stop, so the engine rejects the line.
        line = {**LINE, "product_id": "000000"}
        response = client.post("/api/v1/quotes", json={"lines": [line]})
        quote = response.json()
        assert quote["decision"] == "rejected"

        url = f"/api/v1/quotes/{quote['quote_id']}/confirmation-request"
        assert client.post(url).status_code == 409

    def test_unknown_quote_is_404(self):
        assert client.get("/api/v1/quotes/nope/status").status_code == 404
        assert client.post("/api/v1/quotes/nope/confirmation-request").status_code == 404
        response = client.post("/api/v1/quotes/nope/update", json={"lines": [LINE]})
        assert response.status_code == 404

    def test_extra_field_is_422(self):
        response = client.post("/api/v1/quotes", json={"lines": [LINE], "discount": 50})
        assert response.status_code == 422

        response = client.post("/api/v1/quotes", json={"lines": [{**LINE, "price": 0}]})
        assert response.status_code == 422

        response = client.get("/api/v1/products", params={"q": "maito", "bogus": "1"})
        assert response.status_code == 422

    def test_search_products(self):
        response = client.get(
            "/api/v1/products", params={"q": "MAITO", "claims": ["lactose_free"], "limit": 20}
        )

        assert response.status_code == 200, response.text
        hits = {hit["product_id"]: hit for hit in response.json()["results"]}
        assert list(hits)[0] == "464119"  # the search's order: best match first
        # Price and availability from the recorded snapshots (VALIO_SOURCE=snapshot).
        milk = hits["464306"]
        assert milk["unit_price_gross"] is not None
        assert (milk["price_per_base_unit"], milk["base_unit"]) == (milk["unit_price_gross"], "l")
        assert milk["stock_status"] in ("verified", "unverified")
        assert milk["sales_unit_label"]["fi"]
        # No recorded offer: listed, but unavailable and without a price.
        assert hits["464768"]["stock_status"] == "unavailable"
        assert hits["464768"]["unit_price_gross"] is None

    def test_customer_context(self):
        context = client.get("/api/v1/customer-context").json()

        assert context["company_name"] == "Hassu Hauki Oy"
        assert context["exclusions"][0]["key"] == "lactose_free"
        assert [i["product_id"] for i in context["usual_items"]] == ["464306", "475797"]

    def test_recipes(self):
        hits = client.get("/api/v1/recipes", params={"q": "munavoi"}).json()["results"]
        assert [h["recipe_id"] for h in hits] == ["40728"]

        recipe = client.get("/api/v1/recipes/40728", params={"portions": 90}).json()
        butter = next(i for i in recipe["ingredients"] if i["product_id"] == "475797")
        assert butter["quantity"] == 0.2
        assert butter["unit"] == "kg"

        assert client.get("/api/v1/recipes/1", params={"portions": 10}).status_code == 404
        assert client.get("/api/v1/recipes/40728", params={"portions": 0}).status_code == 422


@pytest.mark.usefixtures("no_caller")
def test_no_caller_is_401():
    assert client.get("/api/v1/customer-context").status_code == 401
    assert client.post("/api/v1/quotes", json={"lines": [LINE]}).status_code == 401


def test_openapi_has_the_contract_models():
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert "LineRequest" in schemas
    assert "QuoteResponse" in schemas
