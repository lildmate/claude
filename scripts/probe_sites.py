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


for url in ["https://op.gg/lol/champions/darius/build/top?target_champion=garen",
            "https://op.gg/lol/champions?position=top"]:
    print("=" * 100)
    r = requests.get(url, headers=UA, timeout=30)
    data = flight(r.text)
    print(url, r.status_code, "flight chars", len(data))
    i = data.find('"rune_pages"')
    j = data.find('"sub_runes"', i)
    print("rune page tail:", data[j - 100: j + 1500] if j > 0 else "no sub_runes")
    for needle in ('"core_items"', '"starter_items"', '"boots"', '"summoner_spells"', '"skill_masteries"',
                   '"skills"', '"stat_mods"', '"positions"', '"champion_id":', '"average_stats"', '"tier":'):
        if needle in data:
            show(data, needle, width=1200, count=1)
        else:
            print("absent:", needle)
sys.exit(0)
