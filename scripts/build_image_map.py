"""Build the product image map: dataset product id -> Valio's own image URL (#108).

The map is our own crawl of the Minun Aimo portal (toimitustukku.valioaimo.fi, use OK'd
by the organisers) joined to the static product file by barcode. The images stay on
Valio's media server (https://api.valioaimo.fi/medias/...) and are hotlinked.

How the crawl was made (needs a signed-in portal session; no credentials, cookies or
tokens are stored in these scripts):

1. A listing crawl and portal_image_crawler.js, pasted into the devtools console of a
   signed-in portal tab, collected shop product codes and their product pages, then
   exported {exportedAt, listing, details} as JSON to ~/Downloads. The listing crawl
   and the export snippet were run by hand and are not in the repository.
2. portal_crawler_pw.mjs (kept running by run_portal_crawler.sh) crawls the rest in a
   Playwright window you sign in to yourself: by listing (--mode listed), by GTIN search
   for unmapped products (--mode gtin) and by exact name search (--mode name). It
   appends to ~/Downloads/valio_portal_details.jsonl.
3. save_portal_snapshot.sh picks the newest export and runs this script.

The raw crawl (the export and the .jsonl) stays on the machine that ran it and is not
committed; only the trimmed map, data/product_images.json.gz, is.

The static file renumbers product ids (460000..), so shop codes do not match ids.
Join on GTIN (any of salesUnitGtin, synkkaData.gtin, units[].gtin), falling back
to an exact normalized Finnish name match when the GTIN is missing or unmatched.

Usage: python3 -I scripts/build_image_map.py <product_data.json> <portal_export.json> <out>

An <out> ending in .json.gz writes the committed form: {product_id: {image, ean, match}},
sorted keys, gzip with no timestamp, so the same crawl gives the same bytes. Any other
<out> writes the full map (all images, shop code, thumbnail). To trim a full map:
python3 -I scripts/build_image_map.py --trim <full.json> data/product_images.json.gz
"""
import gzip, json, os, re, sys, unicodedata
from collections import defaultdict


def gtin_key(g):
    g = re.sub(r"\D", "", g or "")
    return g.lstrip("0") or None


def norm_name(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[®™©]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def product_gtins(p):
    gs = [p.get("salesUnitGtin"), p["synkkaData"].get("gtin")] + [u.get("gtin") for u in p.get("units", [])]
    return {k for k in map(gtin_key, gs) if k}


def main(prod_path, export_path, out_path):
    products = json.load(open(prod_path))
    export = json.load(open(export_path))
    merged = {d["code"]: d for d in export["details"] if d.get("imgs")}
    # Results of the Playwright crawler (one JSON object per line), newer wins.
    jsonl = os.path.join(os.path.dirname(export_path), "valio_portal_details.jsonl")
    if os.path.exists(jsonl):
        for line in open(jsonl):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") != "search" and r.get("imgs"):
                merged[r["code"]] = r
    details = list(merged.values())
    # Exact name matches from the crawler's name-search mode: dataset id -> shop code.
    name_hits = {}
    if os.path.exists(jsonl):
        for line in open(jsonl):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") == "namesearch" and len(r.get("exact") or []) == 1:
                name_hits[r["id"]] = r["exact"][0]
    thumbs = {i["code"]: i.get("img") for i in export.get("listing", [])}

    by_ean, by_name = defaultdict(set), defaultdict(set)
    rec = {d["code"]: d for d in details}
    for d in details:
        if gtin_key(d.get("ean")):
            by_ean[gtin_key(d["ean"])].add(d["code"])
        if d.get("name"):
            by_name[norm_name(d["name"])].add(d["code"])

    out, stats = {}, defaultdict(int)
    for p in products:
        codes = set().union(*(by_ean[g] for g in product_gtins(p))) if product_gtins(p) else set()
        how = "gtin"
        if len(codes) != 1:
            names = [n["value"] for n in p["synkkaData"].get("names", []) if n.get("language") == "fi"]
            name_codes = set().union(*(by_name[norm_name(n)] for n in names)) if names else set()
            if len(name_codes) == 1:
                codes, how = name_codes, "name"
            elif len(codes) > 1 and len(name_codes & codes) == 1:
                codes, how = name_codes & codes, "gtin+name"
            elif p["id"] in name_hits and name_hits[p["id"]] in rec:
                codes, how = {name_hits[p["id"]]}, "namesearch"
        if len(codes) == 1:
            code = next(iter(codes))
            d = rec[code]
            out[p["id"]] = {
                "shopCode": code,
                "ean": d.get("ean"),
                "image": d["imgs"][0],
                "images": d["imgs"],
                "thumbnail": thumbs.get(code),
                "match": how,
            }
            stats[how] += 1
        else:
            stats["ambiguous" if codes else "unmatched"] += 1

    if out_path.endswith(".json.gz"):
        write_trimmed(out, out_path)
    else:
        with open(out_path, "w") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"dataset products {len(products)}; portal products with images {len(details)}")
    print(f"mapped {len(out)} ({len(out) / len(products):.1%}):", dict(stats))


def write_trimmed(full, out_path):
    """The committed map: main image, EAN and match kind only, byte-for-byte reproducible."""
    # The database knows two kinds: a barcode match (also when a name settled between
    # several barcode hits) or an exact name match (also from the crawler's name search).
    kind = {"gtin": "gtin", "gtin+name": "gtin", "name": "name", "namesearch": "name"}
    trimmed = {k: {"image": v["image"], "ean": v.get("ean"), "match": kind[v["match"]]} for k, v in full.items()}
    body = json.dumps(trimmed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with open(out_path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as f:
        f.write(body.encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--trim":
        # Trim an existing full map: build_image_map.py --trim <full.json> <out.json.gz>
        write_trimmed(json.load(open(sys.argv[2])), sys.argv[3])
        sys.exit()
    main(*sys.argv[1:4])
