from app.engine import decide
from app.schemas import Decision
from tests.contract_fixtures import RULES, engine_input, line


def test_milk_line_is_ready():
    out = decide(engine_input(line("l1", "maito", "2.4", group="Mon")))
    assert out.decision == Decision.ready
    [priced] = out.lines
    assert priced.line_id == "l1"
    assert priced.group == "Mon"
    assert priced.product_id == "464306"
    assert priced.quantity_sales_units == 3
    assert priced.line_total_cents == 345
    assert priced.delivery_date == priced.asked.needed_by
    assert [a.product_id for a in priced.alternatives] == ["464073"]
    assert out.total_cents == 345
    assert [f.flag_key for f in out.flags] == ["stock_unverified:l1"]
    assert out.groups[0].subtotal_cents == 345
    assert out.delivery is not None
    assert "3,45 €" in out.speak.fi and "€3.45" in out.speak.en
    assert out.rules_ref == RULES.ref


def test_unclear_needs_clarification():
    out = decide(engine_input(line("l1"), line("l2", "Unclear milk")))
    assert out.decision == Decision.needs_clarification
    assert out.lines == []
    assert out.clarification is not None
    assert out.clarification.line_id == "l2"
    assert [o.product_id for o in out.clarification.options] == ["464306", "464073"]


def test_reject_lists_the_other_lines():
    out = decide(engine_input(line("l1"), line("l2", "please REJECT this")))
    assert out.decision == Decision.rejected
    assert [r.line_id for r in out.rejections] == ["l2"]
    assert out.rejections[0].reason_code == "UNAVAILABLE"
    assert [ln.line_id for ln in out.lines] == ["l1"]


def test_clarification_wins_over_rejection():
    out = decide(engine_input(line("l1", "reject"), line("l2", "unclear")))
    assert out.decision == Decision.needs_clarification


def test_same_input_same_output():
    data = engine_input(line("l1"), line("l2", "voi", "5", group="A"))
    assert decide(data) == decide(data)
    assert decide(data).model_dump_json() == decide(data).model_dump_json()
