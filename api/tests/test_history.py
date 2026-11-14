"""Demo kitchen types and their seeded order history (#32, docs/plans/61-order-history.md).

The generator tests need nothing. The account and quote tests use the test catalogue
(conftest.py), so a history keeps only the products in it.
"""

from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import OrderHistoryLine
from app.schemas import Exclusion, KitchenType, LineRequest
from app.schemas.tools import BuildQuoteRequest
from app.seed import history
from app.services import accounts, customers, quotes
from app.services.caller import Caller
from app.services.policy import get_rule_set
from app.settings import get_settings

NOW = get_rule_set().policy.business_time
STAGE = "+358401110000"
VEGAN = "+358400000003"  # hashes to the vegan catering type
MILK = "464201"  # Valio kevytmaito 1 l laktoositon, in the school kitchen's history
OAT_DRINK = "460825"  # Oatly Kaurajuoma, the test catalogue's only plant-based drink


@pytest.fixture
def stage_number(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_stage_phone", STAGE)
    return STAGE


def test_the_same_number_gets_the_same_type_and_history():
    kind = history.kitchen_type_for("+358401234567")
    assert kind == history.kitchen_type_for("+358401234567")
    assert history.generate("+358401234567", kind, NOW) == history.generate(
        "+358401234567", kind, NOW
    )


def test_numbers_spread_over_every_type():
    kinds = Counter(history.kitchen_type_for(f"+35840{n:07d}") for n in range(700))
    assert set(kinds) == set(KitchenType)


def test_the_stage_number_is_the_school_kitchen(stage_number):
    assert history.kitchen_type_for(stage_number) == KitchenType.school_kitchen


@pytest.mark.parametrize(
    ("kind", "orders"),
    [
        (KitchenType.school_kitchen, 8),
        (KitchenType.lunch_restaurant, 16),
        (KitchenType.cafe, 24),
        (KitchenType.tech_office, 4),
    ],
)
def test_each_type_orders_at_its_rhythm_for_eight_weeks(kind, orders):
    lines = history.generate("+358401234567", kind, NOW)
    dates = sorted({line.ordered_at for line in lines})
    assert len(dates) == orders
    assert dates[-1].date() < NOW.date()
    assert dates[0].date() >= NOW.date() - timedelta(weeks=8)


def test_core_items_are_in_every_order_and_quantities_vary_a_little():
    spec = history.kitchen_types()[KitchenType.school_kitchen]
    lines = history.generate("+358401234567", KitchenType.school_kitchen, NOW)
    milk = [line.quantity for line in lines if line.product_id == MILK]
    assert len(milk) == 8
    base = next(i.quantity for i in spec.items if i.product_id == MILK)
    assert all(abs(q - base) <= base * history._settings_shape()[1] + 1 for q in milk)
    assert len(set(milk)) > 1


async def test_a_new_account_gets_its_type_and_usual_items(db, stage_number):
    account = await accounts.create_demo_account(db, stage_number, [], "fi")

    assert account.kitchen_type == KitchenType.school_kitchen
    assert MILK in {item.product_id for item in account.usual_items}


def test_only_vegan_catering_has_default_exclusions():
    defaults = {
        k: s.default_exclusions for k, s in history.kitchen_types().items() if s.default_exclusions
    }
    assert defaults == {KitchenType.vegan_catering: (Exclusion.vegan,)}


async def test_a_new_vegan_catering_company_starts_vegan(db):
    assert history.kitchen_type_for(VEGAN) == KitchenType.vegan_catering
    account = await accounts.create_demo_account(db, VEGAN, [], "fi")

    assert account.new_company and account.exclusions == [Exclusion.vegan]
    assert (await accounts.me(db, account.user_id)).exclusions == [Exclusion.vegan]


async def test_a_vegan_catering_visitor_who_chose_keeps_the_choice(db):
    account = await accounts.create_demo_account(db, VEGAN, ["nut_free"], "fi")

    assert account.exclusions == [Exclusion.nut_free]


async def test_a_returning_vegan_catering_number_can_drop_vegan(db):
    await accounts.create_demo_account(db, VEGAN, [], "fi")
    account = await accounts.create_demo_account(db, VEGAN, [], "fi")

    assert not account.new_company and account.exclusions == []


async def test_a_milk_free_kitchen_gets_the_oat_drink_instead_of_milk(db, stage_number):
    account = await accounts.create_demo_account(db, stage_number, ["milk_free"], "fi")

    usual = {item.product_id for item in account.usual_items}
    assert MILK not in usual and OAT_DRINK in usual
    swapped = await db.scalar(
        select(OrderHistoryLine.replaces_product_id).where(
            OrderHistoryLine.company_id == account.company_id,
            OrderHistoryLine.product_id == OAT_DRINK,
        )
    )
    assert swapped == MILK


async def test_changing_the_exclusions_regenerates_the_history(db, stage_number):
    await accounts.create_demo_account(db, stage_number, ["milk_free"], "fi")
    account = await accounts.create_demo_account(db, stage_number, [], "fi")

    assert MILK in {item.product_id for item in account.usual_items}


async def test_my_usual_resolves_in_a_quote(db, stage_number):
    account = await accounts.create_demo_account(db, stage_number, [], "en")
    caller = Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=[],
        lang="en",
        channel="web",
    )
    context = await customers.get_customer_context(db, caller)
    assert context.kitchen_type == KitchenType.school_kitchen
    assert context.last_order

    line = LineRequest(
        line_id="l1",
        usual=True,
        text="kevytmaito",
        quantity=10,
        unit="l",
        needed_by=NOW.date() + timedelta(days=4),
    )
    response = await quotes.build_quote(db, caller, BuildQuoteRequest(lines=[line]), now=NOW)

    assert [quoted.product_id for quoted in response.lines] == [MILK]
