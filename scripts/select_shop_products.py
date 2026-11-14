"""Write the webshop's static product selection (#56) from the product file.

Usage:
    python3 scripts/select_shop_products.py [data/valio-products.json]

Reads the static product file (downloaded once with `curl -L` from
/api/products/download, never from the live API) and data/valio_category_names.csv,
and writes web/src/lib/shop/products.json: about 12 real Valio products with their
names, pack size, category and image URL. The image URL stays null until the product
image file (`code`, `name`, `img`, technical-plan.md section 5.5) is in the repository;
the shop then shows a placeholder.
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "src" / "lib" / "shop" / "products.json"

# Real Valio products a kitchen buys, one or two per shelf. Most appear in the recipe
# data (data/recipe-product-map.json); 464073 is also in the API's fixture catalogue.
PRODUCT_IDS = [
    "464073",  # whole milk 1 l lactose free UHT
    "476240",  # Eila skimmed milk drink 1 l
    "476880",  # cooking cream 15 % 10 l
    "469162",  # Ruoka 15 % 1 l
    "476548",  # sour cream 5 kg
    "475797",  # butter 500 g salted
    "476824",  # A+ natural yoghurt 1 kg
    "477044",  # quark 5 kg
    "476721",  # Edam slices 300 g
    "476901",  # cottage cheese 400 g
    "476970",  # Koskenlaskija 1,5 kg
    "476601",  # orange juice 1 l
]

# The category tiles at the top of the shop: shelf key, names, category codes.
SHELVES = [
    ("milk", {"en": "Milk", "fi": "Maidot"}, ["10400"]),
    ("cream", {"en": "Cream", "fi": "Kermat"}, ["10401", "10419"]),
    ("butter", {"en": "Butter", "fi": "Voit"}, ["10500"]),
    ("yoghurt", {"en": "Yoghurt and quark", "fi": "Jogurtit ja rahkat"}, ["10412", "10430"]),
    ("cheese", {"en": "Cheese", "fi": "Juustot"}, ["10602", "10603", "10633"]),
    ("juice", {"en": "Juices", "fi": "Mehut"}, ["21403"]),
]

PACK_SIZE = re.compile(r"(?<![\w,])e?(\d+(?:,\d+)?)\s?(kg|g|dl|l)\b")


def main(product_file: Path) -> None:
    products = {p["id"]: p for p in json.loads(product_file.read_text(encoding="utf-8"))}
    with (ROOT / "data" / "valio_category_names.csv").open(encoding="utf-8") as f:
        categories = {row["category"]: row for row in csv.DictReader(f)}
    shelf_of = {code: key for key, _, codes in SHELVES for code in codes}

    selection = []
    for product_id in PRODUCT_IDS:
        product = products[product_id]
        synkka = product["synkkaData"]
        names = {n["language"]: n["value"] for n in synkka["names"]}
        size = PACK_SIZE.search(names["fi"])
        per_sales_unit = next(
            u["sizeInBaseUnits"] for u in product["units"] if u["unitId"] == product["salesUnit"]
        )
        category = categories[product["category"]]
        selection.append(
            {
                "product_id": product_id,
                "name": {"en": names.get("en", names["fi"]), "fi": names["fi"]},
                "category": product["category"],
                "category_name": {"en": category["name_en"], "fi": category["name_fi"]},
                "shelf": shelf_of[product["category"]],
                "pack_size": f"{size.group(1)} {size.group(2)}" if size else None,
                "sales_unit": product["salesUnit"],
                "units_per_sales_unit": int(per_sales_unit),
                "image_url": None,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "_note": (
            "Written by scripts/select_shop_products.py from the static product file. "
            "Static shop content only: prices and stock come from the agent tools."
        ),
        "shelves": [{"key": key, "name": name} for key, name, _ in SHELVES],
        "products": selection,
    }
    OUT.write_text(json.dumps(document, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(selection)} products to {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "valio-products.json"))
