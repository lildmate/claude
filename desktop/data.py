#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data for the Proteus window: champions, skins, images, profile, match history.

Game data (champions, skins and their images) comes from the League client
when it runs, in its language, else from CommunityDragon, which mirrors the
client's game data. Profile and match history only come from the client.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from utils.core.logging import get_logger

log = get_logger()

GAME_DATA_PREFIX = "/lol-game-data/assets/"
CDRAGON_BASE = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/"
JSON_TTL_S = 6 * 60 * 60
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

RARITIES = {
    "kEpic": "Epic",
    "kLegendary": "Legendary",
    "kUltimate": "Ultimate",
    "kMythic": "Mythic",
    "kTranscendent": "Transcendent",
    "kExalted": "Exalted",
}

QUEUES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Normal Draft",
    430: "Normal Blind",
    480: "Swiftplay",
    490: "Quickplay",
    450: "ARAM",
    1700: "Arena",
    1900: "URF",
    900: "ARURF",
    0: "Egyéni",
}

TIERS = {
    "IRON": "Iron", "BRONZE": "Bronze", "SILVER": "Silver", "GOLD": "Gold", "PLATINUM": "Platinum",
    "EMERALD": "Emerald", "DIAMOND": "Diamond", "MASTER": "Master", "GRANDMASTER": "Grandmaster",
    "CHALLENGER": "Challenger",
}


def cdragon_url(asset_path: str) -> Optional[str]:
    """The CommunityDragon address of a client game-data path (it lowercases them)."""
    if not asset_path.startswith(GAME_DATA_PREFIX):
        return None
    rest = asset_path[len(GAME_DATA_PREFIX):].split("?", 1)[0]
    if not rest or ".." in rest.split("/"):
        return None
    return CDRAGON_BASE + rest.lower()


def image_url(asset_path: Optional[str]) -> Optional[str]:
    """The window's address for a game-data image (served by /img)."""
    if not asset_path or not asset_path.startswith(GAME_DATA_PREFIX):
        return None
    return "/img?p=" + requests.utils.quote(asset_path, safe="/._-")


class GameData:
    """Champions, skins and images, from the client or CommunityDragon."""

    def __init__(self, lcu=None, cache_dir: Optional[Path] = None,
                 http_get: Optional[Callable[..., Any]] = None):
        self.lcu = lcu
        self.cache_dir = cache_dir
        self._http_get = http_get or requests.get
        self._json: Dict[Tuple[str, str], Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    # -- sources -------------------------------------------------------------

    def _client_ok(self) -> bool:
        try:
            return bool(self.lcu is not None and self.lcu.ok)
        except Exception:
            return False

    def _get_json(self, path: str) -> Optional[Any]:
        source = "client" if self._client_ok() else "cdragon"
        key = (source, path)
        now = time.monotonic()
        with self._lock:
            hit = self._json.get(key)
            if hit and now - hit[0] < JSON_TTL_S:
                return hit[1]
        data = None
        if source == "client":
            try:
                data = self.lcu.get(path, timeout=5)
            except Exception as e:
                log.debug("[Window] Client game data %s failed: %s", path, e)
        if data is None:
            url = cdragon_url(path)
            if url:
                try:
                    response = self._http_get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                except Exception as e:
                    log.debug("[Window] CommunityDragon %s failed: %s", url, e)
        if data is not None:
            with self._lock:
                self._json[key] = (now, data)
        return data

    def image(self, asset_path: str) -> Optional[Tuple[bytes, str]]:
        """An image's bytes and type: disk cache, then the client, then CommunityDragon."""
        if not asset_path.startswith(GAME_DATA_PREFIX) or ".." in asset_path:
            return None
        suffix = Path(asset_path.split("?", 1)[0]).suffix.lower()
        content_type = IMAGE_TYPES.get(suffix)
        if not content_type:
            return None
        cached = self._cache_file(asset_path, suffix)
        if cached and cached.is_file():
            try:
                return cached.read_bytes(), content_type
            except OSError:
                pass
        body = None
        if self._client_ok():
            try:
                response = self.lcu.s.get(self.lcu.base + asset_path, timeout=8)
                if response.status_code == 200 and response.content:
                    body = response.content
            except Exception as e:
                log.debug("[Window] Client image %s failed: %s", asset_path, e)
        if body is None:
            url = cdragon_url(asset_path)
            if url:
                try:
                    response = self._http_get(url, timeout=15)
                    if response.status_code == 200 and response.content:
                        body = response.content
                except Exception as e:
                    log.debug("[Window] CommunityDragon image %s failed: %s", url, e)
        if body is None:
            return None
        if cached:
            try:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(body)
            except OSError as e:
                log.debug("[Window] Could not cache %s: %s", asset_path, e)
        return body, content_type

    def _cache_file(self, asset_path: str, suffix: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha1(asset_path.encode("utf-8")).hexdigest()
        return self.cache_dir / digest[:2] / (digest + suffix)

    # -- champions and skins ---------------------------------------------------

    def champions(self) -> List[dict]:
        """Every champion, sorted by name."""
        data = self._get_json(GAME_DATA_PREFIX + "v1/champion-summary.json") or []
        result = []
        for champ in data:
            try:
                champ_id = int(champ.get("id", -1))
            except (TypeError, ValueError):
                continue
            if champ_id <= 0:
                continue
            result.append({
                "id": champ_id,
                "name": champ.get("name") or champ.get("alias") or str(champ_id),
                "alias": champ.get("alias") or "",
                "roles": champ.get("roles") or [],
                "icon": image_url(champ.get("squarePortraitPath")),
            })
        result.sort(key=lambda c: c["name"].casefold())
        return result

    def champion_name(self, champion_id: int) -> str:
        for champ in self.champions():
            if champ["id"] == champion_id:
                return champ["name"]
        return f"#{champion_id}"

    def champion(self, champion_id: int, owned: Optional[set] = None,
                 favorites: Optional[set] = None) -> Optional[dict]:
        """A champion and its skins."""
        data = self._get_json(f"{GAME_DATA_PREFIX}v1/champions/{int(champion_id)}.json")
        if not isinstance(data, dict) or not data.get("skins"):
            return None
        owned = owned or set()
        favorites = favorites or set()
        skins = []
        for skin in data.get("skins", []):
            try:
                skin_id = int(skin.get("id"))
            except (TypeError, ValueError):
                continue
            is_base = bool(skin.get("isBase"))
            skins.append({
                "id": skin_id,
                "name": skin.get("name") or str(skin_id),
                "isBase": is_base,
                "rarity": RARITIES.get(skin.get("rarity") or "", ""),
                "legacy": bool(skin.get("isLegacy")),
                "chromas": len(skin.get("chromas") or []),
                "owned": is_base or skin_id in owned,
                "favorite": skin_id in favorites,
                "tile": image_url(skin.get("tilePath")),
                "splash": image_url(skin.get("uncenteredSplashPath") or skin.get("splashPath")),
                "loadScreen": image_url(skin.get("loadScreenPath")),
            })
        return {
            "id": int(data.get("id", champion_id)),
            "name": data.get("name") or str(champion_id),
            "title": data.get("title") or "",
            "icon": image_url(data.get("squarePortraitPath")),
            "skins": skins,
        }

    def skin(self, skin_id: int) -> Optional[dict]:
        """One skin with its champion's name (a skin's champion is its id // 1000)."""
        champ = self.champion(int(skin_id) // 1000)
        if not champ:
            return None
        for skin in champ["skins"]:
            if skin["id"] == int(skin_id):
                return dict(skin, championId=champ["id"], championName=champ["name"])
        return None


class ClientData:
    """The player's own data from the League client."""

    def __init__(self, lcu, game: GameData):
        self.lcu = lcu
        self.game = game

    def connected(self) -> bool:
        try:
            return bool(self.lcu is not None and self.lcu.ok)
        except Exception:
            return False

    def phase(self) -> Optional[str]:
        if not self.connected():
            return None
        try:
            return self.lcu.phase
        except Exception:
            return None

    def owned_skins(self) -> set:
        if not self.connected():
            return set()
        try:
            return set(self.lcu.owned_skins() or [])
        except Exception:
            return set()

    def summoner(self) -> Optional[dict]:
        if not self.connected():
            return None
        data = self.lcu.get("/lol-summoner/v1/current-summoner", timeout=3)
        if not isinstance(data, dict):
            return None
        icon_id = data.get("profileIconId")
        return {
            "name": data.get("gameName") or data.get("displayName") or "",
            "tag": data.get("tagLine") or "",
            "level": data.get("summonerLevel"),
            "icon": image_url(f"{GAME_DATA_PREFIX}v1/profile-icons/{icon_id}.jpg") if icon_id is not None else None,
        }

    def ranked(self) -> dict:
        if not self.connected():
            return {}
        data = self.lcu.get("/lol-ranked/v1/current-ranked-stats", timeout=3)
        queue_map = data.get("queueMap", {}) if isinstance(data, dict) else {}
        result = {}
        for key, name in (("RANKED_SOLO_5x5", "solo"), ("RANKED_FLEX_SR", "flex")):
            entry = queue_map.get(key) or {}
            tier = (entry.get("tier") or "").upper()
            wins, losses = int(entry.get("wins") or 0), int(entry.get("losses") or 0)
            result[name] = {
                "tier": TIERS.get(tier, ""),
                "division": "" if tier in ("MASTER", "GRANDMASTER", "CHALLENGER") else (entry.get("division") or ""),
                "lp": int(entry.get("leaguePoints") or 0),
                "wins": wins,
                "losses": losses,
                "winrate": round(100 * wins / (wins + losses)) if wins + losses else None,
            }
        return result

    def matches(self, count: int = 20) -> List[dict]:
        if not self.connected():
            return []
        data = self.lcu.get(
            f"/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex={max(0, count - 1)}",
            timeout=5,
        )
        games = (data or {}).get("games", {}).get("games", []) if isinstance(data, dict) else []
        result = []
        for game in games:
            participants = game.get("participants") or []
            if not participants:
                continue
            me = participants[0]
            stats = me.get("stats") or {}
            champion_id = int(me.get("championId") or 0)
            queue_id = int(game.get("queueId") or 0)
            result.append({
                "gameId": game.get("gameId"),
                "championId": champion_id,
                "championName": self.game.champion_name(champion_id) if champion_id else "",
                "championIcon": image_url(f"{GAME_DATA_PREFIX}v1/champion-icons/{champion_id}.png") if champion_id else None,
                "win": bool(stats.get("win")),
                "kills": int(stats.get("kills") or 0),
                "deaths": int(stats.get("deaths") or 0),
                "assists": int(stats.get("assists") or 0),
                "cs": int(stats.get("totalMinionsKilled") or 0) + int(stats.get("neutralMinionsKilled") or 0),
                "queue": QUEUES.get(queue_id, game.get("gameMode") or ""),
                "duration": int(game.get("gameDuration") or 0),
                "createdAt": int(game.get("gameCreation") or 0),
            })
        result.sort(key=lambda m: m["createdAt"], reverse=True)
        return result[:count]
