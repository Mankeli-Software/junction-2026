"""Load and validate the engine rule set from `policy/` and `data/` (#35).

The engine is pure, so this is the only place that reads the rule files. A rule
set that fails any check is refused as a whole: the API must not start on rules
that are half right.
"""

import csv
import hashlib
import io
import string
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas import (
    REJECTING_CODES,
    REMOVAL_CODES,
    TEMPLATE_FIELDS,
    AllergenName,
    Containment,
    Exclusion,
    KitchenRule,
    Localized,
    Message,
    Policy,
    ReasonCode,
    RuleSet,
    TextKey,
    UnitName,
)
from app.schemas.engine import MAX_LINES, MAX_QUANTITY, MAX_TEXT_LENGTH
from app.settings import get_settings

POLICY_FILES = ("policy.yaml", "allergen_rules.yaml", "messages.yaml", "unit_codes.csv")
DATA_FILES = ("gs1_allergen_codes.csv", "allergen_containment_levels.csv")

# "No obligatory allergens present". Never a hazard, so it may not be blocked on.
NOT_AN_ALLERGEN = "X99"


class PolicyError(ValueError):
    """The rule files are missing, malformed or inconsistent."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid rule set:\n" + "\n".join(f"- {p}" for p in problems))


def load_rule_set(policy_dir: Path, data_dir: Path) -> RuleSet:
    sources = {f"policy/{n}": policy_dir / n for n in POLICY_FILES} | {
        f"data/{n}": data_dir / n for n in DATA_FILES
    }
    missing = [name for name, path in sources.items() if not path.is_file()]
    if missing:
        raise PolicyError([f"missing file {name}" for name in missing])
    raw = {name: path.read_bytes() for name, path in sources.items()}

    problems: list[str] = []
    try:
        rule_set = _build(raw, problems)
    except (yaml.YAMLError, ValidationError, KeyError, TypeError, ValueError) as exc:
        raise PolicyError([*problems, str(exc)]) from exc
    if problems:
        raise PolicyError(problems)
    return rule_set


@lru_cache
def get_rule_set() -> RuleSet:
    """The rule set the running API uses, loaded once per process."""
    settings = get_settings()
    return load_rule_set(settings.policy_dir, settings.data_dir)


def content_hash(raw: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(raw):
        digest.update(name.encode() + b"\0" + raw[name] + b"\0")
    return digest.hexdigest()


def _build(raw: dict[str, bytes], problems: list[str]) -> RuleSet:
    policy = Policy.model_validate(_yaml(raw["policy/policy.yaml"]))
    _check_limits(policy, problems)
    allergens = _allergens(raw["data/gs1_allergen_codes.csv"])
    kitchen = _kitchen(_yaml(raw["policy/allergen_rules.yaml"]), allergens, problems)
    messages_doc = _yaml(raw["policy/messages.yaml"])
    messages = _messages(messages_doc.get("codes") or {}, problems)
    texts = _texts(messages_doc.get("texts") or {}, problems)
    containment = _containment(
        raw["data/allergen_containment_levels.csv"],
        messages_doc.get("containment_en") or {},
        problems,
    )
    units = _units(raw["policy/unit_codes.csv"], problems)

    return RuleSet(
        version=policy.version,
        content_hash=content_hash(raw),
        policy=policy,
        kitchen=kitchen,
        messages=messages,
        texts=texts,
        containment=containment,
        units=units,
        allergens=allergens,
    )


def _yaml(data: bytes) -> dict[str, Any]:
    doc = yaml.safe_load(data)
    if not isinstance(doc, dict):
        raise ValueError("a policy YAML file is not a mapping")
    return doc


def _csv(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def _allergens(data: bytes) -> dict[str, AllergenName]:
    return {
        row["code"]: AllergenName(
            gs1_label=row["gs1_label"],
            eu_group=row["eu_1169_2011_group"] or None,
            name_fi=row["name_fi"],
            name_fi_partitive=row["name_fi_partitive"] or None,
        )
        for row in _csv(data)
    }


def _kitchen(
    doc: dict[str, Any], allergens: dict[str, AllergenName], problems: list[str]
) -> dict[Exclusion, KitchenRule]:
    choices = doc.get("choices") or {}
    _same_keys("allergen_rules.yaml choices", set(choices), {c.value for c in Exclusion}, problems)

    kitchen: dict[Exclusion, KitchenRule] = {}
    for key, body in choices.items():
        if key not in Exclusion.__members__.values():
            continue
        rule = KitchenRule.model_validate(body)
        codes = list(rule.block)
        if rule.block_unless_claim:
            codes += rule.block_unless_claim.codes
        for code in codes:
            if code == NOT_AN_ALLERGEN:
                problems.append(f"{key}: {NOT_AN_ALLERGEN} is not an allergen and must not block")
            elif code not in allergens:
                problems.append(f"{key}: unknown allergen code {code}")
        if not codes and not rule.require_claim:
            problems.append(f"{key}: blocks nothing")
        kitchen[Exclusion(key)] = rule
    return kitchen


def _messages(doc: dict[str, Any], problems: list[str]) -> dict[ReasonCode, Message]:
    _same_keys("messages.yaml codes", set(doc), {c.value for c in ReasonCode}, problems)

    messages: dict[ReasonCode, Message] = {}
    for key, body in doc.items():
        if key not in ReasonCode.__members__.values():
            continue
        message = Message.model_validate(body)
        if message.kind == "flag" and message.ack is None:
            problems.append(f"{key}: a flag must say whether the buyer acknowledges it (ack)")
        if message.kind == "reason" and message.ack is not None:
            problems.append(f"{key}: only flags take ack")
        code = ReasonCode(key)
        if code in REMOVAL_CODES and message.short is None:
            problems.append(f"{key}: removes candidates, so it needs a short trace label")
        if code in REJECTING_CODES and message.next is None:
            problems.append(f"{key}: can reject a line, so it needs a next step")
        templates = [(lang, getattr(message, lang)) for lang in ("fi", "en")]
        for part in ("short", "next"):
            if (text := getattr(message, part)) is not None:
                templates += [(f"{part} fi", text.fi), (f"{part} en", text.en)]
        _check_placeholders(key, templates, problems)
        messages[code] = message
    return messages


def _texts(doc: dict[str, Any], problems: list[str]) -> dict[TextKey, Localized]:
    _same_keys("messages.yaml texts", set(doc), {k.value for k in TextKey}, problems)
    texts: dict[TextKey, Localized] = {}
    for key, body in doc.items():
        if key not in TextKey.__members__.values():
            continue
        text = Localized.model_validate(body)
        _check_placeholders(key, [("fi", text.fi), ("en", text.en)], problems)
        texts[TextKey(key)] = text
    return texts


def _check_placeholders(key: str, templates: list[tuple[str, str]], problems: list[str]) -> None:
    for where, template in templates:
        unknown = _placeholders(template) - TEMPLATE_FIELDS
        if unknown:
            problems.append(f"{key} ({where}): unknown placeholder {sorted(unknown)}")


def _containment(
    data: bytes, english: dict[str, str], problems: list[str]
) -> dict[Containment, Localized]:
    finnish = {row["value"]: row["phrase_fi"] for row in _csv(data)}
    expected = {c.value for c in Containment}
    _same_keys("allergen_containment_levels.csv", set(finnish), expected, problems)
    _same_keys("messages.yaml containment_en", set(english), expected, problems)
    return {
        level: Localized(fi=finnish[level], en=english[level])
        for level in Containment
        if level in finnish and level in english
    }


def _units(data: bytes, problems: list[str]) -> dict[str, UnitName]:
    units: dict[str, UnitName] = {}
    for row in _csv(data):
        code = row.pop("code")
        if code in units:
            problems.append(f"unit_codes.csv: duplicate code {code}")
        units[code] = UnitName.model_validate(row)
    return units


def _check_limits(policy: Policy, problems: list[str]) -> None:
    # The contract validates requests with these constants, so they must agree.
    for name, in_policy, in_contract in (
        ("max_lines", policy.limits.max_lines, MAX_LINES),
        ("max_text_length", policy.limits.max_text_length, MAX_TEXT_LENGTH),
        ("max_quantity", policy.limits.max_quantity, MAX_QUANTITY),
    ):
        if in_policy != in_contract:
            problems.append(
                f"policy.yaml limits.{name} is {in_policy} but app/schemas/engine.py has "
                f"{in_contract}; change both"
            )


def _placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field is not None}


def _same_keys(where: str, found: set[str], expected: set[str], problems: list[str]) -> None:
    for key in sorted(expected - found):
        problems.append(f"{where}: missing {key}")
    for key in sorted(found - expected):
        problems.append(f"{where}: unknown {key}")
