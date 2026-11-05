#!/usr/bin/env python3
"""Temporary: runs desktop.opgg on the live op.gg (run on CI)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.opgg import OpGG, parse_rows  # noqa: E402

op = OpGG()
tiers = op.tier_list()
print("tier list version", tiers["version"])
for p in tiers["positions"]:
    print(p["name"], len(p["champions"]), json.dumps(p["champions"][:3]))
keys = op.keys()
print("keys", len(keys), "darius", keys.get("darius"), "garen", keys.get("garen"))
pos = op.champion_positions()
print("positions darius", pos.get(122), "garen", pos.get(86), "sejuani", pos.get(113))
data = op._flight("/lol/champions/darius/build/top?target_champion=garen")
rows = parse_rows(data)
for group, entries in rows.items():
    print("ROWS", group, len(entries), json.dumps(entries[:2]))
print("BUILD vs garen", json.dumps(op.build(122, "Top", 86)))
print("BUILD general", json.dumps(op.build(122, "Top")))
print("BUILD ahri mid", json.dumps(op.build(103, "Middle")))
