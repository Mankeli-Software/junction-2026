#!/bin/bash
# Rebuild the product image map (#108) from the portal crawl. See the header of
# scripts/build_image_map.py for how the crawl is made; it needs a signed-in portal
# session, and the raw crawl stays in ~/Downloads (it is never committed).
#
# Finds the newest browser export in ~/Downloads (any name; recognised by its
# exportedAt/listing/details keys), keeps it as valio_portal_images_latest.json, and
# rebuilds data/product_images.json.gz from it, the crawler's .jsonl next to it and
# the static product file (~/Downloads/valio_aimo_junction26_product_data.json, or
# PRODUCT_FILE). Older exports are left where they are.
set -euo pipefail
cd "$(dirname "$0")/.."
DL=~/Downloads
LATEST="$DL/valio_portal_images_latest.json"
PRODUCT_FILE="${PRODUCT_FILE:-$DL/valio_aimo_junction26_product_data.json}"
python3 -I - "$DL" "$LATEST" <<'EOF'
import json, os, sys, glob
dl, latest = sys.argv[1], sys.argv[2]
def meta(p):
    try:
        if os.path.getsize(p) > 50_000_000:
            return None
        d = json.load(open(p))
        if isinstance(d, dict) and {"exportedAt", "listing", "details"} <= d.keys():
            return d["exportedAt"]
    except Exception:
        return None
cands = [(meta(p), p) for p in glob.glob(os.path.join(dl, "*.json")) if os.path.abspath(p) != os.path.abspath(latest)]
cands = sorted(c for c in cands if c[0])
cur = meta(latest) if os.path.exists(latest) else None
if cands and (cur is None or cands[-1][0] > cur):
    os.replace(cands[-1][1], latest)
    print("snapshot", cands[-1][0], "from", os.path.basename(cands[-1][1]))
EOF
python3 -I scripts/build_image_map.py "$PRODUCT_FILE" "$LATEST" data/product_images.json.gz
