#!/usr/bin/env python3
"""Screenshots of the Proteus window with live data (run on CI, which can reach
CommunityDragon and leagueoflegends.com). No League client there: the profile
stays empty, skins and patch notes are real."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.data import ClientData, GameData  # noqa: E402
from desktop.meta import DeepLol  # noqa: E402
from desktop.patchnotes import PatchNotes  # noqa: E402
from desktop.server import AppAPI, AppServer  # noqa: E402
from desktop.store import Favorites, NextSkins  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
history = {"103": 103015}
game = GameData(None, cache_dir=tmp / "cache")
favorites = Favorites(tmp / "fav.json")
for skin in (103015, 157009, 99007, 222020):
    favorites.set(skin, True)
api = AppAPI(game, ClientData(None, game), favorites,
             NextSkins(read_all=lambda: dict(history), write=lambda c, s: history.__setitem__(str(c), s),
                       clear=lambda c: history.pop(str(c), None)),
             version="1.9.1", open_folder=lambda w: True,
             settings={"get": lambda: {"windowOnStart": True}, "set": lambda b: None},
             patch_notes=PatchNotes(), meta=DeepLol())
server = AppServer(api)
server.start()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=2)
    page.goto(server.url)
    page.wait_for_timeout(4000)
    page.screenshot(path=str(out / "1_fooldal.png"))
    page.goto(server.url.split("#")[0] + "#/skins/103")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(out / "2_skinek.png"))
    page.goto(server.url.split("#")[0] + "#/patch")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(out / "3_patch_notes.png"))
    page.mouse.wheel(0, 900)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "4_patch_notes_reszletek.png"))
    page.goto(server.url.split("#")[0] + "#/tier")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(out / "5_tier_list.png"))
    page.goto(server.url.split("#")[0] + "#/build/103/Middle")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(out / "6_build.png"), full_page=True)
    browser.close()
server.stop()
print("saved", sorted(x.name for x in out.iterdir()))
time.sleep(0.2)
