#!/usr/bin/env python3
"""Temporary: the data op.gg embeds in its build and tier list pages (run on CI)."""

import json
import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def flight(html):
    """The concatenated Next.js flight data of a page."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    return "".join(json.loads('"' + p + '"') for p in parts)


def show(data, needle, width=1600, count=2):
    i, n = 0, 0
    while n < count:
        i = data.find(needle, i)
        if i < 0:
            break
        print(f"--- {needle!r} @ {i} ---")
        print(data[max(0, i - 500): i + width])
        i += len(needle)
        n += 1


url = "https://op.gg/lol/champions/darius/build/top?target_champion=garen"
r = requests.get(url, headers=UA, timeout=30)
data = flight(r.text)
print(url, r.status_code, len(data))
for needle in ('6631', '"ids"', '"skill', '"spell', 'SummonerFlash', '"item_', '"starter', '"core', '"last_items"', '"boots'):
    found = [m.start() for m in re.finditer(re.escape(needle), data)]
    print(needle, "hits", len(found), found[:8])
for needle in ('6631', '"ids"', '"skill'):
    show(data, needle, width=900, count=2)
sys.exit(0)
