#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier list and builds from deeplol.gg, and applying a build's runes and
summoner spells in champion select.

deeplol.gg serves its statistics as JSON (b2c-api-cdn.deeplol.gg): per patch,
region and rank, each champion's tier, win/pick/ban rate per position, and
per position the most played builds with their rune, item, summoner spell and
skill ids, the ids the client itself uses.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests

from utils.core.logging import get_logger

log = get_logger()

API = "https://b2c-api-cdn.deeplol.gg"
REGION = "KR"  # the largest sample
RANK = "Emerald+"
CACHE_TTL_S = 30 * 60
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Proteus", "Origin": "https://www.deeplol.gg",
           "Referer": "https://www.deeplol.gg/"}
POSITIONS = [("Top", "Top"), ("Jungle", "Jungle"), ("Middle", "Mid"), ("Bot", "ADC"), ("Supporter", "Support")]
POSITION_KEYS = {key for key, _ in POSITIONS}
# deeplol's tier number -> the letter players know
TIER_LETTERS = {0: "OP", 1: "S", 2: "A", 3: "B", 4: "C", 5: "D"}
PAGE_PREFIX = "Proteus"


class DeepLol:
    def __init__(self, http_get: Optional[Callable] = None):
        self._get = http_get or (lambda url, params: requests.get(url, params=params, headers=HEADERS, timeout=20))
        self._cache: Dict[Tuple, Tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _json(self, path: str, **params):
        key = (path, tuple(sorted(params.items())))
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < CACHE_TTL_S:
                return hit[1]
        response = self._get(API + path, params)
        if response.status_code != 200:
            raise RuntimeError(f"deeplol.gg {path}: HTTP {response.status_code}")
        data = response.json()
        with self._lock:
            self._cache[key] = (now, data)
        return data

    def version(self) -> str:
        """The newest patch with enough games (deeplol lists the current one first only once filled)."""
        data = self._json("/champion/version", cnt=2)
        versions = data.get("game_version_list") or []
        if not versions:
            raise RuntimeError("deeplol.gg lists no patch")
        return str(versions[0])

    def tier_list(self) -> dict:
        version = self.version()
        data = self._json("/champion/rank", platform_id=REGION, tier=RANK, game_version=version)
        positions: Dict[str, List[dict]] = {key: [] for key, _ in POSITIONS}
        for champ in data.get("champion_data_list") or []:
            try:
                champion_id = int(champ.get("champion_id"))
            except (TypeError, ValueError):
                continue
            for key, perf in (champ.get("performance_dict") or {}).items():
                if key not in POSITION_KEYS or not perf or not perf.get("rank"):
                    continue
                positions[key].append({
                    "championId": champion_id,
                    "tier": TIER_LETTERS.get(perf.get("tier"), str(perf.get("tier"))),
                    "tierNumber": perf.get("tier"),
                    "rank": perf.get("rank"),
                    "rankDelta": perf.get("rank_delta") or 0,
                    "winRate": round(100 * float(perf.get("win_rate") or 0), 1),
                    "pickRate": round(100 * float(perf.get("pick_rate") or 0), 1),
                    "banRate": round(100 * float(perf.get("ban_rate") or 0), 1),
                })
        for entries in positions.values():
            entries.sort(key=lambda e: e["rank"])
        return {"source": "deeplol.gg", "version": version, "region": REGION, "rank": RANK,
                "positions": [{"key": key, "name": name, "champions": positions[key]} for key, name in POSITIONS]}

    def builds(self, champion_id: int) -> dict:
        version = self.version()
        data = self._json("/champion/build", platform_id=REGION, champion_id=int(champion_id),
                          game_version=version, tier=RANK)
        lanes = []
        for key, name in POSITIONS:
            lane = (data.get("build_by_lane") or {}).get(key) or {}
            builds = [parse_build(b) for b in lane.get("build_lst") or []]
            builds = [b for b in builds if b]
            if builds:
                lanes.append({"key": key, "name": name, "builds": builds})
        return {"source": "deeplol.gg", "version": version, "championId": int(champion_id), "lanes": lanes}


def parse_build(raw: dict) -> Optional[dict]:
    rune = raw.get("rune") or {}
    main, sub, stats = rune.get("main_build") or [], rune.get("sub_build") or [], rune.get("stat_build") or []
    if len(main) < 5 or len(sub) < 3 or len(stats) < 3:
        return None
    return {
        "runes": {"primaryStyle": main[0], "primary": main[1:5], "subStyle": sub[0], "secondary": sub[1:3],
                  "shards": stats[:3]},
        "items": list((raw.get("item") or {}).get("build") or []),
        "startItems": list((raw.get("start_item") or {}).get("build") or []),
        "spells": list((raw.get("spell") or {}).get("build") or [])[:2],
        "skills": list((raw.get("skill") or {}).get("build") or []),
        "skillOrder": list((raw.get("skill") or {}).get("detail") or []),
    }


class ChampSelect:
    """Applies a build in champion select through the client."""

    def __init__(self, lcu):
        self.lcu = lcu

    def _ok(self) -> bool:
        try:
            return bool(self.lcu is not None and self.lcu.ok)
        except Exception:
            return False

    def locked(self) -> Optional[dict]:
        """The champion locked (or hovered) in champion select, with the assigned position."""
        if not self._ok():
            return None
        session = self.lcu.get("/lol-champ-select/v1/session", timeout=2)
        if not isinstance(session, dict):
            return None
        me = next((p for p in session.get("myTeam") or [] if p.get("cellId") == session.get("localPlayerCellId")), None)
        if not me or not me.get("championId"):
            return None
        locked = False
        for group in session.get("actions") or []:
            for action in group:
                if action.get("actorCellId") == me.get("cellId") and action.get("type") == "pick":
                    locked = bool(action.get("completed"))
        return {"championId": int(me["championId"]), "locked": locked,
                "position": (me.get("assignedPosition") or "").lower()}

    def apply_runes(self, name: str, runes: dict) -> None:
        if not self._ok():
            raise RuntimeError("A League kliens nem fut")
        session, base = self.lcu.s, self.lcu.base
        pages = session.get(base + "/lol-perks/v1/pages", timeout=5).json() or []
        own = [p for p in pages if str(p.get("name", "")).startswith(PAGE_PREFIX) and p.get("isDeletable")]
        editable = [p for p in pages if p.get("isDeletable")]
        to_delete = own[:1]
        if not to_delete:
            inventory = session.get(base + "/lol-perks/v1/inventory", timeout=5).json() or {}
            owned = int(inventory.get("ownedPageCount") or 0)
            if owned and len(editable) >= owned:
                current = next((p for p in editable if p.get("current")), editable[0] if editable else None)
                to_delete = [current] if current else []
        for page in to_delete:
            session.delete(f"{base}/lol-perks/v1/pages/{page['id']}", timeout=5)
        body = {
            "name": f"{PAGE_PREFIX}: {name}"[:25],
            "primaryStyleId": runes["primaryStyle"],
            "subStyleId": runes["subStyle"],
            "selectedPerkIds": list(runes["primary"]) + list(runes["secondary"]) + list(runes["shards"]),
            "current": True,
        }
        response = session.post(base + "/lol-perks/v1/pages", json=body, timeout=5)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"A kliens nem fogadta el a rúnaoldalt ({response.status_code})")

    def apply_spells(self, spells: List[int]) -> None:
        if not self._ok() or len(spells) < 2:
            return
        self.lcu.patch("/lol-champ-select/v1/session/my-selection",
                       {"spell1Id": int(spells[0]), "spell2Id": int(spells[1])}, timeout=5)
