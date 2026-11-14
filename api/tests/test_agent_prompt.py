import re
from datetime import date
from decimal import Decimal

import pytest

from app.agent import (
    AGENT_TOOLS,
    CALL_CONNECTED,
    END_CALL,
    PROMPT_VERSION,
    build_system_prompt,
)
from app.schemas import (
    BuildQuoteRequest,
    Claim,
    CustomerContext,
    Exclusion,
    ExclusionLabel,
    LineRequest,
    Localized,
    RecipeRef,
    RequestedUnit,
    UpdateQuoteRequest,
    UsualItem,
)

TODAY = date(2026, 11, 14)  # a Saturday

CONTEXT = CustomerContext(
    company_name="Hassu Hauki Oy",
    phone_masked="+358 40 *** **12",
    exclusions=[
        ExclusionLabel(
            key=Exclusion.lactose_free,
            label=Localized(fi="laktoositon", en="lactose-free"),
        ),
        ExclusionLabel(
            key=Exclusion.nut_free,
            label=Localized(fi="pähkinätön", en="nut-free"),
        ),
    ],
    usual_items=[
        UsualItem(
            product_id="400123",
            name=Localized(fi="Valio voi 500 g", en="Valio butter 500 g"),
            quantity=Decimal("20.000"),
            unit="kg",
        )
    ],
    lang="fi",
)

# Every tool, function and argument the prompt may name in backticks.
KNOWN = (
    set(AGENT_TOOLS)
    | {END_CALL, CALL_CONNECTED}
    | set(LineRequest.model_fields)
    | set(UpdateQuoteRequest.model_fields)
    | set(BuildQuoteRequest.model_fields)
    | set(RecipeRef.model_fields)
    | {u.value for u in RequestedUnit}
    | {c.value for c in Claim}
    # Response fields the prompt reads from QuoteResponse and ConfirmationRequestResponse
    | {
        "decision",
        "ready",
        "needs_clarification",
        "rejected",
        "lines",
        "flags",
        "clarification",
        "rejections",
        "total_cents",
        "speak",
        "delivery_status",
        "failed",
        "fi",
        "en",
        "ALLERGEN_NO_LISTING",
        "not_ordered",
    }
)


def prompt(channel="phone", call_language="auto", context=CONTEXT) -> str:
    return build_system_prompt(context, channel, call_language, today=TODAY)


@pytest.mark.parametrize("channel", ["phone", "web_chat"])
def test_customer_context_is_in_the_prompt(channel):
    text = prompt(channel)
    assert "Hassu Hauki Oy" in text
    assert "lactose-free (laktoositon)" in text
    assert "nut-free (pähkinätön)" in text
    assert "Valio voi 500 g / Valio butter 500 g: usually 20 kg (product_id 400123)" in text
    assert "Account language: Finnish" in text


def test_empty_context_says_none():
    context = CONTEXT.model_copy(update={"exclusions": [], "usual_items": [], "lang": "en"})
    text = prompt(context=context)
    assert "Kitchen exclusions: none." in text
    assert "Usual items:\n  - none" in text
    assert "Account language: English" in text


def test_days_are_listed_from_today():
    text = prompt()
    assert "Today is Saturday 2026-11-14 (lauantai)." in text
    assert "Monday 2026-11-16 (maanantai)" in text
    assert "Saturday 2026-11-21 (lauantai)" in text


def test_greeting_and_ai_helper():
    text = prompt()
    assert "Hei, Hassu Hauki Oy! Täällä S.I.MO, Valio Aimon tekoälyavustaja." in text
    assert "say that you are S.I.MO, Valio Aimo's AI helper" in text


def test_phone_and_chat_differ():
    phone, chat = prompt("phone"), prompt("web_chat")
    assert "# Speaking style (phone)" in phone and "# Writing style (chat)" not in phone
    assert "# Writing style (chat)" in chat and "# Speaking style (phone)" not in chat
    assert "No lists" in phone
    assert "after we hang up" in phone and "after we hang up" not in chat
    assert "on its way to your phone" in chat
    assert f"`{END_CALL}`" in phone and END_CALL not in chat
    assert f"`{CALL_CONNECTED}`" in phone and CALL_CONNECTED not in chat


def test_call_language_adds_one_line():
    auto = prompt(call_language="auto").splitlines()
    for lang, name in [("fi", "Finnish"), ("en", "English")]:
        forced = prompt(call_language=lang).splitlines()
        added = [line for line in forced if line not in auto]
        assert added == [f"- Always respond in {name}, whatever language the caller uses."]
        assert len(forced) == len(auto) + 1


def test_answer_in_the_callers_language_is_explicit():
    text = prompt()
    assert "Answer in the language the caller speaks" in text
    assert "If the caller speaks English, answer in English" in text


def test_a_language_switch_holds_to_the_end_of_the_call():
    # #85: after an English "yes", the link sentence came back in the account's Finnish.
    text = prompt()
    assert "Stay in the language of the caller's latest turn" in text
    assert "the link and the goodbye" in text


def test_backticked_names_match_the_contract():
    for channel in ("phone", "web_chat"):
        names = set(re.findall(r"`([^`]+)`", prompt(channel)))
        assert names <= KNOWN, names - KNOWN
        assert {"build_quote", "update_quote", "request_confirmation"} <= names


def test_tool_table_matches_the_contract():
    assert AGENT_TOOLS["build_quote"] is BuildQuoteRequest
    assert AGENT_TOOLS["update_quote"] is UpdateQuoteRequest
    assert len(AGENT_TOOLS) == 10  # vision §8: recipes and recipe photos are two tools each
    assert END_CALL not in AGENT_TOOLS


def test_checklist_rules_are_present():
    text = prompt()
    assert "Call `build_quote` once, with all the lines" in text
    assert "or asks for the price, the total or a summary" in text
    assert "one question per turn" in text
    assert "Mention at most one alternative" in text
    assert "Say this notice only once per order" in text
    assert "Never say the order is placed" in text
    assert "Call `request_confirmation` only in your next turn" in text
    assert "after the caller has said a clear yes" in text
    assert "Never answer your own question" in text
    assert "can't be overridden" in text and "Say so and move on" in text
    assert "Keep the brand and the pack size" in text
    assert "Use the base form where it is natural" in text
    assert "Never offer email, SMS" in text


def test_phone_replies_are_short():
    phone, chat = prompt("phone"), prompt("web_chat")
    assert "at most one or two short sentences per turn, and at most one question" in phone
    assert "Don't repeat back what the caller just said" in phone
    assert '"Selvä. Muuta?" / "Got it. Anything else?"' in phone
    assert "give one compact summary from the result: the total and the delivery day" in phone
    assert "Always say both" in phone
    assert "Don't read out each line, pack size or price" in phone
    # The engine's `speak` may be shortened, but not the parts the buyer must know.
    assert "keep anything the buyer must know: the allergen notice, a substitute" in phone
    # The chat keeps its read-back: the page shows the quote card next to it.
    assert "repeat it back in a few words (product, quantity, day)" in chat
    assert "for each line the product chosen" in chat
    for text in ("Don't repeat back", "compact summary", "`speak`** is"):
        assert text not in chat


@pytest.mark.parametrize("channel", ["phone", "web_chat"])
@pytest.mark.parametrize("call_language", ["auto", "fi", "en"])
def test_name_and_characters(channel, call_language):
    text = prompt(channel, call_language)
    assert "·" not in text  # no middle dot
    assert "S.I.MO" in text
    assert not re.search(r"S\.I\.M\.O|SIMO|S\.I\.Mo|Simo\b", text)


def test_same_input_same_prompt():
    assert prompt() == prompt()


def test_version_is_set():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", PROMPT_VERSION)
