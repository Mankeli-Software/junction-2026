import inspect
import json
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app import schemas
from app.schemas import tools
from tests.contract_fixtures import RULES, engine_input, line

MODELS = [
    obj
    for obj in vars(schemas).values()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not schemas.StrictModel
]
TOOL_MODELS = [
    obj
    for obj in vars(tools).values()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == tools.__name__
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_model_rejects_unknown_fields(model):
    assert model.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError) as err:
        model.model_validate({"not_a_field": 1})
    assert any(e["type"] == "extra_forbidden" for e in err.value.errors())


def test_decimal_dumps_as_json_number_and_round_trips():
    dumped = RULES.model_dump_json()
    raw = json.loads(dumped)
    assert raw["round_up_max_ratio"] == 0.02
    assert '"round_up_max_ratio":0.02' in dumped

    one = line(quantity="1.15")
    assert json.loads(one.model_dump_json())["quantity"] == 1.15
    back = schemas.LineRequest.model_validate_json(one.model_dump_json())
    assert back.quantity == Decimal("1.15")
    assert isinstance(back.quantity, Decimal)


def test_python_dump_keeps_decimal():
    assert isinstance(RULES.model_dump()["round_up_max_ratio"], Decimal)


@pytest.mark.parametrize("model", TOOL_MODELS, ids=lambda m: m.__name__)
def test_tool_models_have_json_schema(model):
    schema = model.model_json_schema()
    assert schema["type"] == "object"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quantity": "0"},
        {"quantity": "100001"},
        {"text": "x" * 201},
        {"line_id": ""},
        {"line_id": "x" * 41},
        {"group": "g" * 81},
    ],
)
def test_line_request_limits(kwargs):
    with pytest.raises(ValidationError):
        line(**kwargs)


def test_line_count_limits():
    with pytest.raises(ValidationError):
        schemas.BuildQuoteRequest(lines=[])
    with pytest.raises(ValidationError):
        schemas.BuildQuoteRequest(lines=[line(f"l{i}") for i in range(51)])
    with pytest.raises(ValidationError):
        engine_input(*[line(f"l{i}") for i in range(51)])


def test_search_limit_bounds():
    assert schemas.SearchProductsRequest(q="maito").limit == 10
    with pytest.raises(ValidationError):
        schemas.SearchProductsRequest(q="maito", limit=21)


def test_quote_response_extends_engine_output():
    assert set(schemas.EngineOutput.model_fields) < set(schemas.QuoteResponse.model_fields)
