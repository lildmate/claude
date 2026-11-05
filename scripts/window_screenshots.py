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
from desktop.meta import DeepLol, parse_live_game  # noqa: E402
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
             version="1.14.0", open_folder=lambda w: True,
             settings={"get": lambda: dict(settings), "set": settings.update},
             patch_notes=PatchNotes(), meta=DeepLol(), opgg=OpGG())


class FakeChampSelect:
    """Champion select as the client would report it: Darius top, Garen among the enemies."""
    def locked(self):
        return {"championId": 122, "locked": True, "position": "Top", "enemies": [86, 64, 103, 222, 412]}

    in_game = False
    runes = {"name": "Proteus: Darius Top", "runes": {"primaryStyle": 8000, "primary": [8010, 9111, 9104, 8299],
                                                      "subStyle": 8200, "secondary": [8224, 8234], "shards": [5005, 5008, 5001]}}

    def game_state(self):
        if self.in_game:
            return {"phase": "InProgress", "currentRunes": dict(self.runes), "live": parse_live_game(LIVE)}
        return {"phase": "ChampSelect", "championId": 122, "locked": True, "position": "Top", "currentRunes": dict(self.runes),
                "allies": [{"championId": 122, "position": "Top", "me": True}], "enemies": [86, 64, 103, 222, 412]}


def player(name, raw, team, position, level, k, d, a, cs, items, me=False):
    return {"riotId": name, "championName": raw, "rawChampionName": "game_character_displayname_" + raw, "team": team,
            "position": position, "level": level, "scores": {"kills": k, "deaths": d, "assists": a, "creepScore": cs},
            "items": [{"itemID": i} for i in items]}


LIVE = {"activePlayer": {"riotId": "Proteus#EUNE"}, "gameData": {"gameTime": 1084},
        "allPlayers": [
            player("Proteus#EUNE", "Darius", "ORDER", "TOP", 13, 5, 2, 3, 142, [6692, 3047, 1037, 2003]),
            player("Ally1#EUNE", "Vi", "ORDER", "JUNGLE", 11, 2, 3, 7, 98, [3071, 3111]),
            player("Ally2#EUNE", "Orianna", "ORDER", "MIDDLE", 12, 4, 1, 5, 160, [6655, 3020]),
            player("Ally3#EUNE", "Kaisa", "ORDER", "BOTTOM", 11, 3, 2, 4, 150, [3124, 3006]),
            player("Ally4#EUNE", "Nautilus", "ORDER", "UTILITY", 9, 0, 3, 10, 22, [3876, 3117]),
            player("Enemy1#EUW", "Garen", "CHAOS", "TOP", 11, 1, 4, 2, 120, [3078, 3047]),
            player("Enemy2#EUW", "LeeSin", "CHAOS", "JUNGLE", 11, 3, 3, 4, 90, [6692, 3111]),
            player("Enemy3#EUW", "Ahri", "CHAOS", "MIDDLE", 12, 4, 3, 2, 155, [6655, 3020]),
            player("Enemy4#EUW", "Jinx", "CHAOS", "BOTTOM", 10, 2, 4, 3, 140, [3031, 3006]),
            player("Enemy5#EUW", "Thresh", "CHAOS", "UTILITY", 9, 0, 2, 8, 20, [3876, 3117]),
        ]}


api.champ_select = FakeChampSelect()
api._auto_status = {"ok": True, "championId": 122, "lane": "Top", "opponent": 86, "source": "op.gg KR Challenger · ellenfél ellen"}
print("counters", api.counters(86, "Top").get("counters", [])[:3])


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
    api.champ_select.in_game = True
    page.goto(server.url.split("#")[0] + "#/home")
    page.wait_for_timeout(500)
    page.goto(server.url.split("#")[0] + "#/game")
    page.wait_for_timeout(10000)
    page.screenshot(path=str(out / "10_game_meccsben.png"), full_page=True)
    page.goto(server.url.split("#")[0] + "#/profile")
    page.wait_for_timeout(3000)
    page.screenshot(path=str(out / "8_profil_szerkesztese.png"))
    browser.close()
server.stop()
print("saved", sorted(x.name for x in out.iterdir()))
time.sleep(0.2)
