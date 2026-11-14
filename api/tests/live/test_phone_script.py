"""Phone calls without a voice: the caller's lines are typed into `/voice/ws` (#98).

The real Gemini Live model, the prompt, the tools and the relay's guards run; only speech
recognition is skipped. Each call opens one Live session, so keep runs few. Run with `-s`
to read the call.
"""

import pytest

from tests.live.agent import dairy_lines, describe_quote
from tests.live.simo_live import CallerScript, PhoneCall, Visitor, describe_story, play_call

STOCK = {
    "fi": {
        "done": "Ei muuta, siinä kaikki.",
        "yes": "Kyllä, lähetä se.",
        "bye": "Kiitos, hei hei.",
    },
    "en": {"done": "Nothing else, that's all.", "yes": "Yes, send it.", "bye": "Thanks, bye."},
}

ORDER = {
    "fi": ["Hei! Tarvitsisin kaksikymmentä kiloa porkkanaa maanantaiksi. Siinä kaikki."],
    "en": ["Hi! I need twenty kilos of carrots for Monday. That's all."],
}
MILK = {
    "fi": ["Hei! Tarvitsisin kaksikymmentä litraa maitoa maanantaiksi. Siinä kaikki."],
    "en": ["Hi! I need twenty litres of milk for Monday. That's all."],
}
RECIPE = {
    "fi": [
        "Hei! Teen makaronilaatikkoa sadallekahdellekymmenelle hengelle maanantaiksi.",
        "Kyllä, tilaa sen ainekset.",
    ],
    "en": [
        "Hi! I'm making macaroni casserole for a hundred and twenty people for Monday.",
        "Yes, order its ingredients.",
    ],
}

LANGS = ("fi", "en")


async def call_as(run, case: str, lang: str, exclusions: list[str], lines: list[str]):
    """One call by a new school kitchen. Returns the call and what the visitor ends up with."""
    run.case = f"{case}-{lang}"
    async with Visitor(run) as visitor:
        account = await visitor.enter_number(exclusions, lang, run.school_number(run.case))
        print(f"\n== {run.case}: {account['company_name']}, {exclusions or 'no exclusions'}")
        call = await play_call(visitor, CallerScript(lines=lines, **STOCK[lang]))
        print(call.describe())
        inbox = await visitor.inbox()
        quote = await visitor.current_quote()
        if quote:
            print(describe_quote(quote, lang))
        if call.ended and call.ended.get("session_id"):
            print(describe_story(await run.story(call.ended["session_id"])))
        return call, inbox, quote


def check_the_call_itself(call: PhoneCall) -> None:
    assert call.ended is not None, "the call never ended properly"
    assert call.said_by("agent"), "S.I.MO said nothing"
    assert call.said_by("buyer"), "the typed lines did not show as the caller's captions"
    assert all("/c/" not in text for text in call.texts), "a link went over the call socket"
    assert call.ended["ended_by"] in ("agent", "visitor"), call.ended


@pytest.mark.parametrize("lang", LANGS)
async def test_a_short_order_ends_with_the_link_in_the_inbox(run, lang):
    call, inbox, quote = await call_as(run, "call-order", lang, [], ORDER[lang])

    check_the_call_itself(call)
    assert "build_quote" in call.tools
    assert call.link_requested(), "S.I.MO never asked for the link after the caller's yes"
    assert call.inbox_during_call == [], "the link was not held during the call"
    assert call.ended["inbox"] is True
    assert len(inbox) == 1 and "/c/" in inbox[0]["link"]
    assert quote and quote["lines"], "no quote with lines after the call"
    assert call.ended["ended_by"] == "agent", "S.I.MO did not hang up by itself"


@pytest.mark.parametrize("lang", LANGS)
async def test_a_milk_free_kitchen_asking_for_milk_never_gets_a_milk_product(run, lang):
    call, inbox, quote = await call_as(run, "call-allergen", lang, ["milk_free"], MILK[lang])

    check_the_call_itself(call)
    assert "build_quote" in call.tools
    if quote:
        assert not dairy_lines(quote), f"milk products: {dairy_lines(quote)}"
    # Never a dead end: a substitute was quoted, or S.I.MO said what happens next.
    assert (quote and quote["lines"]) or len(call.said_by("agent")) >= 2


@pytest.mark.parametrize("lang", LANGS)
async def test_a_recipe_by_phone_is_quoted_as_one_recipe(run, lang):
    call, inbox, quote = await call_as(run, "call-recipe", lang, [], RECIPE[lang])

    check_the_call_itself(call)
    assert "search_recipes" in call.tools
    assert "build_quote" in call.tools
    assert quote and quote["lines"], "no quote with lines after the call"
    assert quote["not_ordered"], "the recipe's unlinked ingredients are not listed"
    groups = {line["group"] for line in quote["lines"]}
    assert len(groups) == 1 and None not in groups, f"not one recipe group: {groups}"
