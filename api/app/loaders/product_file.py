"""Turns the static product file into catalogue rows. Pure: no database, no network.

See docs/plans/29-product-file-loader.md for the shape of the file and the decisions.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

TEMPERATURE_LABELS = frozenset({"warmTemperature", "coolTemperature", "freezeTemperature"})

# Factor to grams, millilitres and millimetres. Other units (H87 pieces, PTN, dirty values
# like "KGM H87") are left as null and reported.
TO_GRAMS = {"GRM": Decimal(1), "KGM": Decimal(1000)}
TO_MILLILITRES = {"MLT": Decimal(1), "CLT": Decimal(10), "LTR": Decimal(1000)}
TO_MILLIMETRES = {"MMT": Decimal(1), "CMT": Decimal(10), "MTR": Decimal(1000)}
TO_PIECES = {"H87": Decimal(1)}


@dataclass(frozen=True)
class Anomaly:
    kind: str
    product_id: str
    detail: str = ""


@dataclass
class ProductRows:
    product: dict[str, Any]
    units: list[dict[str, Any]] = field(default_factory=list)
    conversions: list[dict[str, Any]] = field(default_factory=list)
    allergens: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    labels: list[dict[str, Any]] = field(default_factory=list)
    substitutions: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _name(names: list[dict[str, str]], language: str) -> str | None:
    return next((n["value"] for n in names if n.get("language") == language), None)


def _measure(
    product_id: str, raw: dict[str, Any] | None, factors: dict[str, Decimal], what: str
) -> tuple[Decimal | None, Anomaly | None]:
    if not raw or raw.get("value") is None:
        return None, None
    factor = factors.get(raw.get("unit", ""))
    if factor is None:
        return None, Anomaly("measure_not_normalised", product_id, f"{what} {raw.get('unit')!r}")
    return _decimal(raw["value"]) * factor, None


def _content(
    product_id: str, raw: dict[str, Any] | None, anomalies: list[Anomaly]
) -> dict[str, Decimal | None]:
    """Splits Synkka's `volume` (the net content) by its unit."""
    content: dict[str, Decimal | None] = {
        "volume_ml": None,
        "content_weight_g": None,
        "content_pieces": None,
    }
    if not raw or raw.get("value") is None:
        return content
    for column, factors in (
        ("volume_ml", TO_MILLILITRES),
        ("content_weight_g", TO_GRAMS),
        ("content_pieces", TO_PIECES),
    ):
        if raw.get("unit") in factors:
            content[column] = _decimal(raw["value"]) * factors[raw["unit"]]
            return content
    anomalies.append(Anomaly("measure_not_normalised", product_id, f"volume {raw.get('unit')!r}"))
    return content


def resolve_conversion_unit(product: dict[str, Any], packaging_type: str) -> str | None:
    """Which unit in `units[]` a `unitConversions` row describes, or None if unclear."""
    units = product["units"]
    unit_ids = {u["unitId"] for u in units}
    synkka_gtin = product["synkkaData"].get("gtin")
    if synkka_gtin:
        match = next((u["unitId"] for u in units if u.get("gtin") == synkka_gtin), None)
        if match:
            return match
    if len(unit_ids) == 1:
        return next(iter(unit_ids))
    if packaging_type == "BASE_UNIT_OR_EACH":
        return product["baseUnit"]
    if packaging_type == "PALLET" and "PAL" in unit_ids:
        return "PAL"
    if packaging_type == "CASE" and product["salesUnit"] != product["baseUnit"]:
        return product["salesUnit"]
    return None


def parse_product(product: dict[str, Any], loaded_at: datetime) -> ProductRows:
    pid = product["id"]
    synkka = product["synkkaData"]
    names = synkka.get("names", [])
    classifications = synkka.get("classifications") or []
    groups = {c["name"]: c.get("values", []) for c in classifications}

    rows = ProductRows(
        product={
            "id": pid,
            "name_fi": _name(names, "fi"),
            "name_en": _name(names, "en"),
            "name_sv": _name(names, "sv"),
            "category_id": product["category"],
            "sales_unit": product["salesUnit"],
            "base_unit": product["baseUnit"],
            "sales_unit_gtin": product.get("salesUnitGtin"),
            "synkka_gtin": synkka.get("gtin"),
            "allowed_lot_size": _decimal(product["allowedLotSize"]),
            "temperature_condition": product.get("temperatureCondition"),
            "min_temperature": _decimal(synkka.get("minTemperature")),
            "max_temperature": _decimal(synkka.get("maxTemperature")),
            "variable_unit": synkka.get("variableUnit"),
            "vendor_name": product["vendorName"],
            "brand": synkka.get("brand") or None,
            "country_of_origin": product.get("countryOfOrigin"),
            "has_classifications": bool(classifications),
            "source_updated_at": (
                datetime.fromisoformat(synkka["lastUpdated"]) if synkka.get("lastUpdated") else None
            ),
            "raw": product,
            "loaded_at": loaded_at,
        }
    )
    anomalies = rows.anomalies

    if rows.product["name_fi"] is None:
        anomalies.append(Anomaly("missing_name_fi", pid))
    if rows.product["name_en"] is None:
        anomalies.append(Anomaly("missing_name_en", pid))
    if rows.product["temperature_condition"] is None:
        anomalies.append(Anomaly("missing_temperature_condition", pid))
    if not classifications:
        anomalies.append(Anomaly("no_classifications", pid))

    for unit in product["units"]:
        rows.units.append(
            {
                "product_id": pid,
                "unit_id": unit["unitId"],
                "size_in_base_units": _decimal(unit["sizeInBaseUnits"]),
                "gtin": unit.get("gtin"),
                "is_sales_unit": unit["unitId"] == product["salesUnit"],
                "is_base_unit": unit["unitId"] == product["baseUnit"],
            }
        )
    unit_ids = {u["unit_id"] for u in rows.units}
    if product["salesUnit"] not in unit_ids:
        anomalies.append(Anomaly("sales_unit_not_in_units", pid, product["salesUnit"]))

    for conversion in synkka.get("unitConversions", []):
        packaging_type = conversion["synkkaPackagingType"]
        unit_id = resolve_conversion_unit(product, packaging_type)
        if unit_id is None:
            anomalies.append(Anomaly("conversion_unit_unresolved", pid, packaging_type))
        row: dict[str, Any] = {
            "product_id": pid,
            "packaging_type": packaging_type,
            "unit_id": unit_id,
            "raw": conversion,
        }
        row.update(_content(pid, conversion.get("volume"), anomalies))
        for column, key, factors in (
            ("net_weight_g", "netWeight", TO_GRAMS),
            ("gross_weight_g", "grossWeight", TO_GRAMS),
            ("width_mm", "width", TO_MILLIMETRES),
            ("length_mm", "length", TO_MILLIMETRES),
            ("height_mm", "height", TO_MILLIMETRES),
        ):
            row[column], anomaly = _measure(pid, conversion.get(key), factors, key)
            if anomaly:
                anomalies.append(anomaly)
        rows.conversions.append(row)

    seen_allergens: dict[str, set[str]] = {}
    for group in ("allergen", "nonAllergen"):
        for value in groups.get(group, []):
            key = (value["id"], value["unit"])
            if value["unit"] in seen_allergens.setdefault(value["id"], set()):
                continue
            seen_allergens[value["id"]].add(value["unit"])
            rows.allergens.append({"product_id": pid, "code": key[0], "containment": key[1]})
    for code, containments in sorted(seen_allergens.items()):
        if "FREE_FROM" in containments and containments - {"FREE_FROM"}:
            anomalies.append(
                Anomaly("allergen_contradiction", pid, f"{code} {'/'.join(sorted(containments))}")
            )

    seen_claims = set()
    for value in groups.get("nutritionalClaim", []):
        key = (value["id"], value.get("unit") or "")
        if key in seen_claims:
            continue
        seen_claims.add(key)
        rows.claims.append(
            {
                "product_id": pid,
                "claim_id": key[0],
                "qualifier": key[1],
                "synkka_id": value.get("synkkaId"),
            }
        )

    for label_id in dict.fromkeys(v["id"] for v in groups.get("packagingMarkedLabel", [])):
        kind = "temperature" if label_id in TEMPERATURE_LABELS else "certificate"
        rows.labels.append({"product_id": pid, "label_id": label_id, "kind": kind})

    for position, substitution in enumerate(product.get("substitutions", [])):
        rows.substitutions.append(
            {
                "product_id": pid,
                "substitute_product_id": substitution["substituteProduct"],
                "position": position,
            }
        )

    return rows


def read_categories(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [
            {
                "id": r["category"],
                "name_en": r["name_en"],
                "name_fi": r["name_fi"],
                "name_fi_source": r["name_fi_source"] or None,
                "confidence": r["confidence"] or None,
                "note": r["note"] or None,
                "shop_path_fi": r["shop_path_fi"] or None,
                "mandate_group": r["mandate_group"],
            }
            for r in csv.DictReader(f)
        ]


def read_allergen_codes(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [
            {
                "code": r["code"],
                "gs1_label": r["gs1_label"],
                "gs1_uri": r["gs1_uri"],
                "eu_group": r["eu_1169_2011_group"] or None,
                "name_fi": r["name_fi"] or None,
                "name_fi_partitive": r["name_fi_partitive"] or None,
                "voice_note_fi": r["voice_note_fi"] or None,
                "note": r["note"] or None,
            }
            for r in csv.DictReader(f)
        ]
