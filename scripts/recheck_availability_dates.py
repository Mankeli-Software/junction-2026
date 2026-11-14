"""Re-check how the mock availability API handles dates (availableDate / closingTime).

Usage:
    VALIO_API_KEY=... python3 scripts/recheck_availability_dates.py path/to/valio_aimo_junction26_product_data.json

Samples a small shortlist of 60 products (seed 7) and queries a few requested dates, then prints how
availableDate and closingTime are distributed. Compare proportions, not counts, with the 2026-11-13
baseline in valio-api-analysis.md section 12 (that baseline used 600 products, before the small-batch rule).
"""
import collections as C
import json
import os
import random
import sys
import urllib.request

BASE = "https://junction26.valioaimo.fi/api/"
KEY = os.environ["VALIO_API_KEY"]
DATES = ["2026-11-14", "2026-11-16", "2026-11-20"]


def availability(date, ids):
    req = urllib.request.Request(
        BASE + "availability",
        data=json.dumps({"customer": "1", "requestedDate": date, "products": ids}).encode(),
        # Cloudflare blocks the default Python User-Agent (error 1010)
        headers={"X-API-Key": KEY, "Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


products = json.load(open(sys.argv[1]))
random.seed(7)
ids = [p["id"] for p in random.sample(products, 60)]

for date in DATES:
    res = availability(date, ids)
    dist = C.Counter()
    for p in res["products"]:
        if not p["scheduleLines"]:
            dist[("empty schedule", None, None)] += 1
            continue
        line = p["scheduleLines"][0]
        dist[(p["logisticModel"], line.get("availableDate"), p["closingTime"][:16])] += 1
    print(f"requested {date}  server time {res['timeNow']}")
    for key, n in sorted(dist.items(), key=lambda kv: -kv[1])[:6]:
        print(f"   {n:4d}  {key}")
