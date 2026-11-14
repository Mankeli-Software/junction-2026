"""Finnish and English text from the templates in policy/messages.yaml."""

from datetime import date
from decimal import Decimal

from app.schemas import Localized, ReasonCode, RuleSet, TextKey

# A field is one string for both languages, or a Localized with one per language.
Field = str | int | Decimal | Localized

WEEKDAYS_FI = ("maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina",
               "lauantaina", "sunnuntaina")  # fmt: skip
WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December")  # fmt: skip


def fill(template: Localized, fields: dict[str, Field]) -> Localized:
    return Localized(
        fi=template.fi.format_map(_pick(fields, "fi")),
        en=template.en.format_map(_pick(fields, "en")),
    )


def message(rules: RuleSet, code: ReasonCode, **fields: Field) -> Localized:
    m = rules.messages[code]
    return fill(Localized(fi=m.fi, en=m.en), fields)


def short(rules: RuleSet, code: ReasonCode, **fields: Field) -> Localized:
    label = rules.messages[code].short
    return fill(label, fields) if label else Localized(fi=code.value, en=code.value)


def next_step(rules: RuleSet, code: ReasonCode, **fields: Field) -> Localized:
    step = rules.messages[code].next
    return fill(step, fields) if step else Localized(fi="", en="")


def text(rules: RuleSet, key: TextKey, **fields: Field) -> Localized:
    return fill(rules.texts[key], fields)


def join(*parts: Localized) -> Localized:
    return Localized(
        fi=" ".join(p.fi for p in parts if p.fi),
        en=" ".join(p.en for p in parts if p.en),
    )


def euros(cents: int) -> Localized:
    whole, rest = divmod(cents, 100)
    return Localized(
        fi=f"{whole:,}".replace(",", " ") + f",{rest:02d} €",
        en=f"€{whole:,}.{rest:02d}",
    )


def day(d: date) -> Localized:
    return Localized(
        fi=f"{WEEKDAYS_FI[d.weekday()]} {d.day}.{d.month}.",
        en=f"{WEEKDAYS_EN[d.weekday()]} {d.day} {MONTHS_EN[d.month - 1]}",
    )


def number(value: Decimal) -> Localized:
    """A quantity without trailing zeros: 1000, 2,5 / 2.5."""
    plain = format(value.normalize(), "f")
    return Localized(fi=plain.replace(".", ","), en=plain)


def unit_name(rules: RuleSet, code: str, plural: bool = False) -> Localized:
    """A unit code in words ("laatikkoa", "cases"); unknown codes stay as they are."""
    names = rules.units.get(code)
    if names is None:
        return Localized(fi=code, en=code)
    if plural:
        return Localized(fi=names.name_fi_partitive, en=names.name_en_plural)
    return Localized(fi=names.name_fi, en=names.name_en)


def _pick(fields: dict[str, Field], lang: str) -> dict[str, str]:
    return {k: getattr(v, lang) if isinstance(v, Localized) else str(v) for k, v in fields.items()}
