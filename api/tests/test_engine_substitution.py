"""Ranking, substitution and price (#39, technical-plan.md §4.2)."""

from decimal import Decimal

from app.engine import decide
from app.schemas import Decision, Exclusion, LineRequest, RequestedUnit
from tests.engine_fixtures import MILK_SEARCH, MONDAY, engine_input, milk_line, offer, product

# "Valio kevytmaito 1 l" is what the buyer named; it is out of stock in every test.
VALIO = product("100", "Valio kevytmaito 1 l").model_copy(update={"substitutions": ["300"]})
VALIO_HALF = product("101", "Valio kevytmaito 0,5 l", litres="0.5")
ARLA = product("300", "Arla kevytmaito 1 l")
SOY = product("400", "Alpro soijajuoma 1 l", allergens=(("AY", "CONTAINS"),))
OUT = offer("100", "1.00", None)


def named(quantity: str = "10", **kw) -> LineRequest:
    return LineRequest(
        line_id="milk",
        product_id="100",
        quantity=Decimal(quantity),
        unit=kw.pop("unit", RequestedUnit.l),
        needed_by=MONDAY,
        **kw,
    )


def run(subs, offers, line=None, **kw):
    products = [VALIO, *subs]
    ids = [p.product_id for p in subs]
    return decide(
        engine_input(
            line or named(),
            candidates={"milk": ["100", *ids]},
            substitutes={"milk": ids},
            products=products,
            offers=[OUT, *offers],
            **kw,
        )
    )


# --- The ladder ------------------------------------------------------------------------


def test_the_same_product_in_another_pack_is_swapped_automatically():
    out = run([VALIO_HALF], [offer("101", "0.55")])  # 1,10 €/l: exactly 10 % more

    assert out.decision == Decision.ready
    line = out.lines[0]
    assert line.product_id == "101"
    assert line.quantity_sales_units == 20
    assert "SUBSTITUTED_PACK_SIZE" in line.reason_codes
    flag = next(f for f in out.flags if f.code == "SUBSTITUTED_PACK_SIZE")
    assert flag.kind == "acknowledge"
    assert flag.text.en == (
        "Valio kevytmaito 1 l was replaced by the same product in another pack size: "
        "Valio kevytmaito 0,5 l."
    )
    assert line.reason_text.en.startswith("Valio kevytmaito 1 l is not available right now.")


def test_a_curated_substitute_is_swapped_automatically():
    out = run([ARLA], [offer("300", "1.05", 100)])

    assert out.decision == Decision.ready
    assert out.lines[0].product_id == "300"
    assert out.lines[0].reason_codes == ["SUBSTITUTED_CURATED"]
    assert [f.code for f in out.flags] == ["SUBSTITUTED_CURATED"]


def test_another_pack_is_tried_before_a_curated_pair_even_if_dearer():
    out = run([ARLA, VALIO_HALF], [offer("300", "1.00"), offer("101", "0.54")])

    assert out.lines[0].product_id == "101"
    assert [a.product_id for a in out.lines[0].alternatives] == ["300"]


def test_more_than_ten_percent_dearer_per_litre_asks_instead():
    out = run([ARLA], [offer("300", "1.11")])

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert out.clarification.question.en == (
        "Valio kevytmaito 1 l is not available right now. The substitute Arla kevytmaito 1 l "
        "costs 11% more per litre or kilo, so I didn't swap it automatically. "
        "Is it okay, €11.10 in total?"
    )
    assert [o.product_id for o in out.clarification.options] == ["300"]


def test_the_price_limit_compares_per_litre_not_per_pack():
    # 0,60 € for half a litre is 1,20 €/l: 20 % more, though the pack is cheaper.
    out = run([VALIO_HALF], [offer("101", "0.60")])

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert "20%" in out.clarification.question.en


def test_a_dearer_pack_falls_through_to_a_curated_pair_within_the_limit():
    out = run([VALIO_HALF, ARLA], [offer("101", "0.60"), offer("300", "1.02")])

    assert out.decision == Decision.ready
    assert out.lines[0].product_id == "300"


def test_a_substitute_that_adds_an_allergen_is_never_automatic():
    soy_curated = VALIO.model_copy(update={"substitutions": ["400"]})
    out = decide(
        engine_input(
            named(),
            candidates={"milk": ["100", "400"]},
            substitutes={"milk": ["400"]},
            products=[soy_curated, SOY],
            offers=[OUT, offer("400", "1.00")],
        )
    )

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert out.clarification.question.en.endswith(
        "Would Alpro soijajuoma 1 l work instead, €10.00 in total?"
    )


def test_prices_that_cant_be_compared_are_never_swapped_automatically():
    # Asked in sales units, and the substitute has no size in litres or kilos.
    no_size = product("300", "Arla maitojuoma").model_copy(update={"unit_conversions": []})
    out = run([no_size], [offer("300", "1.00")], line=named("10", unit=RequestedUnit.sales_unit))

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert "Would Arla maitojuoma work instead" in out.clarification.question.en


def test_a_similar_product_is_suggested_as_a_question():
    other = product("500", "Arla Luomu kevytmaito 1 l")
    out = run([other], [offer("500", "1.00")])

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert out.clarification.question.fi == (
        "Tuote Valio kevytmaito 1 l ei ole tällä hetkellä saatavilla. "
        "Käykö tilalle Arla Luomu kevytmaito 1 l, yhteensä 10,00\u00a0€?"
    )
    assert [o.line_total_cents for o in out.clarification.options] == [1000]


def test_a_milk_free_kitchen_is_asked_about_a_plant_drink_for_maito():
    oat = product(
        "600", "Kaurajuoma 1 l", category="10402", claims=(), allergens=(("AW", "CONTAINS"),)
    )
    out = decide(
        engine_input(
            milk_line(claims=[], quantity="10"),
            candidates={"milk": [*MILK_SEARCH[:2], "600"]},
            substitutes={"milk": ["600"]},
            products=[*[product(p, f"Maito {p} 1 l") for p in MILK_SEARCH[:2]], oat],
            offers=[offer(p, "1.00") for p in [*MILK_SEARCH[:2], "600"]],
            exclusions=(Exclusion.milk_free,),
        )
    )

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert out.clarification.question.en.startswith("Maito 464073 1 l contains milk")
    assert "Would Kaurajuoma 1 l work instead" in out.clarification.question.en
    assert [o.product_id for o in out.clarification.options] == ["600"]


def test_similar_products_keep_the_candidate_order_over_price():
    first = product("500", "Kaurajuoma 1 l")
    cheap = product("501", "Kaurapohjainen kaakaojuoma 1 l")
    out = run([first, cheap], [offer("500", "1.50"), offer("501", "0.90")])

    assert out.clarification is not None
    assert [o.product_id for o in out.clarification.options] == ["500", "501"]


def test_no_usable_substitute_requests_a_callback():
    out = run([ARLA], [offer("300", "1.00", None)])

    assert out.decision == Decision.rejected
    rejection = out.rejections[0]
    assert rejection.reason_code == "CALLBACK_REQUESTED"
    assert rejection.next_step.en == "Customer service will contact you."


def test_without_substitutes_the_original_reason_rejects():
    out = run([], [])

    assert out.decision == Decision.rejected
    assert out.rejections[0].reason_code == "UNAVAILABLE"


def test_substitutes_are_ignored_while_the_line_can_be_filled():
    in_stock = decide(
        engine_input(
            named(),
            candidates={"milk": ["100", "300"]},
            substitutes={"milk": ["300"]},
            products=[VALIO, ARLA],
            offers=[offer("100", "1.00", 100), offer("300", "0.50", 100)],
        )
    )
    assert in_stock.lines[0].product_id == "100"
    assert in_stock.lines[0].reason_codes == []


# --- Missing price ---------------------------------------------------------------------


def test_the_best_hit_without_a_price_asks_to_try_again():
    offers = [offer(pid, "1.00") for pid in MILK_SEARCH]
    offers[0] = offer(MILK_SEARCH[0], None, ok=False)
    out = decide(engine_input(offers=offers))

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert "try again" in out.clarification.question.en


def test_a_lower_hit_without_a_price_is_skipped_and_counted():
    offers = [offer(pid, "1.00") for pid in MILK_SEARCH]
    offers[-1] = offer(MILK_SEARCH[-1], None, ok=False)
    out = decide(engine_input(offers=offers))

    assert out.decision == Decision.ready
    removed = {r.reason_code: r for r in out.lines[0].trace.removed}
    assert [p.product_id for p in removed["OFFER_UNAVAILABLE"].products] == [MILK_SEARCH[-1]]


def test_a_blocked_top_hit_and_a_failed_offer_ask_rather_than_reject():
    milk = product("1", "Maito 1 l", claims=())
    oat = product("2", "Kaurajuoma 1 l", claims=(), allergens=())
    out = decide(
        engine_input(
            milk_line(claims=[]),
            candidates={"milk": ["1", "2"]},
            products=[milk, oat],
            offers=[offer("1", "1.00"), offer("2", None, ok=False)],
            exclusions=(Exclusion.milk_free,),
        )
    )

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert "Kaurajuoma 1 l" in out.clarification.question.en
    assert "try again" in out.clarification.question.en


# --- Price -----------------------------------------------------------------------------


def test_the_line_total_is_rounded_up_to_the_next_cent():
    p = product("1", "Maito 1 l")
    out = decide(
        engine_input(
            milk_line(quantity="7"),
            candidates={"milk": ["1"]},
            products=[p],
            offers=[offer("1", "0.333")],
        )
    )

    line = out.lines[0]
    assert line.unit_price_gross == Decimal("0.333")
    assert line.line_total_cents == 234  # 7 × 0,333 = 2,331 €
    assert out.total_cents == 234


def test_the_order_total_is_the_sum_of_the_rounded_line_totals():
    p = product("1", "Maito 1 l")
    lines = [milk_line("a", quantity="1"), milk_line("b", quantity="1")]
    out = decide(
        engine_input(
            *lines,
            candidates={"a": ["1"], "b": ["1"]},
            products=[p],
            offers=[offer("1", "0.333")],
        )
    )

    assert [line.line_total_cents for line in out.lines] == [34, 34]
    assert out.total_cents == 68


def test_a_price_not_valid_on_the_delivery_date_removes_the_product():
    p = product("1", "Maito 1 l")
    expired = offer("1", "1.00").model_copy(update={"price_valid_to": MONDAY.replace(day=15)})
    out = decide(engine_input(candidates={"milk": ["1"]}, products=[p], offers=[expired]))

    assert out.decision == Decision.rejected
    assert out.rejections[0].reason_code == "PRICE_NOT_VALID"


# --- Ranking ---------------------------------------------------------------------------


def test_finnish_origin_breaks_a_tie():
    abroad = product("1", "Maito A 1 l").model_copy(update={"origin": "SE"})
    home = product("2", "Maito B 1 l")
    out = decide(
        engine_input(
            candidates={"milk": ["1", "2"]},
            products=[abroad, home],
            offers=[offer("1", "1.00"), offer("2", "1.00")],
        )
    )

    assert out.lines[0].product_id == "2"


def test_the_trace_lists_the_ranked_candidates_and_the_removed_products():
    trace = decide(engine_input()).lines[0].trace

    assert [(c.rank, c.product_id, c.chosen) for c in trace.ranked] == [
        (1, "464306", True),
        (2, "464119", False),
        (3, "464201", False),
        (4, "464073", False),
    ]
    assert trace.ranked[0].price_per_base_unit == Decimal("1.1500")
    assert {r.reason_code: [p.product_id for p in r.products] for r in trace.removed} == {
        "UNAVAILABLE": ["464440"],
        "PARTIAL_STOCK": ["462775", "463380"],
    }
