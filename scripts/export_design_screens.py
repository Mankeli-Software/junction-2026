"""Export the design canvas screens into docs/design.

Usage:
    python3 scripts/export_design_screens.py <canvas project dir> [docs/design]

<canvas project dir> holds the canvas files as downloaded from the design
artifact (canvas.json and the *.dc.html artboards). The script:

1. copies the artboard sources to docs/design/source/,
2. converts each artboard to a standalone HTML page in docs/design/html/
   (the screens are static, so the design runtime is not needed),
3. renders a PNG of each page to docs/design/screens/ with headless Chrome,
   if Chrome is installed.

Fonts load from Google Fonts, so rendering needs network access.
"""
import json
import os
import re
import shutil
import subprocess
import sys

NAMES = {
    "Landing.dc.html": "00-start-computer",
    "Landing-Mobile.dc.html": "01-start-phone",
    "Main.dc.html": "10-call-setup",
    "Call-2-Account.dc.html": "11-call-contact",
    "Call-3-InCall.dc.html": "12-call-in-call",
    "Call-4-Ended.dc.html": "13-call-ended",
    "Call-0-Desktop.dc.html": "14-call-on-computer",
    "Confirm-1-Review.dc.html": "20-confirm-check",
    "Confirm-2-Line.dc.html": "21-confirm-line",
    "Confirm-3-Received.dc.html": "22-confirm-received",
    "Dash-1-Overview.dc.html": "30-dashboard-overview",
    "Dash-2-Summary.dc.html": "31-dashboard-summary",
    "Dash-3-FullFlow.dc.html": "32-dashboard-full-flow",
    "Dash-4-AuditLog.dc.html": "33-dashboard-audit-log",
    "Shop-1-Desktop.dc.html": "40-webshop-desktop",
    "Shop-2-Menu.dc.html": "41-webshop-menu",
    "Shop-3-Quote.dc.html": "42-webshop-quote",
}
# Pages taller than their canvas frame, so the screenshot shows all of it.
HEIGHT_OVERRIDE = {"30-dashboard-overview": 1740}
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def convert(src_file, names):
    s = open(src_file).read()
    title = re.search(r"<title>(.*?)</title>", s, re.S).group(1)
    helmet = re.search(r"<helmet>(.*?)</helmet>", s, re.S).group(1)
    body = re.search(r"<x-dc>(.*?)</x-dc>", s, re.S).group(1)
    body = re.sub(r"<helmet>.*?</helmet>", "", body, flags=re.S).strip()
    for k, v in names.items():
        body = body.replace(f'href="{k}"', f'href="{v}.html"')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n{helmet.strip()}\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "docs/design"
    canvas = json.load(open(os.path.join(src, "canvas.json")))
    for d in ("source", "html", "screens"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    for f, n in NAMES.items():
        shutil.copy(os.path.join(src, f), os.path.join(out, "source", f))
        html_path = os.path.abspath(os.path.join(out, "html", n + ".html"))
        open(html_path, "w").write(convert(os.path.join(src, f), NAMES))
        if not os.path.exists(CHROME):
            continue
        b = canvas["boards"][f]
        h = HEIGHT_OVERRIDE.get(n, b["h"])
        png = os.path.abspath(os.path.join(out, "screens", n + ".png"))
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", "--virtual-time-budget=4000",
             f"--window-size={b['w']},{h}", f"--screenshot={png}", "file://" + html_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    print(f"Exported {len(NAMES)} screens to {out}")


if __name__ == "__main__":
    main()
