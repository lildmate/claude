#!/usr/bin/env python3
"""Temporary: prints how the tier list and build sites carry their data (run on CI)."""

import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
PAGES = [
    "https://u.gg/lol/tier-list",
    "https://op.gg/lol/champions?position=mid",
    "https://lolalytics.com/lol/tierlist/",
    "https://www.onetricks.gg/champions/builds/ahri",
    "https://www.onetricks.gg/en/champions/builds/ahri",
    "https://www.onetricks.gg/champions/ranking/ahri",
]


def probe(url):
    print("=" * 100)
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except Exception as e:
        print(url, "FAILED", repr(e))
        return
    t = r.text
    print(url, "->", r.status_code, r.url, len(t), "chars", r.headers.get("content-type"))
    scripts = re.findall(r'<script([^>]*)>', t)
    print("script tags:", len(scripts))
    for s in scripts[:40]:
        if "src=" in s or "id=" in s or "type=" in s:
            print("   ", s.strip()[:160])
    for marker in ("__NEXT_DATA__", "__SSR_DATA__", "__INITIAL_STATE__", "window.__", "self.__next_f",
                   "q:container", "qwik", "application/ld+json", "__NUXT__", "tierlist", "tier_list",
                   "winRate", "win_rate", "winrate", "pickRate", "pick_rate", "Electrocute", "Ahri", "Aatrox",
                   "stats2.u.gg", "api.op.gg", "ax.lolalytics", "lolalytics.com/mega", "/api/"):
        n = t.count(marker)
        if n:
            print(f"  {marker!r}: {n}")
    for marker in ("Aatrox", "Electrocute", "winRate", "win_rate", "Ahri"):
        i = t.find(marker)
        if i >= 0:
            print(f"--- context of {marker!r} ---")
            print(t[max(0, i - 600): i + 900].replace("\n", " "))
            break
    apis = sorted(set(re.findall(r'https?://[a-z0-9.-]*(?:api|stats|ax|a1|mega)[a-z0-9.-]*\.[a-z]+/[^"\'\s<>)]{0,80}', t)))
    print("api-looking urls:", apis[:25])


if __name__ == "__main__":
    for u in PAGES:
        probe(u)
    sys.exit(0)
