#!/usr/bin/env python3
"""Temporary: deeplol.gg 16.22 data, and matchup builds on op.gg / lolalytics (run on CI)."""

import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
DL = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.deeplol.gg", "Referer": "https://www.deeplol.gg/"}

print("== deeplol 16.22 ==")
for path, params in [("/champion/rank", {"platform_id": "KR", "tier": "Emerald+", "game_version": "16.22"}),
                     ("/champion/build", {"platform_id": "KR", "champion_id": 122, "game_version": "16.22", "tier": "Emerald+"}),
                     ("/champion/rank", {"platform_id": "KR", "tier": "Emerald+", "game_version": "16.21"})]:
    r = requests.get("https://b2c-api-cdn.deeplol.gg" + path, params=params, headers=DL, timeout=20)
    t = r.text
    print(path, params.get("game_version"), r.status_code, len(t), t[:300])
    try:
        d = r.json()
        if "champion_data_list" in d:
            ranked = sum(1 for c in d["champion_data_list"] for p in (c.get("performance_dict") or {}).values() if p and p.get("rank"))
            print("   champions", len(d["champion_data_list"]), "ranked entries", ranked)
        if "build_by_lane" in d:
            print("   lanes", {k: len(v.get("build_lst") or []) for k, v in d["build_by_lane"].items()})
    except Exception as e:
        print("   not json", e)

for url in ["https://op.gg/lol/champions/darius/build/top?target_champion=garen",
            "https://op.gg/lol/champions/darius/build/top",
            "https://op.gg/lol/champions/darius/counters/top?target_champion=garen",
            "https://lolalytics.com/lol/darius/vs/garen/build/",
            "https://lolalytics.com/lol/darius/build/"]:
    print("=" * 90)
    r = requests.get(url, headers=UA, timeout=30)
    t = r.text
    print(url, r.status_code, len(t))
    for kw in ("Conqueror", "Stridebreaker", "Black Cleaver", "Sterak", "Garen", "target_champion", "games", "Win Rate"):
        print(f"   {kw!r}: {t.count(kw)}")
    items = re.findall(r'alt="([A-Z][A-Za-z\' ]{3,30})"', t)
    print("   alts:", items[:40])
    m = re.search(r'Garen.{0,300}', t)
    if m:
        print("   garen ctx:", m.group(0)[:300].replace("\n", " "))
sys.exit(0)
