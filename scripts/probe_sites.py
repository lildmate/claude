#!/usr/bin/env python3
"""Temporary: which deeplol.gg API calls its champion pages make (run on CI)."""

import json
import sys
import time

import requests
from playwright.sync_api import sync_playwright

PAGES = [
    "https://www.deeplol.gg/champions/chogath/build/top",
    "https://www.deeplol.gg/champions/chogath/counter/top",
    "https://www.deeplol.gg/champions/chogath/build/top/sejuani",
    "https://www.deeplol.gg/champions/chogath/build/top?enemy=sejuani",
]
HEADERS = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.deeplol.gg", "Referer": "https://www.deeplol.gg/"}

seen = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("request", lambda r: seen.append(r.url) if "b2c-api" in r.url else None)
    for url in PAGES:
        before = len(seen)
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(7)
            print("PAGE", url, "->", resp.status if resp else None, "| final", page.url)
            text = page.inner_text("body")
            i = text.find("Sejuani")
            print("   sejuani mention:", text[max(0, i - 200): i + 400].replace("\n", " | ") if i >= 0 else "none")
        except Exception as e:
            print("PAGE", url, "failed", repr(e))
        for u in seen[before:]:
            print("   API", u)
    # clickable matchup controls on the build page
    try:
        page.goto(PAGES[0], wait_until="domcontentloaded", timeout=45000)
        time.sleep(6)
        for sel in ["text=Counter", "text=Matchup", "text=VS", "text=vs"]:
            n = page.locator(sel).count()
            print("selector", sel, n)
    except Exception as e:
        print("controls failed", repr(e))
    browser.close()

print("=" * 80)
for u in sorted(set(seen)):
    if any(k in u for k in ("riot_data", "notice", "season", "riot-status", "item-info", "champion-info")):
        continue
    try:
        r = requests.get(u, headers=HEADERS, timeout=20)
        print("FETCH", u, r.status_code)
        print("   ", json.dumps(r.json(), ensure_ascii=False)[:1500])
    except Exception as e:
        print("FETCH", u, "failed", repr(e))
sys.exit(0)
