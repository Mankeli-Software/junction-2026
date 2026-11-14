"""The stage demo script over MCP, the way an outside agent sees the app (#98).

One visitor (a milk-free school kitchen, new for each run) connects an agent through the
real OAuth flow; the beats then run in order in one MCP session. A failing beat is
reported at the end and the later ones still run. Run with `-s` to read what S.I.MO would
have in front of it at each beat.
"""

from tests.live.agent import ToolFailed, dairy_lines, dead_ends, describe_quote
from tests.live.simo_live import Visitor, describe_story, mcp_agent, next_weekday

TOOLS = {
    "search_products",
    "get_customer_context",
    "search_recipes",
    "get_recipe",
    "propose_recipe",
    "confirm_recipe",
    "build_quote",
    "update_quote",
    "request_confirmation",
    "get_order_status",
}
RECIPE_SEARCHES = ("makaronilaatikko", "makaroni")
PORTIONS = 120


def usual_line(item: dict, needed_by: str, line_id: str, times: int = 1) -> dict:
    return {
        "line_id": line_id,
        "product_id": item["product_id"],
        "usual": True,
        "quantity": float(item["quantity"]) * times,
        "unit": item["unit"],
        "needed_by": needed_by,
    }


async def test_the_demo_script_over_mcp(run, beats):
    async with Visitor(run) as visitor:
        account = await visitor.enter_number(["milk_free"], "fi")
        print(f"visitor: {account['company_name']}, {account['kitchen_type']}")
        today = await run.business_date()
        monday = next_weekday(today, 0).isoformat()
        access_token = await visitor.connect_agent()

        async with mcp_agent(run, access_token) as agent:
            context: dict = {}
            quotes: dict[str, dict] = {}

            with beats("context"):
                assert await agent.tool_names() == TOOLS
                context = await agent.call("get_customer_context")
                print(f"  {context['company_name']}, {context['kitchen_type']}")
                print("  usual: " + ", ".join(i["name"]["fi"] for i in context["usual_items"]))
                assert context["kitchen_type"] == "school_kitchen"
                assert [e["key"] for e in context["exclusions"]] == ["milk_free"]
                assert context["usual_items"], "no usual items"
                assert context["last_order"], "no last order"

            with beats("usual"):
                lines = [
                    usual_line(item, monday, f"u{n}")
                    for n, item in enumerate(context["usual_items"], 1)
                ]
                quote = quotes["usual"] = await agent.call("build_quote", lines=lines)
                print(describe_quote(quote))
                assert quote["lines"], "nothing of the usual order could be quoted"
                assert not dairy_lines(quote), f"milk products: {dairy_lines(quote)}"
                assert not dead_ends(quote), f"no next step: {dead_ends(quote)}"

            with beats("recipe"):
                hits: list[dict] = []
                for words in RECIPE_SEARCHES:
                    hits = (await agent.call("search_recipes", q=words))["results"]
                    if hits:
                        break
                assert hits, f"no recipe for {RECIPE_SEARCHES}"
                print("  found: " + ", ".join(f"{h['name']} [{h['recipe_id']}]" for h in hits[:5]))
                # The first hit with ingredients linked to products; the others can't be ordered.
                recipe, linked = None, []
                for hit in hits[:5]:
                    recipe = await agent.call(
                        "get_recipe", recipe_id=hit["recipe_id"], portions=PORTIONS
                    )
                    linked = [i["name"] for i in recipe["ingredients"] if i["product_id"]]
                    print(f"  {recipe['name']} for {recipe['portions']}: linked {linked}")
                    if linked:
                        break
                assert recipe and linked, "no macaroni recipe has an ingredient linked to a product"
                line = {
                    "line_id": "r1",
                    "quantity": PORTIONS,
                    "unit": "piece",
                    "needed_by": monday,
                    "recipe_ref": {"recipe_id": recipe["recipe_id"], "portions": PORTIONS},
                    "group": recipe["name"],
                }
                quote = quotes["recipe"] = await agent.call("build_quote", lines=[line])
                print(describe_quote(quote))
                covered = len(quote["lines"]) + len(quote["not_ordered"]) + len(quote["rejections"])
                assert covered >= len(recipe["ingredients"]), "ingredients went missing"
                assert not dairy_lines(quote), f"milk products: {dairy_lines(quote)}"
                assert not dead_ends(quote), f"no next step: {dead_ends(quote)}"

            with beats("allergen"):
                asked = [
                    ("a1", "maito", 20, "l"),
                    ("a2", "voi", 5, "kg"),
                    ("a3", "juustoraaste", 3, "kg"),
                ]
                lines = [
                    {"line_id": i, "text": text, "quantity": q, "unit": unit, "needed_by": monday}
                    for i, text, q, unit in asked
                ]
                quote = quotes["allergen"] = await agent.call("build_quote", lines=lines)
                print(describe_quote(quote))
                assert not dairy_lines(quote), f"milk products: {dairy_lines(quote)}"
                assert not dead_ends(quote), f"no next step: {dead_ends(quote)}"
                answered = {line["line_id"] for line in quote["lines"]}
                answered |= {r["line_id"] for r in quote["rejections"]}
                if quote["clarification"]:
                    answered.add(quote["clarification"]["line_id"])
                assert answered, "no line was answered at all"

            with beats("exception"):
                # Delivery asked for today: past the cutoff.
                line = {
                    "line_id": "e1",
                    "text": "porkkana",
                    "quantity": 10,
                    "unit": "kg",
                    "needed_by": today.isoformat(),
                }
                quote = quotes["exception"] = await agent.call("build_quote", lines=[line])
                print(describe_quote(quote))
                assert not dead_ends(quote), f"no next step: {dead_ends(quote)}"
                later = [ln for ln in quote["lines"] if ln["delivery_date"] > today.isoformat()]
                assert later or quote["rejections"] or quote["clarification"], (
                    "a delivery for today went through without another date or a next step"
                )

            # The order that is confirmed at the end: ten times a usual item.
            quoted = {line["product_id"] for line in quotes.get("usual", {}).get("lines", [])}
            item = next(
                (i for i in context.get("usual_items", []) if i["product_id"] in quoted), None
            )

            with beats("unusual"):
                assert item, "no usual item could be quoted in the `usual` beat"
                line = usual_line(item, monday, "x1", times=10)
                quote = quotes["order"] = await agent.call("build_quote", lines=[line])
                print(describe_quote(quote))
                assert quote["decision"] == "ready"
                assert "QUANTITY_UNUSUAL" in {flag["code"] for flag in quote["flags"]}

            with beats("update"):
                assert "order" in quotes, "no quote to update"
                first = quotes["order"]
                line = usual_line(item, monday, "x1", times=11)
                quote = await agent.call("update_quote", quote_id=first["quote_id"], lines=[line])
                print(describe_quote(quote))
                assert quote["version"] == first["version"] + 1
                assert quote["parent_quote_id"] == first["quote_id"]
                assert quote["decision"] == "ready"
                quotes["order"] = quote
                old = await agent.call("get_order_status", quote_id=first["quote_id"])
                assert old["replaced_by_quote_id"] == quote["quote_id"], old

            with beats("confirm"):
                assert "order" in quotes, "no quote to confirm"
                quote = quotes["order"]
                sent = await agent.call("request_confirmation", quote_id=quote["quote_id"])
                print(f"  sent to {sent['sent_to_masked']}: {sent['delivery_status']}")
                inbox = await visitor.inbox()
                assert inbox, "the link did not reach the inbox"
                confirmed = await visitor.confirm(inbox[-1]["link"])
                flags = [flag["code"] for flag in confirmed["view"]["flags"]]
                print(f"  page flags: {flags}; order {confirmed['order_number']}")
                assert "QUANTITY_UNUSUAL" in flags, "the sanity flag is not on the page"
                status = await agent.call("get_order_status", quote_id=quote["quote_id"])
                assert status["status"] == "confirmed", status
                assert status["order_number"] == confirmed["order_number"]

            with beats("errors"):
                # A tool error must come back as one the agent can read, not as a crash.
                try:
                    await agent.call("get_order_status", quote_id="no-such-quote")
                except ToolFailed as error:
                    print(f"  {error}")
                else:
                    raise AssertionError("an unknown quote id gave no error")

        with beats("audit"):
            sessions = await run.sessions()
            assert sessions, "the run's sessions are not listed"
            for card in sessions:
                print(f"  session {card['session_id']} ({card['client']}): {card['state']}")
                print(describe_story(await run.story(card["session_id"])))
                check = await run.verify_audit(card["session_id"])
                assert check["ok"], check
            whole = await run.verify_audit()
            print(f"  chain: {whole}")
            assert whole["ok"], whole

        with beats("hidden"):
            # A test run stays off the public dashboard.
            async with run.http() as http:
                public = (await http.get("/api/v1/public/orders")).json()
            names = [company["name"] for company in public["companies"]]
            assert account["company_name"] not in names

    beats.finish()
