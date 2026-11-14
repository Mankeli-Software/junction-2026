"""Map recipe products (valioaimo.fi web product ids) to Aimo product codes.

The recipe export (data/valio-recipes.json) references products by the website's
product id. The product data file uses 6-digit Aimo product codes. There is no
shared key, so we match on the Finnish product name with pack sizes removed.
One recipe product is a product *family*; it usually maps to several codes
(one per pack size).

Usage:
    python3 -I scripts/build_recipe_product_map.py <product_data.json> \
        data/valio-recipes.json data/recipe-product-map.json

Reviewed decisions live in OVERRIDES below; they win over the automatic match.
"""

import html
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone

# Words that only describe packaging in recipe names ("bucket", "bag", ...).
PACK_HINT = {"sanko", "pussi", "suurpakkaus", "vuoka"}
# Words the catalog adds that don't change the product family.
NEUTRAL_EXTRA = {
    "laktoositon", "uht", "gluteeniton", "novobox", "esl", "perinteinen",
    "kokonainen", "viipaloitu", "pakaste", "original", "maustamaton", "hyla", "valio",
} | PACK_HINT
STOP = {"x", "n", "e", "á", "à", "a", "noin"}

UNIT = r"(?:kg|g|l|dl|cl|ml|kpl|mm)"
NUM = r"\d+(?:[.,]\d+)?"
PACK_PATTERNS = [
    rf"\b{NUM}\s*{UNIT}\s*x\s*(?:n\.\s*)?{NUM}\s*(?:/\s*{NUM}\s*{UNIT})?",  # 430 g x 6 / 2,58 kg
    rf"\b{NUM}\s*x\s*{NUM}\s*{UNIT}\b",                                      # 4x5 kg
    rf"\b(?:e|n\.\s*)?{NUM}\s*{UNIT}\b",                                     # e2,5 kg, n. 3,2 kg, 500 g
    rf"\(\s*(?:n\.\s*|á\s*)?{NUM}[^)]*\)",                                   # (n. 75 g), (54 kpl), (16x16 mm)
]


def clean(s: str) -> str:
    s = html.unescape(unicodedata.normalize("NFKC", s)).lower()
    s = s.replace("®", " ").replace("™", " ").replace("+", " ")
    s = re.sub(r"(\d)\s+%", r"\1%", s)  # "15 %" -> "15%"
    for pat in PACK_PATTERNS:
        s = re.sub(pat, " ", s)
    return s


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-zåäö0-9%&]+", clean(s)) if t not in STOP]


def same(a: str, b: str) -> bool:
    """Token equality tolerant of Finnish inflection (kuutiot / kuutioina)."""
    if a == b:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    # Only allow a short differing ending, so compounds don't match their first
    # part (ruoka / ruokakerma, sulatejuusto / sulatejuustotanko).
    return n >= 5 and n >= max(len(a), len(b)) - 3


def score(rtoks: list[str], ctoks: list[str]):
    missing = [t for t in rtoks if not any(same(t, c) for c in ctoks)]
    extra = [c for c in ctoks if c not in NEUTRAL_EXTRA and not any(same(c, t) for t in rtoks)]
    return missing, extra


def net_weight_kg(p):
    for conv in p.get("synkkaData", {}).get("unitConversions") or []:
        if conv.get("synkkaPackagingType") == "BASE_UNIT_OR_EACH":
            nw = conv.get("netWeight") or {}
            v, u = nw.get("value"), nw.get("unit")
            if v is None:
                return None
            return {"GRM": v / 1000, "KGM": v, "MGM": v / 1e6}.get(u)
    return None


SIZE_UNITS_KG = {"kg": 1.0, "g": 0.001, "l": 1.0, "dl": 0.1, "cl": 0.01, "ml": 0.001}
SIZE_RE = re.compile(
    r"(?<![\w,])(?:e|n\.?\s*)?(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|l|dl|cl|ml)(?![a-zåäö])",
    re.IGNORECASE,
)


def size_from_text(text):
    """First pack size in a name or URL slug -> (kg, is_volume). '4x5 kg' -> 20 kg."""
    t = text.replace(" ", " ")
    t = re.sub(r"(?<!\d)0(\d)-(?=(kg|g|l|dl|cl|ml)\b)", r"0,\1-", t)  # URL slugs: 05-l -> 0,5 l
    t = re.sub(r"(\d)-(\d)", r"\1,\2", t)            # URL slugs: 2-5-kg -> 2,5 kg
    t = re.sub(r"(\d)-(kg|g|l|dl|cl|ml)\b", r"\1 \2", t)  # URL slugs: 1-kg-tolkki
    # "16 g x n. 325 / 5,2 kg": the base unit is the whole bag/case, use the total.
    total = re.search(r"x\s*(?:n\.\s*)?\d+\s*/\s*(\d+(?:[.,]\d+)?)\s*(kg|g|l)\b", t, re.IGNORECASE)
    if total:
        return round(float(total.group(1).replace(",", ".")) * SIZE_UNITS_KG[total.group(2).lower()], 6), False
    m = SIZE_RE.search(t)
    if not m:
        return None
    count = int(m.group(1)) if m.group(1) else 1
    value = float(m.group(2).replace(",", ".")) * count
    unit = m.group(3).lower()
    return round(value * SIZE_UNITS_KG[unit], 6), unit in ("l", "dl", "cl", "ml")


def units_per_sales_unit(p):
    return next((u["sizeInBaseUnits"] for u in p["units"] if u["unitId"] == p["salesUnit"]), None)


def weight_info(p, recipe_url, single_candidate):
    """netWeightKg of one base unit / piece, and where it came from."""
    w = net_weight_kg(p)
    if w is not None:
        return w, "productData"
    s = size_from_text(fi_name(p))
    if s:
        if p["baseUnit"] == "KI":
            # base unit is a case of unknown count; the name only gives the piece size
            return s[0], "namePieceInCase"
        return s[0], "nameVolume" if s[1] else "name"
    if single_candidate:
        tail = recipe_url.rstrip("/").split("/tuotteet/")[-1]
        if "/" in tail:  # only the pack-specific part, e.g. .../1-kg-tolkki
            s = size_from_text(tail.split("/", 1)[1])
            if s:
                return s[0], "recipeUrl"
    return None, None


def fi_name(p):
    return next((n["value"] for n in p["synkkaData"]["names"] if n["language"] == "fi"), None)


# Reviewed by hand against the catalog names (2026-11-14). ids = Aimo product codes.
# confidence: "reviewed" (sure), "probable" (judgement call, see note),
# default "not_in_catalog" when ids is empty.
def R(ids, note=None):
    return {"ids": ids, "confidence": "reviewed", "note": note}


def PR(ids, note):
    return {"ids": ids, "confidence": "probable", "note": note}


def NO(note=None):
    return {"ids": [], "confidence": "not_in_catalog", "note": note}


OVERRIDES: dict[str, dict] = {
    # medium matches, confirmed or narrowed
    "209563": R(["469079"]),
    "85272": R(["471751"], "Kalaonni-brand fillet excluded"),
    "199": R(["477050"], "Eila piimä is the fat-free one"),
    "207085": R(["469036"]),
    "14133": PR(["462718"], "catalog name has no 6 %; 2 kg tub fits 'sanko'"),
    "3700": R(["476745", "475784"], "plain AURA: 170 g piece and 3.2 kg whole; Gold and filling excluded"),
    "33923": R(["464241"]),
    "3122": R(["476875"]),
    "3124": R(["476698"]),
    "33807": PR(["463223"], "only the kevyt (light) variant is in the catalog"),
    "3643": R(["462593", "463948", "464362"], "sliced (viipale) packs only"),
    "33638": R(["462630"], "plain = alkuperäinen slices"),
    "33658": R(["462622"], "sliced (viipale) pack only"),
    "33678": R(["462636", "465279", "465555"], "sliced (viipale) packs only"),
    "33899": R(["463875"]),
    "33930": R(["462616", "464204", "476721"], "sliced (viipale) packs only"),
    "85793": R(["471224"], "Fazer/Vaasan products excluded"),
    "85950": R(["471707"], "Fazer product excluded"),
    "86440": NO("only fresh non-Valio strawberries in catalog; no Valio frozen strawberry (Suomi)"),
    "87427": NO("roasted-butter curd not in catalog; nearest is 471368 Valio voi curd täyte"),
    # unmatched, found under a different name
    "13": R(["469556", "469181"], "plain Valio täysmaito (non lactose-free): 1 l ESL and 10 l novobox"),
    "96524": R(["471847"], "Valio vapaan kanan munamassa 5 kg"),
    "85307": R(["471860"]),
    "87904": PR(["468233"], "Valio vadelmatäyte 10 kg; 469041 vadelma leipomohillo is the alternative"),
    "36086": PR(["472684", "473441"], "assumed to be Gold&Green Mureat ja mehevät suikaleet Original"),
    "87887": PR(["469300"], "catalog calls it mansikkapala leipomohillo"),
    "69036": R(["469157"]),
    "87821": PR(["469073"], "catalog has mansikka kakkuhillo, not kakkutäyte"),
    "500": R(["469061"]),
    "3390": R(["476757", "476869"]),
    "33677": R(["462584", "465293"], "sliced full-fat Oltermanni"),
    "85321": R(["471201"]),
    "85320": R(["471318"]),
    "3921": R(["472672", "475588"]),
    "33791": R(["475496"], "474950 'Hienoin Alppi Kreivi' is a separate aged variant"),
    "33978": R(["475629"]),
    "85350": PR(["470813"], "FS chilikalafilee; 'rapea' not in name"),
    "613": R(["476600"]),
    "33843": R(["463467", "463904"]),
    "34193": PR(["465174"], "only mozzarella juustomuru (crumble) in catalog, no raaste"),
    # unmatched, not in the product file
    "87428": NO(),
    "34216": NO(),
    "87426": NO("only vanilja-tuorejuustotäyte 469783 exists"),
    "36069": NO(),
    "14283": NO("other maustettu rahka flavours exist, not puolukka-kinuski"),
    "22362": NO(),
    "34276": NO(),
    "34833": NO(),
}

# Generic recipe ingredients with no recipe product (productId null), linked by hand (#100).
# Ingredient ids are shared across recipes, so a link applies to every recipe using them.
# Keys are synthetic recipe product ids, 900001 and up, clear of the website's ids; the map
# lists them under "mappings" like any recipe product and under "ingredientLinks".
# Salt and white pepper stay unlinked: they are listed as not ordered.
INGREDIENT_LINKS: dict[str, dict] = {
    "900001": {
        "name": "makaroni",
        "ingredientIds": [20309],  # makaronia
        **R(["466316", "461424", "462863"], "Myllyn Paras Makaroni 400 g, 1 kg, 10 kg; dark excluded"),
    },
    "900002": {
        "name": "vähärasvainen naudan jauheliha",
        "ingredientIds": [20078],  # vähärasvaista naudan jauhelihaa
        **R(["463104"], "Atria Naudan 0 Jauheliha 10% 2 kg, fresh"),
    },
    "900003": {
        "name": "pakastesipulikuutio",
        "ingredientIds": [19807],  # pakastesipulikuutioita
        **R(["461339", "461230"], "Apetit Sipulikuutio pakaste 200 g and 3 x 1.5 kg"),
    },
    "900004": {
        "name": "kananmuna",
        # kananmunia (19759, 22245), kananmunaa (19489, 19599)
        "ingredientIds": [19759, 22245, 19489, 19599],
        **R(
            ["467676", "467880", "468445", "467464", "463982"],
            "Kieku Vapaan kanan muna shell eggs, trays M10 to cases L180; organic and liquid egg excluded",
        ),
    },
}


def packs(by_id, ids, recipe_url):
    """One entry per catalogue pack, lightest first."""
    products = []
    for i in ids:
        p = by_id[i]
        w, src = weight_info(p, recipe_url, len(ids) == 1)
        products.append({
            "id": i,
            "name": fi_name(p),
            "salesUnit": p["salesUnit"],
            "baseUnit": p["baseUnit"],
            "unitsPerSalesUnit": units_per_sales_unit(p),
            "netWeightKg": w,
            "weightSource": src,
        })
    return sorted(products, key=lambda x: (x["netWeightKg"] is None, x["netWeightKg"] or 0, x["id"]))


def main(product_path, recipes_path, out_path):
    catalog = [p for p in json.load(open(product_path)) if not p.get("deleted") and fi_name(p)]
    by_id = {p["id"]: p for p in catalog}
    ctok = {p["id"]: tokens(fi_name(p)) for p in catalog}
    recipes = json.load(open(recipes_path))
    uses = Counter(
        i["productId"] for r in recipes["recipes"]
        for s in r["ingredientSegments"] for i in s["ingredients"] if i["productId"]
    )
    related = Counter(pid for r in recipes["recipes"] for pid in r["relatedProductIds"])

    out = {}
    for pid, rp in recipes["products"].items():
        rt_all = tokens(rp["name"])
        rt = [t for t in rt_all if t not in PACK_HINT and t != "valio"]
        best_tier, cands = None, []
        for cid, ct in ctok.items():
            missing, extra = score(rt, ct)
            if not missing and not extra:
                tier = "high"
            elif (not missing and len(extra) == 1) or (len(missing) == 1 and not extra and len(rt) >= 3):
                tier = "medium"
            else:
                continue
            if best_tier is None or tier == "high" and best_tier == "medium":
                best_tier, cands = tier, []
            if tier == best_tier:
                cands.append((cid, missing, extra))

        entry = {
            "recipeProductName": html.unescape(rp["name"]),
            "recipeProductUrl": rp["url"],
            "ingredientUses": uses.get(int(pid), 0),
            "relatedUses": related.get(int(pid), 0),
            "packHint": next((t for t in rt_all if t in PACK_HINT), None),
        }
        if pid in OVERRIDES:
            ov = OVERRIDES[pid]
            entry["confidence"] = ov["confidence"]
            ids, entry["note"] = ov["ids"], ov.get("note")
        elif cands:
            entry["confidence"] = best_tier
            ids = [c[0] for c in cands]
            diffs = sorted({f"-{m}" for c in cands for m in c[1]} | {f"+{e}" for c in cands for e in c[2]})
            entry["note"] = ("token diff: " + " ".join(diffs)) if diffs else None
        else:
            entry["confidence"] = "unmatched"
            ids, entry["note"] = [], None
        entry["aimoProducts"] = packs(by_id, ids, rp["url"])
        out[pid] = entry

    ingredient_uses = Counter(
        i["id"] for r in recipes["recipes"]
        for s in r["ingredientSegments"] for i in s["ingredients"] if not i["productId"]
    )
    ingredient_links = {}
    for key, link in INGREDIENT_LINKS.items():
        assert key not in out, f"synthetic id {key} collides with a recipe product"
        out[key] = {
            "recipeProductName": link["name"],
            "recipeProductUrl": None,
            "ingredientUses": sum(ingredient_uses[i] for i in link["ingredientIds"]),
            "relatedUses": 0,
            "packHint": None,
            "confidence": link["confidence"],
            "note": link["note"],
            "aimoProducts": packs(by_id, link["ids"], ""),
        }
        for ingredient_id in link["ingredientIds"]:
            ingredient_links[str(ingredient_id)] = key

    conf = Counter(e["confidence"] for e in out.values())
    result = {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": "scripts/build_recipe_product_map.py",
            "recipeProducts": len(out),
            "confidence": dict(conf),
            "notes": (
                "Keys are recipe product ids (data/valio-recipes.json products / ingredient productId). "
                "aimoProducts are Aimo product codes from the product data file, one per pack size, "
                "sorted by netWeightKg = net weight of one base unit (one piece). weightSource: "
                "productData = unitConversions; name = pack size in the product name; nameVolume = "
                "volume in the name taken as 1 l = 1 kg (approximate); namePieceInCase = base unit is a "
                "case (KI) and only the piece size is known, so the case weight is unknown; recipeUrl = pack size in the "
                "recipe product URL. unitsPerSalesUnit = base units in one salesUnit (e.g. KI case of 5), "
                "so one ordered sales unit weighs netWeightKg * unitsPerSalesUnit. Confidence: high = name matches with pack "
                "size removed; medium = one word differs (see note); reviewed = checked by hand; "
                "probable = checked by hand, judgement call (see note); not_in_catalog = checked, "
                "no such product in the file; unmatched = needs review. packHint 'sanko'/'suurpakkaus' "
                "means the recipe means a bulk pack. ingredientLinks: recipe ingredient id -> "
                "synthetic recipe product id (900001 and up) for generic ingredients that have no "
                "recipe product; it applies in every recipe using that ingredient."
            ),
        },
        "mappings": out,
        "ingredientLinks": ingredient_links,
    }
    json.dump(result, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(dict(conf))


if __name__ == "__main__":
    main(*sys.argv[1:4])
