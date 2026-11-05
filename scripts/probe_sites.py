#!/usr/bin/env python3
"""Temporary: opens onetricks.gg pages in a real browser and prints their structure (run on CI)."""

import re
import sys
import time

from playwright.sync_api import sync_playwright

PAGES = [
    "https://www.deeplol.gg/champions",
    "https://www.deeplol.gg/champions/ahri/build",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/130.0.0.0 Safari/537.36",
            locale="en-US", viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        api_calls = []
        def on_response(r):
            ctype = r.headers.get("content-type", "")
            if "json" in ctype or "/api" in r.url:
                body = ""
                try:
                    body = r.text()[:700]
                except Exception:
                    pass
                api_calls.append((r.status, r.url, ctype, body))
        page.on("response", on_response)
        for url in PAGES:
            print("=" * 100)
            api_calls.clear()
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=60000)
                print(url, "->", resp.status if resp else None)
            except Exception as e:
                print(url, "goto failed:", repr(e))
            time.sleep(4)
            html = page.content()
            text = page.inner_text("body") if page.query_selector("body") else ""
            print("html", len(html), "text", len(text))
            print("---- visible text ----")
            print(text[:3500])
            print("---- json/api responses ----")
            for c in api_calls[:40]:
                print("  ", c)
            for marker in ("__NEXT_DATA__", "self.__next_f", "__NUXT__", "q:container", "astro-island", "props="):
                n = html.count(marker)
                if n:
                    print(f"  marker {marker!r}: {n}")
            m = re.search(r"astro-island[^>]*props=\"([^\"]{0,3000})", html)
            if m:
                print("astro props sample:", m.group(1)[:3000])
            time.sleep(6)
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("probe failed:", repr(e))
    sys.exit(0)
