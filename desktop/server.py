#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Proteus window's local server.

Serves the window's page (desktop/web) and a small JSON API on 127.0.0.1.
Only the window can use it: every API and image request carries a random
token the window got in its address, and requests addressed to any other
host name (DNS rebinding) are refused. No CORS headers are sent, so other
pages can neither read the API nor send it the token header.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from utils.core.logging import get_logger

from .data import ClientData, GameData
from .store import Favorites, NextSkins

log = get_logger()

MAX_BODY = 16 * 1024
MAX_UPLOAD = 4 * 1024 * 1024 * 1024  # map mods can take a few GB
UPLOAD_CHUNK = 1024 * 1024


def web_dir() -> Path:
    """The window's page files (bundled under _internal in a frozen build)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "desktop" / "web"
    return Path(__file__).resolve().parent / "web"


class AppAPI:
    """What the window's page asks for."""

    def __init__(self, game: GameData, client: ClientData, favorites: Favorites, next_skins: NextSkins,
                 version: str = "", open_folder: Optional[Callable[[str], bool]] = None,
                 settings: Optional[dict] = None, patch_notes=None, mods=None,
                 upload_dir: Optional[Path] = None, meta=None, champ_select=None, opgg=None):
        self.meta = meta
        self.opgg = opgg
        self.champ_select = champ_select
        self.patch_notes = patch_notes
        self.mods = mods
        self.upload_dir = upload_dir
        self.game = game
        self.client = client
        self.favorites = favorites
        self.next_skins = next_skins
        self.version = version
        self.open_folder = open_folder
        self.settings = settings or {}

    def status(self) -> dict:
        connected = self.client.connected()
        return {
            "version": self.version,
            "client": {"connected": connected, "phase": self.client.phase() if connected else None},
            "time": int(time.time() * 1000),
        }

    def champions(self) -> dict:
        return {"champions": self.game.champions()}

    def champion(self, champion_id: int) -> Optional[dict]:
        champ = self.game.champion(champion_id, owned=self.client.owned_skins(), favorites=self.favorites.all())
        if champ is None:
            return None
        champ["nextSkinId"] = self.next_skins.for_champion(champion_id)
        return champ

    def favorite_skins(self) -> dict:
        skins = []
        for skin_id in sorted(self.favorites.all()):
            skin = self.game.skin(skin_id)
            if skin:
                skins.append(skin)
        skins.sort(key=lambda s: (s["championName"].casefold(), s["name"].casefold()))
        return {"skins": skins}

    def latest_patch_notes(self) -> dict:
        notes = self.patch_notes.latest() if self.patch_notes else None
        if not notes:
            return {"available": False}
        icons = {}
        for champ in self.game.champions():
            icons[champ["name"].casefold()] = champ["icon"]
            if champ.get("alias"):
                icons.setdefault(champ["alias"].casefold(), champ["icon"])
        champions = [dict(c, icon=icons.get(c["name"].casefold())) for c in notes["champions"]]
        return dict(notes, champions=champions, available=True)

    def _champion_index(self) -> dict:
        return {c["id"]: c for c in self.game.champions()}

    def tier_list(self, rank: Optional[str] = None) -> dict:
        """op.gg's tier list (the live patch), with deeplol.gg's win rate next to it."""
        data = None
        if self.opgg:
            try:
                data = self.opgg.tier_list(rank)
            except Exception as e:
                log.warning("[Window] op.gg tier list failed: %s", e)
        deeplol = None
        if self.meta:
            try:
                deeplol = self.meta.tier_list()
            except Exception as e:
                log.warning("[Window] deeplol.gg tier list failed: %s", e)
        if data is None:
            if deeplol is None:
                return {"available": False}
            data, deeplol = deeplol, None
        champs = self._champion_index()
        other = {}
        if deeplol:
            for position in deeplol["positions"]:
                for entry in position["champions"]:
                    other[(position["key"], entry["championId"])] = entry["winRate"]
        for position in data["positions"]:
            for entry in position["champions"]:
                champ = champs.get(entry["championId"]) or {}
                entry["name"] = champ.get("name") or f"#{entry['championId']}"
                entry["icon"] = champ.get("icon")
                entry["otherWinRate"] = other.get((position["key"], entry["championId"]))
        return dict(data, available=True, otherSource=(f"deeplol.gg {deeplol['version']}" if deeplol else None))

    def _lane_builds(self, champion_id: int, opponent_id: Optional[int] = None,
                     rank: Optional[str] = None) -> Tuple[List[dict], str, str]:
        """Per lane: op.gg's build (against the opponent when given), then deeplol.gg's."""
        deeplol = {"lanes": [], "version": ""}
        if self.meta:
            try:
                deeplol = self.meta.builds(champion_id)
            except Exception as e:
                log.warning("[Window] deeplol.gg build failed: %s", e)
        positions = []
        if self.opgg:
            try:
                positions = self.opgg.champion_positions().get(int(champion_id), [])
            except Exception as e:
                log.warning("[Window] op.gg positions failed: %s", e)
        lane_names = {"Top": "Top", "Jungle": "Jungle", "Middle": "Mid", "Bot": "ADC", "Supporter": "Support"}
        order = positions + [l["key"] for l in deeplol["lanes"] if l["key"] not in positions]  # noqa: E741
        lanes, version = [], ""
        for key in order:
            builds = []
            dl = next((l["builds"] for l in deeplol["lanes"] if l["key"] == key), [])  # noqa: E741
            if self.opgg and key in positions:
                try:
                    op = self.opgg.build(champion_id, key, opponent_id, rank)
                except Exception as e:
                    log.warning("[Window] op.gg build failed: %s", e)
                    op = None
                if op:
                    version = version or op.get("version") or ""
                    if dl:  # spells and skills only come from deeplol.gg
                        op["spells"], op["skills"], op["skillOrder"] = dl[0]["spells"], dl[0]["skills"], dl[0]["skillOrder"]
                    op["source"] = "op.gg KR " + op.get("rank", "") + (" · ellenfél ellen" if opponent_id else "")
                    builds.append(op)
            for b in dl:
                builds.append(dict(b, source="deeplol.gg KR Emerald+ " + deeplol["version"]))
            if builds:
                lanes.append({"key": key, "name": lane_names.get(key, key), "builds": builds})
        return lanes, version or deeplol.get("version", ""), deeplol.get("currentVersion") or version

    def builds(self, champion_id: int, opponent_id: Optional[int] = None, rank: Optional[str] = None) -> dict:
        if not self.meta and not self.opgg:
            return {"available": False}
        lanes, version, current = self._lane_builds(champion_id, opponent_id, rank)
        perks, styles = self.game.lookup("perks"), self.game.lookup("styles")
        items, spells = self.game.lookup("items"), self.game.lookup("spells")
        named = lambda table, ids: [dict(table.get(int(i), {"name": str(i), "icon": None}), id=int(i)) for i in ids]  # noqa: E731
        for lane in lanes:
            for build in lane["builds"]:
                r = build["runes"]
                build["view"] = {
                    "primaryStyle": named(styles, [r["primaryStyle"]])[0],
                    "subStyle": named(styles, [r["subStyle"]])[0],
                    "primary": named(perks, r["primary"]),
                    "secondary": named(perks, r["secondary"]),
                    "shards": named(perks, r["shards"]),
                    "items": named(items, build["items"]),
                    "startItems": named(items, build["startItems"]),
                    "spells": named(spells, build["spells"]),
                }
                build["runePagesView"] = [{
                    "games": page.get("games"), "pickRate": page.get("pickRate"),
                    "primaryStyle": named(styles, [page["runes"]["primaryStyle"]])[0],
                    "subStyle": named(styles, [page["runes"]["subStyle"]])[0],
                    "primary": named(perks, page["runes"]["primary"]),
                    "secondary": named(perks, page["runes"]["secondary"]),
                    "shards": named(perks, page["runes"]["shards"]),
                } for page in build.get("runePages") or []]
        index = self._champion_index()
        champ = index.get(int(champion_id)) or {}
        opponent = index.get(int(opponent_id)) if opponent_id else None
        return {"available": True, "source": "op.gg + deeplol.gg", "version": version, "currentVersion": current or version,
                "championId": int(champion_id), "championName": champ.get("name") or "", "championIcon": champ.get("icon"),
                "opponent": {"id": opponent["id"], "name": opponent["name"], "icon": opponent["icon"]} if opponent else None,
                "lanes": lanes}

    def champ_select_state(self) -> dict:
        state = self.champ_select.locked() if self.champ_select else None
        if not state:
            return {"inChampSelect": False}
        guess = None
        if self.opgg and state.get("enemies"):
            try:
                positions = self.opgg.champion_positions()
                mine = state.get("position") or (positions.get(state["championId"]) or [None])[0]
                main = [e for e in state["enemies"] if (positions.get(e) or [None])[0] == mine]
                any_ = [e for e in state["enemies"] if mine in (positions.get(e) or [])]
                guess = (main or any_ or [None])[0]
                state["position"] = mine
            except Exception as e:
                log.debug("[Window] Opponent guess failed: %s", e)
        return {"inChampSelect": True, **state, "opponentGuess": guess}

    def _setting(self, key: str, default=None):
        try:
            return (self.settings.get("get") or (lambda: {}))().get(key, default)
        except Exception:
            return default

    def _guess_opponent(self, champion_id: Optional[int], position: Optional[str], enemies: List[int]):
        """(your position, the enemy most likely in your lane) by op.gg's main positions."""
        if not self.opgg or not enemies:
            return position, None
        try:
            positions = self.opgg.champion_positions()
        except Exception as e:
            log.debug("[Window] Opponent guess failed: %s", e)
            return position, None
        mine = position or ((positions.get(champion_id) or [None])[0] if champion_id else None)
        if not mine:
            return None, None
        main = [e for e in enemies if (positions.get(e) or [None])[0] == mine]
        any_ = [e for e in enemies if mine in (positions.get(e) or [])]
        return mine, (main or any_ or [None])[0]

    def game_state(self) -> dict:
        """The Game page: queue, champion select (both teams, your lane opponent) or the game."""
        state = self.champ_select.game_state() if self.champ_select else {"phase": "Offline"}
        enemies = state.get("enemies") or []
        if state.get("phase") == "ChampSelect":
            mine = next((a for a in state.get("allies") or [] if a.get("me")), None)
            hovered = state.get("championId") or (mine or {}).get("championId") or None
            position, guess = self._guess_opponent(hovered, state.get("position"), enemies)
            state.update(position=position, opponentGuess=guess, autoRunes=self._auto_status)
        index = self._champion_index()
        live = state.get("live")
        if live:
            by_alias = {str(c.get("alias") or "").casefold(): cid for cid, c in index.items()}
            by_name = {str(c.get("name") or "").casefold(): cid for cid, c in index.items()}
            items = self.game.lookup("items")
            for player in live["players"]:
                cid = by_alias.get(player["alias"].casefold()) or by_name.get(player["championName"].casefold())
                player["championId"] = cid
                player["itemViews"] = [dict(items.get(i, {"name": str(i), "icon": None}), id=i) for i in player["items"]]
            me = next((p for p in live["players"] if p["me"]), None)
            if me:
                state["championId"] = me["championId"] or state.get("championId")
                state["position"] = me["position"] or state.get("position")
                rivals = [p for p in live["players"] if p["team"] != me["team"]]
                lane = next((p for p in rivals if p["position"] and p["position"] == state["position"]), None)
                state["enemies"] = enemies = [p["championId"] for p in rivals if p["championId"]]
                state["opponentGuess"] = lane["championId"] if lane else self._guess_opponent(
                    state["championId"], state["position"], enemies)[1]
        current = state.get("currentRunes")
        if current and current.get("runes"):
            perks, styles = self.game.lookup("perks"), self.game.lookup("styles")
            view = lambda table, ids: [dict(table.get(int(i), {"name": str(i), "icon": None}), id=int(i)) for i in ids if i]  # noqa: E731
            r = current["runes"]
            current["view"] = {"primaryStyle": (view(styles, [r["primaryStyle"]]) or [None])[0],
                               "subStyle": (view(styles, [r["subStyle"]]) or [None])[0],
                               "primary": view(perks, r["primary"]), "secondary": view(perks, r["secondary"]),
                               "shards": view(perks, r["shards"])}
        named = lambda cid: {"id": cid, "name": (index.get(cid) or {}).get("name") or f"#{cid}", "icon": (index.get(cid) or {}).get("icon")}  # noqa: E731
        ids = set(enemies) | {a.get("championId") for a in state.get("allies") or []} | {state.get("championId")}
        ids |= {p.get("championId") for p in (live or {}).get("players") or []}
        state["champions"] = {str(c): named(c) for c in ids if c}
        return state

    def counters(self, champion_id: int, position: str, rank: Optional[str] = None) -> dict:
        """The champions that beat this one in its lane, best first (op.gg's tier list)."""
        if not self.opgg:
            return {"available": False}
        try:
            found = self.opgg.counters(champion_id, position, rank)
        except Exception as e:
            log.warning("[Window] op.gg counters failed: %s", e)
            found = None
        if not found:
            return {"available": False}
        index = self._champion_index()
        entry = found["entry"]
        counters = [dict(d, name=(index.get(d["championId"]) or {}).get("name") or f"#{d['championId']}",
                         icon=(index.get(d["championId"]) or {}).get("icon")) for d in entry["counterDetails"]]
        counters.sort(key=lambda c: -(c.get("winRate") or 0))
        return {"available": True, "championId": int(champion_id), "position": found["position"], "lane": found["lane"],
                "tier": entry["tier"], "winRate": entry["winRate"], "counters": counters, "rank": found["rank"]}

    _auto_status: Optional[dict] = None
    _auto_key = None
    _auto_failed_at = 0.0

    def auto_runes_tick(self) -> None:
        """Called every few seconds: once your champion is locked in, its build's
        runes and spells go in (Beállítások: automatikus rúnák)."""
        if not self.champ_select or not self._setting("autoRunes", True):
            return
        try:
            pick = self.champ_select.locked()
        except Exception:
            pick = None
        if not pick:
            self._auto_key, self._auto_status = None, None
            return
        if not pick.get("locked"):
            return
        position, opponent = self._guess_opponent(pick["championId"], pick.get("position"), pick.get("enemies") or [])
        key = (pick["championId"], position, opponent)
        if key == self._auto_key:
            return
        if self._auto_status and not self._auto_status.get("ok") and time.monotonic() - self._auto_failed_at < 10:
            return  # a failed try is tried again a little later
        self._auto_key = key
        rank = self._setting("buildRank", None)
        try:
            lanes, _, _ = self._lane_builds(pick["championId"], opponent, rank)
            lane = next((l for l in lanes if l["key"] == position), lanes[0] if lanes else None)  # noqa: E741
            if not lane:
                raise ValueError("no build")
            self.apply_build({"championId": pick["championId"], "lane": lane["key"], "index": 0,
                              "opponent": opponent, "rank": rank})
            self._auto_status = {"ok": True, "championId": pick["championId"], "lane": lane["name"], "opponent": opponent,
                                 "source": lane["builds"][0].get("source")}
            log.info("[Window] Runes set for %s %s (vs %s)", pick["championId"], lane["key"], opponent)
        except Exception as e:
            self._auto_status = {"ok": False, "championId": pick["championId"], "error": str(e)}
            self._auto_key, self._auto_failed_at = None, time.monotonic()
            log.warning("[Window] Automatic runes failed: %s", e)

    def apply_build(self, body: dict) -> dict:
        if not self.champ_select:
            raise ValueError("nincs build")
        champion_id, lane, index = int(body["championId"]), str(body["lane"]), int(body.get("index") or 0)
        opponent_id = int(body["opponent"]) if body.get("opponent") else None
        lanes, _, _ = self._lane_builds(champion_id, opponent_id, body.get("rank") or None)
        lane_data = next((l for l in lanes if l["key"] == lane), None)  # noqa: E741
        if not lane_data or index >= len(lane_data["builds"]):
            raise ValueError("nincs ilyen build")
        build = lane_data["builds"][index]
        runes = build["runes"]
        pages = build.get("runePages") or []
        if body.get("page") is not None and 0 <= int(body["page"]) < len(pages):
            runes = pages[int(body["page"])]["runes"]
        name = (self._champion_index().get(champion_id) or {}).get("name") or str(champion_id)
        self.champ_select.apply_runes(f"{name} {lane_data['name']}", runes)
        if body.get("spells", True) and build.get("spells"):
            try:
                self.champ_select.apply_spells(build["spells"])
            except Exception as e:  # the runes are in all the same
                log.warning("[Window] Summoner spells not set: %s", e)
                return {"ok": True, "spells": False}
        return {"ok": True}

    def mod_list(self, champion_id: int) -> dict:
        if not self.mods:
            return {"mods": []}
        return {"mods": self.mods.champion_mods(champion_id)}

    def profile(self) -> dict:
        if not self.client.connected():
            return {"connected": False}
        return {
            "connected": True,
            "summoner": self.client.summoner(),
            "ranked": self.client.ranked(),
            "matches": self.client.matches(20),
        }

    def set_favorite(self, body: dict) -> dict:
        skins = self.favorites.set(int(body["skinId"]), bool(body.get("favorite")))
        return {"ok": True, "favorite": int(body["skinId"]) in skins}

    def set_next_skin(self, body: dict) -> dict:
        champion_id = int(body["championId"])
        skin_id = body.get("skinId")
        skin_id = int(skin_id) if skin_id is not None else None
        if skin_id is not None and skin_id // 1000 != champion_id:
            raise ValueError("the skin is not this champion's")
        self.next_skins.set(champion_id, skin_id)
        return {"ok": True, "nextSkinId": self.next_skins.for_champion(champion_id)}

    def open(self, body: dict) -> dict:
        which = str(body.get("folder") or "")
        if not self.open_folder or which not in ("mods", "logs"):
            raise ValueError("unknown folder")
        return {"ok": bool(self.open_folder(which))}

    def get_settings(self) -> dict:
        getter = self.settings.get("get")
        return getter() if getter else {}

    def put_settings(self, body: dict) -> dict:
        setter = self.settings.get("set")
        if not setter:
            raise ValueError("no settings")
        setter(body)
        return self.get_settings()


class _Handler(BaseHTTPRequestHandler):
    server_version = "Proteus"
    sys_version = ""

    # quiet: the default logs every request to stderr
    def log_message(self, fmt, *args):
        log.debug("[Window] " + fmt, *args)

    @property
    def app(self) -> "AppServer":
        return self.server.app  # type: ignore[attr-defined]

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[dict] = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.app.port
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _token_ok(self, query: dict) -> bool:
        token = self.headers.get("X-Proteus-Token") or (query.get("t") or [""])[0]
        return bool(token) and secrets.compare_digest(token, self.app.token)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        url = urlparse(self.path)
        query = parse_qs(url.query)
        path = url.path
        if path.startswith("/api/") or path == "/img":
            if not self._token_ok(query):
                return self._send(403, b"Forbidden", "text/plain")
            try:
                return self._get_api(path, query)
            except Exception as e:
                log.warning("[Window] %s failed: %s", path, e)
                return self._json(500, {"error": "internal"})
        return self._static(path)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        url = urlparse(self.path)
        if not url.path.startswith("/api/") or not self.headers.get("X-Proteus-Token") \
                or not self._token_ok({}):
            return self._send(403, b"Forbidden", "text/plain")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if url.path == "/api/mods/upload":
            return self._upload(parse_qs(url.query), length)
        if length < 0 or length > MAX_BODY:
            return self._json(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("not an object")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        api = self.app.api
        routes = {
            "/api/favorite": api.set_favorite,
            "/api/next-skin": api.set_next_skin,
            "/api/open-folder": api.open,
            "/api/settings": api.put_settings,
            "/api/apply-build": api.apply_build,
        }
        handler = routes.get(url.path)
        if handler is None:
            return self._json(404, {"error": "not found"})
        try:
            return self._json(200, handler(body))
        except (KeyError, TypeError, ValueError) as e:
            return self._json(400, {"error": str(e)})
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        except Exception as e:
            log.warning("[Window] %s failed: %s", url.path, e)
            return self._json(500, {"error": "internal"})

    def _upload(self, query: dict, length: int):
        """A dropped mod file: streamed to a temporary file, imported, removed."""
        from .mods import safe_upload_name

        api = self.app.api
        if not api.mods or not api.upload_dir:
            return self._json(404, {"error": "not found"})
        if length <= 0 or length > MAX_UPLOAD:
            return self._json(413, {"error": "A fájl túl nagy vagy üres"})
        first = lambda key: (query.get(key) or [""])[0]  # noqa: E731
        try:
            name = safe_upload_name(first("name"))
            kind = first("kind") or "skin"
            champion_id = int(first("champion") or 0) or None
            skin_ids = [int(s) for s in first("skins").split(",") if s.strip()]
        except ValueError as e:
            self._drain(length)
            return self._json(400, {"error": str(e)})
        api.upload_dir.mkdir(parents=True, exist_ok=True)
        target = api.upload_dir / (secrets.token_hex(8) + "_" + name)
        try:
            remaining = length
            with open(target, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK, remaining))
                    if not chunk:
                        raise ValueError("A feltöltés megszakadt")
                    f.write(chunk)
                    remaining -= len(chunk)
            # the import names the mod after the file: hand it the original name
            named = target.with_name(name)
            if named.exists():
                named = target
            else:
                target.replace(named)
                target = named
            result = api.mods.import_file(named, kind, champion_id, skin_ids)
            return self._json(200, result)
        except (ValueError, FileNotFoundError) as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            log.warning("[Window] Mod import failed: %s", e)
            return self._json(500, {"error": "Nem sikerült importálni: " + str(e)[:200]})
        finally:
            try:
                target.unlink()
            except OSError:
                pass

    def _drain(self, length: int) -> None:
        while length > 0:
            chunk = self.rfile.read(min(UPLOAD_CHUNK, length))
            if not chunk:
                break
            length -= len(chunk)

    def _get_api(self, path: str, query: dict):
        api = self.app.api
        if path == "/img":
            asset = (query.get("p") or [""])[0]
            image = api.game.image(asset)
            if image is None:
                return self._send(404, b"", "text/plain")
            return self._send(200, image[0], image[1], {"Cache-Control": "private, max-age=86400"})
        if path == "/api/status":
            return self._json(200, api.status())
        if path == "/api/champions":
            return self._json(200, api.champions())
        if path.startswith("/api/champions/"):
            try:
                champion_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._json(400, {"error": "bad id"})
            champ = api.champion(champion_id)
            return self._json(200, champ) if champ else self._json(404, {"error": "not found"})
        if path == "/api/favorites":
            return self._json(200, api.favorite_skins())
        if path == "/api/profile":
            return self._json(200, api.profile())
        if path == "/api/mods":
            try:
                champion_id = int((query.get("champion") or ["0"])[0])
            except ValueError:
                return self._json(400, {"error": "bad id"})
            return self._json(200, api.mod_list(champion_id))
        if path == "/api/tierlist":
            return self._json(200, api.tier_list((query.get("rank") or [None])[0]))
        if path.startswith("/api/builds/"):
            try:
                champion_id = int(path.rsplit("/", 1)[1])
                opponent = int((query.get("vs") or ["0"])[0]) or None
            except ValueError:
                return self._json(400, {"error": "bad id"})
            return self._json(200, api.builds(champion_id, opponent, (query.get("rank") or [None])[0]))
        if path == "/api/game":
            return self._json(200, api.game_state())
        if path.startswith("/api/counters/"):
            try:
                champion_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._json(400, {"error": "bad id"})
            first = lambda key: (query.get(key) or [""])[0] or None  # noqa: E731
            return self._json(200, api.counters(champion_id, first("pos") or "", first("rank")))
        if path == "/api/champ-select":
            return self._json(200, api.champ_select_state())
        if path == "/api/patch-notes":
            return self._json(200, api.latest_patch_notes())
        if path == "/api/settings":
            return self._json(200, api.get_settings())
        return self._json(404, {"error": "not found"})

    def _static(self, path: str):
        root = self.app.web_root.resolve()
        name = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (root / name).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._send(404, b"Not found", "text/plain")
        if not target.is_file():
            return self._send(404, b"Not found", "text/plain")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript",):
            content_type += "; charset=utf-8"
        extra = {"Cache-Control": "no-cache"}
        if target.name == "index.html":
            extra["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            )
        return self._send(200, target.read_bytes(), content_type, extra)


class AppServer:
    """Runs the window's server on a free port of 127.0.0.1."""

    def __init__(self, api: AppAPI, web_root: Optional[Path] = None, port: int = 0):
        self.api = api
        self.web_root = web_root or web_dir()
        self.token = secrets.token_urlsafe(24)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.app = self  # type: ignore[attr-defined]
        self.port = self._httpd.server_address[1]
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="ProteusWindowServer", daemon=True)
        self._thread.start()
        log.info("[Window] Serving the Proteus window on 127.0.0.1:%s", self.port)

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception as e:
            log.debug("[Window] Stop failed: %s", e)
