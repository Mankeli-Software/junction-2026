"""The allergen and diet filter (#37): every rule in vision §10 on hand-built products."""

import pytest

from app.engine import decide
from app.engine.filters import may_block
from app.schemas import Claim, Decision, EngineOutput, Exclusion, Localized, UsualItem
from tests.engine_fixtures import RULES, engine_input, milk_line, offer, product

NUT_SET = ["AN", "SA", "SH", "SW", "SC", "SP", "SM", "SR", "ST", "AP", "PN"]


def order(*products, exclusions=(), claims=()) -> EngineOutput:
    """One line for "maito" over the given products, all in stock at the same price."""
    return decide(
        engine_input(
            milk_line(claims=list(claims)),
            candidates={"milk": [p.product_id for p in products]},
            products=list(products),
            offers=[offer(p.product_id, "1.00") for p in products],
            exclusions=tuple(exclusions),
        )
    )


def chosen(out: EngineOutput) -> str | None:
    return out.lines[0].product_id if out.lines else None


def blocked(out: EngineOutput) -> bool:
    return out.decision == Decision.rejected and out.rejections[0].reason_code in {
        "ALLERGEN_CONFLICT",
        "DIET_CLAIM_MISSING",
    }


# --- Containment levels ---------------------------------------------------------------


@pytest.mark.parametrize("containment", ["CONTAINS", "MAY_CONTAIN"])
def test_a_listed_excluded_code_blocks(containment):
    out = order(
        product("1", "Munakas", allergens=(("AE", containment),)), exclusions=[Exclusion.egg_free]
    )

    assert blocked(out)
    assert out.rejections[0].reason_code == "ALLERGEN_CONFLICT"


def test_may_contain_is_named_in_the_reason():
    out = order(
        product("1", "Keksi", allergens=(("SH", "MAY_CONTAIN"),)), exclusions=[Exclusion.nut_free]
    )

    assert "may contain" in out.rejections[0].text.en


def test_free_from_never_blocks():
    out = order(
        product("1", "Maito", allergens=(("AM", "FREE_FROM"),)), exclusions=[Exclusion.milk_free]
    )

    assert chosen(out) == "1"


@pytest.mark.parametrize("exclusion", list(Exclusion))
def test_x99_never_blocks(exclusion):
    claims = (Claim.lactose_free, Claim.gluten_free, Claim.vegan)
    out = order(
        product("1", "Vesi", claims=claims, allergens=(("X99", "CONTAINS"),)),
        exclusions=[exclusion],
    )

    assert chosen(out) == "1"
    assert all(f.code != "ALLERGEN_NO_LISTING" for f in out.flags)


def test_only_the_product_s_own_listing_counts():
    """A product in a milk category but with no milk listed is not blocked (no inference)."""
    out = order(product("1", "Kaurajuoma", category="10400", allergens=(("GO", "CONTAINS"),)),
                exclusions=[Exclusion.milk_free])  # fmt: skip

    assert chosen(out) == "1"


# --- Milk-free versus lactose-free ----------------------------------------------------


def test_milk_free_blocks_milk():
    out = order(product("1", "Maito", claims=()), exclusions=[Exclusion.milk_free])

    assert blocked(out)


def test_milk_free_blocks_lactose_alone():
    out = order(
        product("1", "Juusto", allergens=(("ML", "CONTAINS"),)), exclusions=[Exclusion.milk_free]
    )

    assert blocked(out)


def test_a_lactose_free_claim_never_makes_milk_milk_free():
    out = order(
        product("1", "Laktoositon maito", claims=(Claim.lactose_free,)),
        exclusions=[Exclusion.milk_free],
    )

    assert blocked(out)


def test_lactose_free_accepts_milk_with_the_lactose_claim():
    out = order(
        product("1", "Laktoositon maito", claims=(Claim.lactose_free,)),
        exclusions=[Exclusion.lactose_free],
    )

    assert chosen(out) == "1"


def test_lactose_free_blocks_milk_without_the_claim():
    out = order(product("1", "Maito", claims=()), exclusions=[Exclusion.lactose_free])

    assert blocked(out)


def test_lactose_free_blocks_listed_lactose_even_with_the_claim():
    out = order(
        product("1", "Ristiriita", claims=(Claim.lactose_free,), allergens=(("ML", "CONTAINS"),)),
        exclusions=[Exclusion.lactose_free],
    )

    assert blocked(out)


# --- Nuts -------------------------------------------------------------------------------


@pytest.mark.parametrize("code", NUT_SET)
def test_nut_free_blocks_every_nut_code(code):
    out = order(
        product("1", "Pähkinäsekoitus", allergens=((code, "CONTAINS"),)),
        exclusions=[Exclusion.nut_free],
    )

    assert blocked(out)


def test_coconut_is_not_a_nut():
    out = order(
        product("1", "Kookosmaito", allergens=(("SO", "CONTAINS"),)),
        exclusions=[Exclusion.nut_free],
    )

    assert chosen(out) == "1"


def test_cocoa_is_not_a_nut():
    out = order(
        product("1", "Kaakao", allergens=(("NC", "CONTAINS"),)), exclusions=[Exclusion.nut_free]
    )

    assert chosen(out) == "1"


# --- Gluten and vegan -------------------------------------------------------------------


def test_gluten_free_blocks_aw_even_with_the_claim():
    out = order(
        product("1", "Leipä", claims=(Claim.gluten_free,), allergens=(("AW", "CONTAINS"),)),
        exclusions=[Exclusion.gluten_free],
    )

    assert blocked(out)


@pytest.mark.parametrize("code", ["UW", "NR", "GB", "GO", "GS", "GK"])
def test_a_gluten_cereal_needs_the_gluten_claim(code):
    without = order(product("1", "Puuro", claims=(), allergens=((code, "CONTAINS"),)),
                    exclusions=[Exclusion.gluten_free])  # fmt: skip
    with_claim = order(
        product(
            "1", "Gluteeniton puuro", claims=(Claim.gluten_free,), allergens=((code, "CONTAINS"),)
        ),  # fmt: skip
        exclusions=[Exclusion.gluten_free],
    )

    assert blocked(without)
    assert chosen(with_claim) == "1"


def test_vegan_needs_the_vegan_claim():
    out = order(product("1", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),)),
                exclusions=[Exclusion.vegan])  # fmt: skip

    assert out.rejections[0].reason_code == "DIET_CLAIM_MISSING"


def test_a_vegan_claim_never_clears_a_listed_animal_code():
    out = order(product("1", "Ristiriita", claims=(Claim.vegan,)), exclusions=[Exclusion.vegan])

    assert out.rejections[0].reason_code == "ALLERGEN_CONFLICT"


def test_a_conflict_moves_on_to_a_safe_product():
    """Blocking is per candidate: the next safe product is chosen, the trace counts the block."""
    milk = product("1", "Maito", claims=())
    oat = product("2", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    out = order(milk, oat, exclusions=[Exclusion.milk_free])

    assert chosen(out) == "2"
    assert [(r.reason_code, r.count) for r in out.lines[0].trace.removed] == [
        ("ALLERGEN_CONFLICT", 1)
    ]


# --- No listing and UNDECLARED: orderable, one notice per order ---------------------------


def no_listing_flags(out: EngineOutput):
    return [f for f in out.flags if f.code == "ALLERGEN_NO_LISTING"]


def test_no_listing_is_orderable_and_flagged():
    out = order(product("1", "Omena", claims=(), allergens=()), exclusions=[Exclusion.milk_free])

    assert chosen(out) == "1"
    [flag] = no_listing_flags(out)
    assert (flag.flag_key, flag.kind, flag.line_ids) == (
        "ALLERGEN_NO_LISTING",
        "acknowledge",
        ["milk"],
    )
    assert "Omena" in flag.text.en and "milk-free kitchen" in flag.text.en
    assert "maidoton" in flag.text.fi


def test_no_listing_is_not_flagged_without_an_exclusion():
    out = order(product("1", "Omena", claims=(), allergens=()))

    assert no_listing_flags(out) == []


def test_a_claim_does_not_replace_a_listing():
    out = order(product("1", "Kaurajuoma", claims=(Claim.vegan,), allergens=()),
                exclusions=[Exclusion.vegan])  # fmt: skip

    assert chosen(out) == "1"
    assert len(no_listing_flags(out)) == 1


def test_undeclared_for_an_excluded_code_is_orderable_and_flagged():
    out = order(product("1", "Keksi", claims=(), allergens=(("SH", "UNDECLARED"),)),
                exclusions=[Exclusion.nut_free])  # fmt: skip

    assert chosen(out) == "1"
    assert len(no_listing_flags(out)) == 1


def test_undeclared_for_an_unrelated_code_is_not_flagged():
    out = order(product("1", "Kookosjuoma", claims=(), allergens=(("SO", "UNDECLARED"),)),
                exclusions=[Exclusion.milk_free])  # fmt: skip

    assert chosen(out) == "1"
    assert no_listing_flags(out) == []


def test_undeclared_for_a_claim_cleared_code_is_flagged():
    """UW is checked by gluten-free (cleared by the claim), so undetermined UW is still unknown."""
    out = order(
        product("1", "Puuro", claims=(Claim.gluten_free,), allergens=(("UW", "UNDECLARED"),)),
        exclusions=[Exclusion.gluten_free],
    )

    assert len(no_listing_flags(out)) == 1


def test_one_notice_lists_every_unlisted_product_and_every_choice():
    apple = product("a", "Omena", claims=(), allergens=())
    pear = product("p", "Päärynä", claims=(), allergens=())
    milk = product("m", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    lines = [milk_line(pid, product_id=pid, text=None, claims=[]) for pid in ("a", "m", "p")]
    out = decide(
        engine_input(
            *lines,
            candidates={},
            products=[apple, pear, milk],
            offers=[offer(p, "1.00") for p in ("a", "m", "p")],
            exclusions=(Exclusion.nut_free, Exclusion.milk_free),
        )
    )

    [flag] = no_listing_flags(out)
    assert flag.line_ids == ["a", "p"]
    assert "Omena, Päärynä" in flag.text.en
    assert "milk-free, nut-free kitchen" in flag.text.en
    assert flag is out.flags[-1]


def test_having_a_listing_is_not_a_ranking_factor():
    listed = product("1", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    unlisted = product("2", "Kaurajuoma 2", claims=(), allergens=())
    data = engine_input(
        milk_line(claims=[]),
        candidates={"milk": ["1", "2"]},
        products=[listed, unlisted],
        offers=[offer("1", "1.10"), offer("2", "1.00")],
        exclusions=(Exclusion.milk_free,),
    )
    out = decide(data)

    assert chosen(out) == "2"
    assert len(no_listing_flags(out)) == 1


def test_an_unlisted_alternative_does_not_raise_the_notice():
    listed = product("1", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    unlisted = product("2", "Kaurajuoma 2", claims=(), allergens=())
    data = engine_input(
        milk_line(claims=[]),
        candidates={"milk": ["1", "2"]},
        products=[listed, unlisted],
        offers=[offer("1", "1.00"), offer("2", "1.10")],
        exclusions=(Exclusion.milk_free,),
    )
    out = decide(data)

    assert chosen(out) == "1"
    assert [a.product_id for a in out.lines[0].alternatives] == ["2"]
    assert no_listing_flags(out) == []


# --- Substitutes and other offered options go through the same filter --------------------


def test_offered_options_are_filtered_for_the_kitchen():
    """Every product offered to the buyer, not just the chosen one, passes the same filter.
    The substitution step (#39) uses the same check."""
    milk = product("1", "Arki maito", claims=())
    oat = product("2", "Arki kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    soy = product("3", "Arki soijajuoma", claims=(), allergens=(("AY", "CONTAINS"),))
    usual = tuple(
        UsualItem(product_id=p.product_id, name=p.name, quantity=1, unit="ST")
        for p in (milk, oat, soy)
    )
    out = decide(
        engine_input(
            milk_line(usual=True, text="arki", claims=[]),
            candidates={},
            products=[milk, oat, soy],
            offers=[offer(p, "1.00") for p in ("1", "2", "3")],
            exclusions=(Exclusion.milk_free,),
            usual=usual,
        )
    )

    assert out.decision == Decision.needs_clarification
    assert out.clarification is not None
    assert [o.product_id for o in out.clarification.options] == ["2", "3"]


def test_alternatives_are_filtered_for_the_kitchen():
    milk = product("1", "Maito", claims=())
    oat = product("2", "Kaurajuoma", claims=(), allergens=(("GO", "CONTAINS"),))
    out = order(milk, oat, exclusions=[Exclusion.milk_free])

    assert out.lines[0].alternatives == []


def test_the_notice_text_is_localized():
    out = order(product("1", "Omena", claims=(), allergens=()), exclusions=[Exclusion.nut_free])

    [flag] = no_listing_flags(out)
    assert isinstance(flag.text, Localized)
    assert "pähkinätön" in flag.text.fi


# --- may_block agrees with the engine (#83) -------------------------------------------

M, LF, GF, V = Exclusion.milk_free, Exclusion.lactose_free, Exclusion.gluten_free, Exclusion.vegan
N = Exclusion.nut_free


@pytest.mark.parametrize(
    ("allergens", "claims", "exclusions", "expected"),
    [
        ((), (), [], False),
        ((), (), [M, LF, GF, N], False),  # no listing: kept, with a notice
        ((("AM", "CONTAINS"),), (), [], False),  # no exclusion
        ((("AM", "CONTAINS"),), (), [M], True),
        ((("AM", "MAY_CONTAIN"),), (), [M], True),
        ((("AM", "FREE_FROM"),), (), [M], False),
        ((("AM", "CONTAINS"),), (), [LF], True),
        ((("AM", "CONTAINS"),), (Claim.lactose_free,), [LF], False),
        ((("AM", "CONTAINS"),), (Claim.lactose_free,), [M], True),
        ((("ML", "CONTAINS"),), (Claim.lactose_free,), [LF], True),
        ((("AW", "MAY_CONTAIN"),), (Claim.gluten_free,), [GF], True),
        ((("GO", "CONTAINS"),), (), [GF], True),
        ((("GO", "CONTAINS"),), (Claim.gluten_free,), [GF], False),
        ((("GO", "CONTAINS"),), (Claim.gluten_free,), [M], False),
        ((("PN", "MAY_CONTAIN"),), (), [N], True),
        ((("AE", "FREE_FROM"),), (), [N], False),
        ((("GO", "CONTAINS"),), (), [V], True),  # vegan requires the claim
        ((("GO", "CONTAINS"),), (Claim.vegan,), [V], False),
        ((("AE", "CONTAINS"),), (Claim.vegan,), [V], True),
        ((("AM", "CONTAINS"),), (Claim.lactose_free,), [N, LF, V], True),
    ],
)
def test_may_block_agrees_with_the_engine(allergens, claims, exclusions, expected):
    p = product("1", "Tuote", claims=claims, allergens=allergens)

    assert may_block(p, exclusions, RULES) is expected
    assert blocked(order(p, exclusions=exclusions)) is expected
