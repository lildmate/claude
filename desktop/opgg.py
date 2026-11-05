#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier list and builds (also against one lane opponent) from op.gg.

op.gg serves the live patch. Its pages carry their data as Next.js flight
data (self.__next_f): the tier list's champions with position win/pick/ban
rates and tiers, a build page's rune pages with the client's rune ids, and
its item, spell and skill tables as rows ("core_items_3") of items, each
with its game count and win rate. ?target_champion=<key> gives the same page
for games against that champion.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests

from utils.core.logging import get_logger

log = get_logger()

SITE = "https://op.gg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/140.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
CACHE_TTL_S = 30 * 60
# Proteus position key -> op.gg's
POSITIONS = [("Top", "Top", "top", "TOP"), ("Jungle", "Jungle", "jungle", "JUNGLE"),
             ("Middle", "Mid", "mid", "MID"), ("Bot", "ADC", "adc", "ADC"), ("Supporter", "Support", "support", "SUPPORT")]
TIER_LETTERS = {0: "OP", 1: "S", 2: "A", 3: "B", 4: "C", 5: "D"}
FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
ROW = re.compile(r'\["\$","tr","([a-z_]+?)_(\d+)",')
META = re.compile(r'"metaType":"(item|spell|skill|rune|perk)","metaId":(\d+)')
GAMES = re.compile(r'"children":\["([\d,]+)"," ","Games"\]')
PERCENT = re.compile(r'"children":"(\d+(?:\.\d+)?)%"')
SKILL_KEY = re.compile(r'"children":"([QWER])"')


def flight(html: str) -> str:
    """A page's concatenated Next.js flight data."""
    return "".join(json.loads('"' + part + '"') for part in FLIGHT.findall(html))


def _objects_with(data: str, start: str, must: str, window: int = 400):
    """JSON objects in data that begin with start and hold must near their start."""
    decoder = json.JSONDecoder()
    for match in re.finditer(re.escape(start), data):
        if must not in data[match.start(): match.start() + window]:
            continue
        try:
            obj, _ = decoder.raw_decode(data, match.start())
        except ValueError:
            continue
        yield obj


def champion_keys(data: str) -> Dict[str, int]:
    """op.gg champion key -> champion id, from a page's champion list."""
    keys = {}
    for obj in _objects_with(data, '{"key":"', '"id":', window=60):
        try:
            keys[str(obj["key"])] = int(obj["id"])
        except (KeyError, TypeError, ValueError):
            continue
    return keys


def parse_tier_list(data: str, keys: Dict[str, int]) -> List[dict]:
    result = []
    for obj in _objects_with(data, '{"key":"', '"positionName"'):
        champion_id = keys.get(str(obj.get("key")))
        tier = obj.get("positionTierData") or {}
        if not champion_id or not tier.get("rank"):
            continue
        result.append({
            "championId": champion_id,
            "tier": TIER_LETTERS.get(tier.get("tier"), str(tier.get("tier"))),
            "tierNumber": tier.get("tier"),
            "rank": tier.get("rank"),
            "rankDelta": (tier.get("rank_prev") or tier.get("rank")) - tier.get("rank"),
            "winRate": round(float(obj.get("positionWinRate") or 0), 1),
            "pickRate": round(float(obj.get("positionPickRate") or 0), 1),
            "banRate": round(float(obj.get("positionBanRate") or 0), 1),
            "counters": [c.get("champion_id") for c in obj.get("positionCounters") or [] if c.get("champion_id")],
        })
    result.sort(key=lambda e: e["rank"])
    return result


def parse_runes(data: str) -> List[dict]:
    """The rune pages, most played first, as client ids."""
    i = data.find('"data":{"rune_pages"')
    if i < 0:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(data, i + len('"data":'))
    except ValueError:
        return []
    pages = []
    for page in obj.get("rune_pages") or []:
        for build in page.get("builds") or []:
            active = lambda rows: [r["id"] for row in rows or [] for r in row if r.get("isActive")]  # noqa: E731
            primary, secondary, shards = active(build.get("main_runes")), active(build.get("sub_runes")), active(build.get("shards"))
            style, sub = (build.get("primary_perk_style") or {}).get("id"), (build.get("perk_sub_style") or {}).get("id")
            if style and sub and len(primary) == 4 and len(secondary) == 2 and len(shards) == 3:
                pages.append({"runes": {"primaryStyle": style, "primary": primary, "subStyle": sub,
                                        "secondary": secondary, "shards": shards},
                              "games": int(page.get("play") or 0), "pickRate": page.get("pick_rate")})
                break
    return pages


def parse_rows(data: str) -> Dict[str, List[dict]]:
    """Table rows by group ('core_items', 'starter_items', ...): their ids, games and win rate."""
    groups: Dict[str, List[dict]] = {}
    marks = list(ROW.finditer(data))
    for n, mark in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else min(len(data), mark.end() + 8000)
        segment = data[mark.end(): end]
        ids = [int(i) for _, i in META.findall(segment)]
        games = GAMES.search(segment)
        percents = PERCENT.findall(segment)
        skills = SKILL_KEY.findall(segment)
        if not ids and not skills:
            continue
        groups.setdefault(mark.group(1), []).append({
            "ids": ids, "skills": skills,
            "games": int(games.group(1).replace(",", "")) if games else 0,
            "winRate": float(percents[-1]) if percents else None,
        })
    return groups


def _best(rows: List[dict]) -> Optional[dict]:
    return rows[0] if rows else None


class OpGG:
    def __init__(self, http_get: Optional[Callable] = None):
        self._get = http_get or (lambda url: requests.get(url, headers=HEADERS, timeout=25))
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _flight(self, path: str) -> str:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(path)
            if hit and now - hit[0] < CACHE_TTL_S:
                return hit[1]
        response = self._get(SITE + path)
        if response.status_code != 200:
            raise RuntimeError(f"op.gg {path}: HTTP {response.status_code}")
        data = flight(response.text)
        with self._lock:
            self._cache[path] = (now, data)
        return data

    def version(self, data: str) -> str:
        match = re.search(r'"metaLatestVersion":"([\d.]+)"', data)
        return match.group(1) if match else ""

    def keys(self) -> Dict[str, int]:
        return champion_keys(self._flight("/lol/champions?position=top"))

    def tier_list(self) -> dict:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(POSITIONS)) as pool:  # five pages at once
            pages = list(pool.map(lambda p: self._flight(f"/lol/champions?position={p[2]}"), POSITIONS))
        keys = champion_keys(pages[0])
        version = self.version(pages[0])
        positions = [{"key": key, "name": name, "champions": parse_tier_list(data, keys)}
                     for (key, name, _, _), data in zip(POSITIONS, pages)]
        return {"source": "op.gg", "version": version, "currentVersion": version, "region": "global",
                "rank": "Emerald+", "positions": positions}

    def champion_positions(self) -> Dict[int, List[str]]:
        """champion id -> its positions, most played first (Proteus keys)."""
        data = self._flight("/lol/champions?position=top")
        by_opgg = {p[3]: p[0] for p in POSITIONS}
        result = {}
        for obj in _objects_with(data, '{"key":"', '"positions":[', window=400):
            if "id" in obj:
                result[int(obj["id"])] = [by_opgg[p] for p in obj.get("positions") or [] if p in by_opgg]
        return result

    def build(self, champion_id: int, position: str, opponent_id: Optional[int] = None) -> Optional[dict]:
        keys = self.keys()
        by_id = {v: k for k, v in keys.items()}
        champ_key = by_id.get(int(champion_id))
        opgg_position = next((p[2] for p in POSITIONS if p[0] == position), None)
        if not champ_key or not opgg_position:
            return None
        path = f"/lol/champions/{champ_key}/build/{opgg_position}"
        if opponent_id and by_id.get(int(opponent_id)):
            path += f"?target_champion={by_id[int(opponent_id)]}"
        data = self._flight(path)
        runes = parse_runes(data)
        if not runes:
            return None
        rows = parse_rows(data)
        core = _best(rows.get("core_items", []))
        starter = _best(rows.get("starter_items", []))
        boots = _best(rows.get("boots", []))
        items = list(core["ids"]) if core else []
        if boots and boots["ids"]:
            items.insert(1, boots["ids"][0])
        for row in rows.get("last_items", [])[:3]:
            items.extend(i for i in row["ids"] if i not in items)
        return {
            "runes": runes[0]["runes"],
            "items": items,
            "startItems": list(starter["ids"]) if starter else [],
            "spells": [],  # not in op.gg's tables: filled from deeplol.gg
            "skills": [],
            "skillOrder": [],
            "games": runes[0]["games"],
            "coreWinRate": core["winRate"] if core else None,
            "version": self.version(data),
        }
