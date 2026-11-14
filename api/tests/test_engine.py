"""The engine pipeline on hand-built inputs (#36). No database, no network."""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.engine import decide, input_errors
from app.schemas import (
    Claim,
    Decision,
    Exclusion,
    Localized,
    RequestedUnit,
    StockStatus,
    UsualItem,
)
from tests.engine_fixtures import (
    MILK_OFFERS,
    MILK_PRODUCTS,
    MILK_SEARCH,
    engine_input,
    milk_line,
    offer,
    product,
)


def test_milk_scenario_picks_the_cheapest_lactose_free_milk():
    out = decide(engine_input())

    assert out.decision == Decision.ready
    [line] = out.lines
    assert line.product_id == "464306"
    assert line.quantity_sales_units == 1000
    assert line.line_total_cents == 115000
    assert line.unit_price_gross == Decimal("1.15")
    assert line.price_per_base_unit == Decimal("1.15")
    assert line.base_unit == "l"
    assert line.delivery_date == date(2026, 11, 16)
    assert line.stock_status == StockStatus.unverified
    assert [a.product_id for a in line.alternatives] == ["464119", "464201"]
    assert out.total_cents == 115000
    assert out.rules_ref.startswith("2026-11-14.")


def test_milk_trace_counts_each_candidate_once_in_pipeline_order():
    trace = decide(engine_input()).lines[0].trace

    assert trace.found == 7
    assert [(r.reason_code, r.count) for r in trace.removed] == [
        ("UNAVAILABLE", 1),
        ("PARTIAL_STOCK", 2),
    ]
    assert trace.left == 4
    assert trace.removed[0].text.en == "not available"


def test_unverified_stock_is_flagged_for_acknowledgement():
    out = decide(engine_input())

    assert [(f.code, f.flag_key, f.kind) for f in out.flags] == [
        ("AVAILABILITY_UNVERIFIED", "AVAILABILITY_UNVERIFIED:milk", "acknowledge")
    ]


def test_ready_speech_names_the_top_pick_and_one_alternative():
    speak = decide(engine_input()).speak

    assert speak.fi == (
        "Tarjous on valmis. Valio Arki kevytmaito 1 l, 1000 kappaletta, 1\u00a0150,00\u00a0€."
        " Vaihtoehtona Valio rasvaton maito 1 l UHT, 1\u00a0512,00\u00a0€."
        " Toimitus maanantaina 16.11., yhteensä 1\u00a0150,00\u00a0€."
        " Tarkistettavia kohtia vahvistussivulla: 1."
    )
    assert speak.en == (
        "The quote is ready. Valio Arki kevytmaito 1 l, 1000 pieces, €1,150.00."
        " Alternatively Valio rasvaton maito 1 l UHT, €1,512.00."
        " Delivery Monday 16 November, total €1,150.00."
        " Notes to check on the confirmation page: 1."
    )


def test_a_long_order_names_three_lines_and_counts_the_rest():
    lines = [milk_line(f"l{i}", quantity="10") for i in range(5)]
    out = decide(engine_input(*lines, candidates={f"l{i}": MILK_SEARCH for i in range(5)}))

    assert out.decision == Decision.ready
    assert out.speak.en.count("Valio Arki kevytmaito 1 l, 10 pieces") == 3
    assert "More products: 2." in out.speak.en
    assert "Alternatively" not in out.speak.en


def test_case_products_are_converted_through_the_pack_size():
    only_cases = engine_input(candidates={"milk": ["464119"]})
    [line] = decide(only_cases).lines

    assert line.sales_unit == "KI"
    assert line.quantity_sales_units == 100
    assert line.line_total_cents == 151200
    assert line.price_per_base_unit == Decimal("1.512")


def test_rounding_up_is_explained_on_the_line():
    data = engine_input(milk_line(quantity="995"), candidates={"milk": ["464119"]})
    [line] = decide(data).lines

    assert line.quantity_sales_units == 100
    assert line.quantity_in_asked_unit == Decimal("1000")
    assert "ROUNDED_UP" in line.reason_codes
    assert "100" in line.reason_text.en


def test_a_package_word_converts_to_sales_units():
    line = milk_line(quantity="2", unit=RequestedUnit.package, package_word="laatikkoa")
    [priced] = decide(engine_input(line, candidates={"milk": ["464119"]})).lines

    assert priced.quantity_sales_units == 2
    assert priced.quantity_in_asked_unit == Decimal("2")


def test_a_milk_free_kitchen_rejects_milk_with_a_next_step():
    out = decide(engine_input(exclusions=(Exclusion.milk_free,)))

    assert out.decision == Decision.rejected
    [rejection] = out.rejections
    assert rejection.reason_code == "ALLERGEN_CONFLICT"
    assert "maitoa" in rejection.text.fi and "milk-free" in rejection.text.en
    assert rejection.next_step.en
    assert out.speak.en.startswith("Unfortunately I can't order any")


def test_lactose_free_kitchen_needs_the_claim_on_milk_products():
    no_claim = [product("1", "Maito", claims=())]
    out = decide(
        engine_input(
            milk_line(claims=[]),
            candidates={"milk": ["1"]},
            products=no_claim,
            offers=[offer("1", "1.00")],
            exclusions=(Exclusion.lactose_free,),
        )
    )

    assert out.rejections[0].reason_code == "ALLERGEN_CONFLICT"


def test_one_failed_line_does_not_block_the_rest():
    butter = milk_line(
        "butter", product_id="500", text=None, claims=[], quantity="5", unit=RequestedUnit.kg
    )
    data = engine_input(
        milk_line(),
        butter,
        products=[*MILK_PRODUCTS, product("500", "Valio voi 500 g", category="20100")],
        offers=[*MILK_OFFERS, offer("500", "4.20", None)],
    )
    out = decide(data)

    assert out.decision == Decision.ready
    assert [line.line_id for line in out.lines] == ["milk"]
    [rejection] = out.rejections
    assert (rejection.line_id, rejection.reason_code) == ("butter", "UNAVAILABLE")
    assert "Valio voi 500 g" in out.speak.fi
    assert "customer service can contact you" in out.speak.en


def test_candidates_spanning_categories_ask_which_one():
    cream = [
        product("c1", "Ruokakerma", category="11100", claims=()),
        product("c2", "Vispikerma", category="11200", claims=()),
        product("c3", "Kevyt ruokakerma", category="11100", claims=()),
    ]
    data = engine_input(
        milk_line("cream", text="kerma", claims=[], quantity="10"),
        candidates={"cream": ["c1", "c2", "c3"]},
        products=cream,
        offers=[offer("c1", "2.00"), offer("c2", "3.00"), offer("c3", "1.50")],
    )
    out = decide(data)

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert [o.product_id for o in out.clarification.options] == ["c3", "c2"]
    assert out.speak == out.clarification.question


def test_a_category_on_the_line_skips_the_ambiguity_question():
    cream = [
        product("c1", "Ruokakerma", category="11100"),
        product("c2", "Vispi", category="11200"),
    ]
    data = engine_input(
        milk_line("cream", text="kerma", category="11100"),
        candidates={"cream": ["c1", "c2"]},
        products=cream,
        offers=[offer("c1", "2.00"), offer("c2", "3.00")],
    )

    assert decide(data).decision == Decision.ready


def test_a_clarification_wins_over_ready_lines():
    data = engine_input(
        milk_line(),
        milk_line("other", text="jotain"),
        candidates={"milk": MILK_SEARCH, "other": []},
    )
    out = decide(data)

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None and out.clarification.line_id == "other"


def test_when_no_price_could_be_fetched_the_agent_offers_to_try_again():
    failed = [offer(pid, None, ok=False) for pid in MILK_SEARCH]
    out = decide(engine_input(offers=failed))

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert "try again" in out.clarification.question.en


def test_an_unknown_product_id_is_rejected():
    line = milk_line(product_id="999999", text=None, claims=[])
    out = decide(engine_input(line))

    assert out.rejections[0].reason_code == "PRODUCT_NOT_FOUND"


def test_past_the_closing_time_is_rejected():
    late = [offer("464306", "1.15", closing="2026-11-12T08:00:00+02:00")]
    out = decide(engine_input(candidates={"milk": ["464306"]}, offers=late))

    assert out.rejections[0].reason_code == "PAST_CLOSING_TIME"


def test_too_late_for_the_needed_date_is_rejected():
    late = [offer("464306", "1.15", available=date(2026, 11, 20))]
    out = decide(engine_input(candidates={"milk": ["464306"]}, offers=late))

    assert out.rejections[0].reason_code == "DELIVERY_DATE_UNREACHABLE"


def test_my_usual_uses_the_matching_usual_item():
    usual = (
        UsualItem(
            product_id="464306",
            name=Localized(fi="Valio Arki kevytmaito 1 l", en="Valio Arki semi skimmed 1 l"),
            quantity=Decimal(20),
            unit="ST",
        ),
    )
    line = milk_line(usual=True, text="arki", claims=[], quantity="20", unit=RequestedUnit.piece)
    out = decide(engine_input(line, usual=usual))

    assert out.lines[0].product_id == "464306"
    assert out.lines[0].quantity_sales_units == 20


def test_no_matching_usual_item_asks():
    line = milk_line(usual=True, text="kerma", claims=[])
    out = decide(engine_input(line))

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None and out.clarification.options == []


def test_lines_sharing_a_line_id_are_rejected_and_the_others_are_not():
    out = decide(engine_input(milk_line(), milk_line(), milk_line(line_id="other")))

    assert [(r.line_id, r.reason_code) for r in out.rejections] == [
        ("milk", "DUPLICATE_LINE_ID"),
        ("milk", "DUPLICATE_LINE_ID"),
    ]
    # The third line has its own id: it goes on to the product search (nothing found here).
    assert out.clarification is not None and out.clarification.line_id == "other"


def test_a_date_before_the_business_day_is_rejected_with_its_own_code():
    out = decide(engine_input(milk_line(needed_by=date(2026, 11, 11))))

    [rejection] = out.rejections
    assert rejection.reason_code == "NEEDED_BY_PAST"
    assert "needed_by" in rejection.text.en and "needed_by" in rejection.next_step.en


def test_a_line_must_say_what_it_wants():
    out = decide(engine_input(milk_line(text=None, claims=[Claim.lactose_free])))

    assert out.rejections[0].reason_code == "LINE_EMPTY"


def test_a_package_without_its_word_is_rejected_and_says_what_to_send():
    out = decide(engine_input(milk_line(unit="package", package_word=None)))

    [rejection] = out.rejections
    assert rejection.reason_code == "PACKAGE_WORD_MISSING"
    assert "package_word" in rejection.next_step.en


def test_input_errors_lists_every_error_of_every_line_in_order():
    lines = [
        milk_line(line_id="a"),
        milk_line(line_id="b", unit="package", package_word=None, needed_by=date(2026, 11, 11)),
        milk_line(line_id="c", text=None, claims=[]),
        milk_line(line_id="a"),
    ]

    errors = input_errors(lines, date(2026, 11, 13))

    assert [(lines[i].line_id, code.value) for i, code in errors] == [
        ("a", "DUPLICATE_LINE_ID"),
        ("b", "PACKAGE_WORD_MISSING"),
        ("b", "NEEDED_BY_PAST"),
        ("c", "LINE_EMPTY"),
        ("a", "DUPLICATE_LINE_ID"),
    ]


def test_a_whole_recipe_line_is_not_an_empty_line():
    line = milk_line(text=None, claims=[], recipe_ref={"recipe_id": "38100", "portions": 120})

    assert input_errors([line], date(2026, 11, 13)) == []


def test_same_input_gives_the_same_output_whatever_the_list_order():
    forward = decide(engine_input())
    backward = decide(
        engine_input(products=list(reversed(MILK_PRODUCTS)), offers=list(reversed(MILK_OFFERS)))
    )

    assert forward == backward
    assert forward.model_dump_json() == decide(engine_input()).model_dump_json()


def test_the_engine_imports_nothing_impure():
    forbidden = {"sqlalchemy", "httpx", "requests", "random", "time", "app.db", "app.services",
                 "app.adapters", "app.settings", "os", "pathlib", "secrets", "uuid"}  # fmt: skip
    engine_dir = Path(__file__).resolve().parents[1] / "app" / "engine"
    for source in engine_dir.glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                assert not any(name == f or name.startswith(f + ".") for f in forbidden), (
                    f"{source.name} imports {name}"
                )
    assert "datetime.now" not in "".join(p.read_text() for p in engine_dir.glob("*.py"))
