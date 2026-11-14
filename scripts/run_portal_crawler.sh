#!/bin/bash
# Keep the Playwright portal crawler (scripts/portal_crawler_pw.mjs, #108) running:
# restart it when its watchdog exits (code 3) or it crashes. Stops when it finishes
# normally (code 0) or is killed. Needs a signed-in portal session in the crawler's
# window; see scripts/build_image_map.py for the whole rebuild.
# Usage: PW_NODE_MODULES=<dir with node_modules/playwright> scripts/run_portal_crawler.sh --mode gtin
cd "$(dirname "$0")/.."
while true; do
  node scripts/portal_crawler_pw.mjs "$@"
  code=$?
  [ $code -eq 0 ] && { echo "crawler finished"; exit 0; }
  [ $code -ge 128 ] && { echo "crawler killed ($code), stopping"; exit $code; }
  echo "crawler exited with $code, restarting in 5 s"
  sleep 5
done
