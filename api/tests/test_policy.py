"""The rule files in policy/ load, and the loader refuses inconsistent ones (#35)."""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.engine.codes import Containment, KitchenChoice, ReasonCode
from app.services.policy import DATA_FILES, POLICY_FILES, PolicyError, load_rule_set
from app.settings import REPO_ROOT

POLICY_DIR = REPO_ROOT / "policy"
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    """A writable copy of the rule files, for tests that break them."""
    policy, data = tmp_path / "policy", tmp_path / "data"
    policy.mkdir()
    data.mkdir()
    for name in POLICY_FILES:
        shutil.copy(POLICY_DIR / name, policy / name)
    for name in DATA_FILES:
        shutil.copy(DATA_DIR / name, data / name)
    return policy, data


def edit_yaml(path: Path, change) -> None:
    doc = yaml.safe_load(path.read_text())
    change(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True))


def problems_of(policy: Path, data: Path) -> str:
    with pytest.raises(PolicyError) as exc:
        load_rule_set(policy, data)
    return str(exc.value)


def test_the_committed_rule_set_loads():
    rules = load_rule_set(POLICY_DIR, DATA_DIR)

    assert set(rules.messages) == set(ReasonCode)
    assert set(rules.kitchen) == set(KitchenChoice)
    assert set(rules.containment) == set(Containment)
    assert rules.policy.rounding.max_overage_ratio == Decimal("0.02")
    assert rules.policy.business_time.isoformat() == "2026-11-12T09:00:00+02:00"
    assert rules.ref.startswith(f"{rules.version}+sha256:")


def test_loading_twice_gives_the_same_hash():
    assert (
        load_rule_set(POLICY_DIR, DATA_DIR).content_hash
        == load_rule_set(POLICY_DIR, DATA_DIR).content_hash
    )


def test_any_edit_changes_the_hash_even_without_a_version_bump(dirs):
    policy, data = dirs
    before = load_rule_set(policy, data)
    with (policy / "messages.yaml").open("a") as f:
        f.write("\n# a comment\n")

    after = load_rule_set(policy, data)

    assert after.version == before.version
    assert after.content_hash != before.content_hash


def test_kitchen_rules_match_the_decisions():
    kitchen = load_rule_set(POLICY_DIR, DATA_DIR).kitchen

    assert set(kitchen[KitchenChoice.MILK_FREE].block) == {"AM", "ML"}
    assert {"AN", "SA", "AP", "PN"} <= set(kitchen[KitchenChoice.NUT_FREE].block)
    assert "SO" not in kitchen[KitchenChoice.NUT_FREE].block
    vegan = kitchen[KitchenChoice.VEGAN]
    assert [c.code for c in vegan.require_claim] == ["VEGAN"]
    assert {"AM", "AE", "AF", "BF", "CM", "PO"} <= set(vegan.block)
    for rule in kitchen.values():
        assert "X99" not in rule.block


def test_a_reason_code_without_a_template_is_refused(dirs):
    policy, data = dirs
    edit_yaml(policy / "messages.yaml", lambda d: d["codes"].pop("UNIT_UNKNOWN"))

    assert "messages.yaml codes: missing UNIT_UNKNOWN" in problems_of(policy, data)


def test_a_template_without_a_reason_code_is_refused(dirs):
    policy, data = dirs
    edit_yaml(
        policy / "messages.yaml",
        lambda d: d["codes"].update({"MADE_UP": {"kind": "reason", "fi": "x", "en": "x"}}),
    )

    assert "messages.yaml codes: unknown MADE_UP" in problems_of(policy, data)


def test_an_unknown_placeholder_is_refused(dirs):
    policy, data = dirs
    edit_yaml(policy / "messages.yaml", lambda d: d["codes"]["NO_MATCH"].update(en="{prodct}"))

    assert "unknown placeholder ['prodct']" in problems_of(policy, data)


def test_a_flag_must_say_whether_it_needs_acknowledgement(dirs):
    policy, data = dirs
    edit_yaml(policy / "messages.yaml", lambda d: d["codes"]["ROUNDED_UP"].pop("ack"))

    assert "ROUNDED_UP: a flag must say" in problems_of(policy, data)


def test_x99_may_not_block(dirs):
    policy, data = dirs
    edit_yaml(
        policy / "allergen_rules.yaml", lambda d: d["choices"]["egg_free"]["block"].append("X99")
    )

    assert "X99 is not an allergen" in problems_of(policy, data)


def test_an_unknown_allergen_code_is_refused(dirs):
    policy, data = dirs
    edit_yaml(
        policy / "allergen_rules.yaml", lambda d: d["choices"]["egg_free"]["block"].append("ZZ")
    )

    assert "egg_free: unknown allergen code ZZ" in problems_of(policy, data)


def test_a_missing_kitchen_choice_is_refused(dirs):
    policy, data = dirs
    edit_yaml(policy / "allergen_rules.yaml", lambda d: d["choices"].pop("vegan"))

    assert "missing vegan" in problems_of(policy, data)


def test_a_bad_policy_value_is_refused(dirs):
    policy, data = dirs
    edit_yaml(policy / "policy.yaml", lambda d: d.update(call_language="sv"))

    assert "call_language" in problems_of(policy, data)


def test_a_missing_file_is_refused(dirs):
    policy, data = dirs
    (policy / "unit_codes.csv").unlink()

    assert "missing file policy/unit_codes.csv" in problems_of(policy, data)
