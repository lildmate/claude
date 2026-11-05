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
from desktop.opgg import OpGG  # noqa: E402
from desktop.patchnotes import PatchNotes  # noqa: E402
from desktop.server import AppAPI, AppServer  # noqa: E402
from desktop.store import Favorites, NextSkins  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
history = {"103": 103015}
settings = {"windowOnStart": True, "rankDisplay": {"tier": "CHALLENGER", "division": "I"}}
game = GameData(None, cache_dir=tmp / "cache")
favorites = Favorites(tmp / "fav.json")
for skin in (103015, 157009, 99007, 222020):
    favorites.set(skin, True)
api = AppAPI(game, ClientData(None, game), favorites,
             NextSkins(read_all=lambda: dict(history), write=lambda c, s: history.__setitem__(str(c), s),
                       clear=lambda c: history.pop(str(c), None)),
             version="1.13.0", open_folder=lambda w: True,
             settings={"get": lambda: dict(settings), "set": settings.update},
             patch_notes=PatchNotes(), meta=DeepLol(), opgg=OpGG())


class FakeChampSelect:
    """Champion select as the client would report it: Darius top, Garen among the enemies."""
    def locked(self):
        return {"championId": 122, "locked": True, "position": "Top", "enemies": [86, 64, 103, 222, 412]}

    def game_state(self):
        return {"phase": "ChampSelect", "championId": 122, "locked": True, "position": "Top",
                "allies": [{"championId": 122, "position": "Top", "me": True}], "enemies": [86, 64, 103, 222, 412]}


api.champ_select = FakeChampSelect()
api._auto_status = {"ok": True, "championId": 122, "lane": "Top", "opponent": 86, "source": "op.gg KR Challenger · ellenfél ellen"}
print("counters", api.counters(86, "Top").get("counters", [])[:3])


def probe_counters():
    """What op.gg says about counters (printed in the CI log, to read their format)."""
    import json as _json
    from desktop.opgg import _objects_with
    o = api.opgg
    for rank in ("challenger", "emerald_plus"):
        data = o._flight(f"/lol/champions?position=top&region=kr&tier={rank}")
        for obj in _objects_with(data, '{"key":"garen"', '"positionName"'):
            print("PROBE tier", rank, _json.dumps(obj.get("positionCounters"))[:600])
            break
    data = o._flight("/lol/champions/garen/counters/top?region=kr&tier=emerald_plus")
    for word in ("win_rate", "winRate", "counter", "play"):
        i = data.find(word)
        print("PROBE counters page", word, repr(data[max(0, i - 300): i + 500]) if i >= 0 else "-")


try:
    probe_counters()
except Exception as e:
    print("PROBE failed", e)

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
    page.wait_for_selector("table", timeout=60000)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(out / "5_tier_list.png"))
    page.goto(server.url.split("#")[0] + "#/build/103/Middle")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(out / "6_build.png"), full_page=True)
    page.goto(server.url.split("#")[0] + "#/build/122/Top/86")
    page.wait_for_timeout(10000)
    page.screenshot(path=str(out / "7_darius_vs_garen.png"), full_page=True)
    page.goto(server.url.split("#")[0] + "#/game")
    page.wait_for_timeout(15000)
    page.screenshot(path=str(out / "9_game.png"), full_page=True)
    page.goto(server.url.split("#")[0] + "#/profile")
    page.wait_for_timeout(3000)
    page.screenshot(path=str(out / "8_profil_szerkesztese.png"))
    browser.close()
server.stop()
print("saved", sorted(x.name for x in out.iterdir()))
time.sleep(0.2)
