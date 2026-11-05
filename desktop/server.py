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
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from utils.core.logging import get_logger

from .data import ClientData, GameData
from .store import Favorites, NextSkins

log = get_logger()

MAX_BODY = 16 * 1024


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
                 settings: Optional[dict] = None):
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
        }
        handler = routes.get(url.path)
        if handler is None:
            return self._json(404, {"error": "not found"})
        try:
            return self._json(200, handler(body))
        except (KeyError, TypeError, ValueError) as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            log.warning("[Window] %s failed: %s", url.path, e)
            return self._json(500, {"error": "internal"})

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
