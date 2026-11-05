#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Proteus window: skin library, profile and match history, settings.

start(lcu) runs the window's local server; Window.open() opens the window
(also from the tray). See server.py for the page's API and window.py for how
the window is opened.
"""

from __future__ import annotations

from typing import Optional

from utils.core.logging import get_logger

log = get_logger()

WINDOW_ON_START_OPTION = ("General", "window_on_start")


class Window:
    def __init__(self, server, data_dir, icon=None):
        self.server = server
        self.data_dir = data_dir
        self.icon = icon

    def open(self) -> bool:
        from .window import open_window

        return open_window(self.server.url, self.data_dir, self.icon)

    def stop(self) -> None:
        self.server.stop()


def _open_folder(which: str) -> bool:
    from utils.core.paths import get_user_data_dir, open_folder_in_explorer

    folder = get_user_data_dir() / which
    folder.mkdir(parents=True, exist_ok=True)
    open_folder_in_explorer(folder)
    return True


def _settings():
    from config import get_config_option, set_config_option

    def get():
        value = (get_config_option(*WINDOW_ON_START_OPTION, "true") or "true").strip().lower()
        return {"windowOnStart": value not in ("0", "false", "no", "off")}

    def put(body: dict):
        if "windowOnStart" in body:
            set_config_option(*WINDOW_ON_START_OPTION, "true" if body["windowOnStart"] else "false")

    return {"get": get, "set": put}


def open_on_start() -> bool:
    return _settings()["get"]()["windowOnStart"]


def start(lcu, version: str) -> Optional[Window]:
    """Start the window's server. None when it cannot run (the rest of Proteus goes on)."""
    try:
        from utils.core.paths import get_asset_path, get_user_data_dir

        from .data import ClientData, GameData
        from .meta import ChampSelect, DeepLol
        from .opgg import OpGG
        from .mods import Mods
        from .patchnotes import PatchNotes
        from .server import AppAPI, AppServer
        from .store import Favorites, NextSkins

        data_dir = get_user_data_dir()
        game = GameData(lcu, cache_dir=data_dir / "window-cache")
        api = AppAPI(
            game=game,
            client=ClientData(lcu, game),
            favorites=Favorites(data_dir / "favorites.json"),
            next_skins=NextSkins(),
            version=version,
            open_folder=_open_folder,
            settings=_settings(),
            patch_notes=PatchNotes(),
            mods=Mods(),
            upload_dir=data_dir / "window-uploads",
            meta=DeepLol(),
            champ_select=ChampSelect(lcu),
            opgg=OpGG(),
        )
        server = AppServer(api)
        server.start()
        icon = None
        try:
            icon_path = get_asset_path("icon.ico")
            icon = icon_path if icon_path and icon_path.is_file() else None
        except Exception:
            pass
        return Window(server, data_dir, icon)
    except Exception as e:
        log.error("[Window] The Proteus window could not start: %s", e)
        return None
