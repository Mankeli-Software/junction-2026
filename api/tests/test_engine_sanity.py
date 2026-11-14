"""Sanity checks from history and the exact-fit choice (#42, technical-plan.md §4.2)."""

from datetime import timedelta
from decimal import Decimal

from app.engine import decide
from app.schemas import Decision, HistoryLine, LineRequest, RequestedUnit
from tests.engine_fixtures import (
    BUSINESS_NOW,
    ISSUED_AT,
    MONDAY,
    engine_input,
    milk_line,
    offer,
    product,
)

MILK = product("1", "Maito 1 l")
ONE = {"candidates": {"milk": ["1"]}, "products": [MILK], "offers": [offer("1", "1.00", 100000)]}


def past(quantity: str, days_ago: int, unit: str = "l", pid: str = "1") -> HistoryLine:
    return HistoryLine(
        product_id=pid,
        quantity=Decimal(quantity),
        sales_unit=unit,
        ordered_at=BUSINESS_NOW - timedelta(days=days_ago),
    )


WEEKLY = (past("100", 7), past("110", 14), past("90", 21))


def codes(out) -> list[str]:
    return [f.code for f in out.flags]


# --- Unusual quantity ------------------------------------------------------------------


def test_a_usual_quantity_raises_no_flag():
    out = decide(engine_input(milk_line(quantity="120"), history=WEEKLY, **ONE))

    assert out.decision == Decision.ready
    assert "QUANTITY_UNUSUAL" not in codes(out)


def test_far_more_than_usual_is_flagged_with_the_usual_range():
    out = decide(engine_input(milk_line(quantity="1000"), history=WEEKLY, **ONE))

    flag = next(f for f in out.flags if f.code == "QUANTITY_UNUSUAL")
    assert flag.kind == "acknowledge"
    assert flag.text.en == (
        "1000 pieces of Maito 1 l is an unusual amount. You usually order 90 to 110 pieces."
    )
    assert flag.text.fi == (
        "1000 kappaletta tuotetta Maito 1 l on poikkeava määrä. Tilaatte yleensä 90–110 kappaletta."
    )
    assert "QUANTITY_UNUSUAL" in out.lines[0].reason_codes
    assert out.decision == Decision.ready  # never blocking


def test_far_less_than_usual_is_flagged():
    out = decide(engine_input(milk_line(quantity="10"), history=WEEKLY, **ONE))

    assert "QUANTITY_UNUSUAL" in codes(out)


def test_the_limits_are_half_the_smallest_and_twice_the_largest():
    at_low = decide(engine_input(milk_line(quantity="45"), history=WEEKLY, **ONE))
    at_high = decide(engine_input(milk_line(quantity="220"), history=WEEKLY, **ONE))

    assert "QUANTITY_UNUSUAL" not in codes(at_low)
    assert "QUANTITY_UNUSUAL" not in codes(at_high)


def test_fewer_than_three_past_orders_are_not_enough():
    out = decide(engine_input(milk_line(quantity="1000"), history=WEEKLY[:2], **ONE))

    assert "QUANTITY_UNUSUAL" not in codes(out)


def test_past_quantities_are_compared_in_sales_units():
    # 10 cases of 10 l is 100 l: asked in litres now, in cases before.
    case = product("1", "Maito 1 l", sales_unit="KI", per_case=10)
    history = (past("10", 7, "sales_unit"), past("11", 14, "sales_unit"), past("9", 21, "l"))
    out = decide(
        engine_input(
            milk_line(quantity="1000"),
            candidates={"milk": ["1"]},
            products=[case],
            offers=[offer("1", "10.00", 100000, sales_unit="KI")],
            history=history,
        )
    )

    flag = next(f for f in out.flags if f.code == "QUANTITY_UNUSUAL")
    assert flag.text.en.endswith("You usually order 0.9 to 11 cases.")


def test_a_past_line_that_cant_be_converted_is_skipped():
    history = (*WEEKLY[:2], past("100", 21, "kg"))
    out = decide(engine_input(milk_line(quantity="1000"), history=history, **ONE))

    assert "QUANTITY_UNUSUAL" not in codes(out)


def test_only_the_same_product_counts():
    history = tuple(h.model_copy(update={"product_id": "2"}) for h in WEEKLY)
    out = decide(engine_input(milk_line(quantity="1000"), history=history, **ONE))

    assert "QUANTITY_UNUSUAL" not in codes(out)


# --- Possible duplicate ----------------------------------------------------------------


def confirmed(minutes_ago: int, pid: str = "1") -> HistoryLine:
    return HistoryLine(
        product_id=pid,
        quantity=Decimal(5),
        sales_unit="sales_unit",
        ordered_at=ISSUED_AT - timedelta(minutes=minutes_ago),
    )


def test_the_same_product_confirmed_20_minutes_ago_is_flagged():
    out = decide(engine_input(milk_line(quantity="120"), history=(confirmed(20),), **ONE))

    flag = next(f for f in out.flags if f.code == "DUPLICATE_ORDER")
    assert flag.kind == "acknowledge"
    assert flag.text.en == (
        "Maito 1 l was already in an order you confirmed in the last two hours. "
        "Please check this isn't a duplicate."
    )
    assert out.decision == Decision.ready


def test_an_order_older_than_two_hours_is_not_a_duplicate():
    out = decide(engine_input(milk_line(quantity="120"), history=(confirmed(121),), **ONE))

    assert "DUPLICATE_ORDER" not in codes(out)


def test_another_product_in_a_recent_order_is_not_a_duplicate():
    out = decide(engine_input(milk_line(quantity="120"), history=(confirmed(5, "2"),), **ONE))

    assert "DUPLICATE_ORDER" not in codes(out)


# --- Exact-fit choice ------------------------------------------------------------------

CASES = product("10", "Valio maito 10 l", litres="10")  # one sales unit is 10 l
LITRES = product("20", "Arla maito 1 l")


def named_cases(quantity: str = "15") -> LineRequest:
    return LineRequest(
        line_id="milk",
        product_id="10",
        quantity=Decimal(quantity),
        unit=RequestedUnit.l,
        needed_by=MONDAY,
    )


def exact_fit(*subs, quantity: str = "15"):
    return decide(
        engine_input(
            named_cases(quantity),
            candidates={"milk": ["10", *(p.product_id for p in subs)]},
            substitutes={"milk": [p.product_id for p in subs]},
            products=[CASES, *subs],
            offers=[offer("10", "9.00", 1000), offer("20", "1.10", 1000)],
        )
    )


def test_a_named_product_with_a_large_surplus_offers_the_exact_fit():
    out = exact_fit(LITRES)  # 15 l: two 10 l packs leave 5 l over

    assert out.decision == Decision.ready
    assert out.lines[0].product_id == "10"
    assert "ROUNDED_UP" not in codes(out)
    flag = next(f for f in out.flags if f.code == "EXACT_FIT_ALTERNATIVE")
    assert flag.kind == "choose"
    assert flag.flag_key == "EXACT_FIT_ALTERNATIVE:milk"
    assert [(o.option_id, o.label.en, o.line_total_cents) for o in flag.options] == [
        ("keep", "Valio maito 10 l, 2 pieces", 1800),
        ("exact:20", "Arla maito 1 l, 15 pieces", 1650),
    ]
    assert flag.text.en == (
        "Valio maito 10 l would leave a surplus. Arla maito 1 l fits the amount you need "
        "more exactly."
    )


def test_without_an_exact_fit_the_round_up_must_be_acknowledged():
    out = exact_fit()

    assert "EXACT_FIT_ALTERNATIVE" not in codes(out)
    assert "ROUNDED_UP" in codes(out)


def test_no_choice_when_the_named_product_fits():
    out = exact_fit(LITRES, quantity="20")

    assert codes(out) == []
    assert out.lines[0].product_id == "10"


def test_a_text_line_already_picks_the_exact_fit():
    out = decide(
        engine_input(
            milk_line(quantity="15", claims=[]),
            candidates={"milk": ["10", "20"]},
            products=[CASES, LITRES],
            offers=[offer("10", "9.00", 1000), offer("20", "1.10", 1000)],
        )
    )

    assert out.lines[0].product_id == "20"
    assert "EXACT_FIT_ALTERNATIVE" not in codes(out)
