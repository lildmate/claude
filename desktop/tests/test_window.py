import http.client
import json
import tempfile
import unittest
from pathlib import Path

from desktop.data import ClientData, GameData, cdragon_url, image_url
from desktop.server import AppAPI, AppServer
from desktop.store import Favorites, NextSkins
from desktop.window import edge_arguments


class FakeResponse:
    def __init__(self, status_code=200, data=None, content=b""):
        self.status_code = status_code
        self._data = data
        self.content = content

    def json(self):
        return self._data


CHAMPION = {
    "id": 103, "name": "Ahri", "title": "the Nine-Tailed Fox",
    "squarePortraitPath": "/lol-game-data/assets/v1/champion-icons/103.png",
    "skins": [
        {"id": 103000, "isBase": True, "name": "Ahri", "tilePath": "/lol-game-data/assets/ASSETS/Characters/Ahri/Skins/Base/Images/ahri_splash_tile_0.jpg"},
        {"id": 103007, "name": "K/DA Ahri", "rarity": "kEpic", "chromas": [{}, {}],
         "tilePath": "/lol-game-data/assets/ASSETS/Characters/Ahri/Skins/Skin07/Images/ahri_splash_tile_7.jpg"},
        {"id": 103015, "name": "Spirit Blossom Ahri", "rarity": "kLegendary", "isLegacy": False},
    ],
}


class FakeLCU:
    ok = True
    base = "https://127.0.0.1:1"
    phase = "ChampSelect"

    def owned_skins(self):
        return [103007]

    def get(self, path, timeout=None):
        if path.endswith("champion-summary.json"):
            return [{"id": -1, "name": "None"}, {"id": 103, "name": "Ahri", "alias": "Ahri"},
                    {"id": 1, "name": "Annie", "alias": "Annie"}]
        if path.endswith("/champions/103.json"):
            return CHAMPION
        if path.startswith("/lol-ranked"):
            return {"queueMap": {"RANKED_SOLO_5x5": {"tier": "GOLD", "division": "II", "leaguePoints": 45, "wins": 3, "losses": 1},
                                 "RANKED_FLEX_SR": {"tier": "MASTER", "division": "I", "leaguePoints": 12, "wins": 0, "losses": 0}}}
        if path.startswith("/lol-match-history"):
            return {"games": {"games": [
                {"gameId": 1, "gameCreation": 1000, "gameDuration": 1500, "queueId": 420,
                 "participants": [{"championId": 103, "stats": {"win": True, "kills": 9, "deaths": 2, "assists": 11,
                                                                 "totalMinionsKilled": 150, "neutralMinionsKilled": 10}}]},
                {"gameId": 2, "gameCreation": 2000, "gameDuration": 900, "queueId": 450,
                 "participants": [{"championId": 1, "stats": {"win": False, "kills": 1, "deaths": 5, "assists": 3}}]},
            ]}}
        if path.startswith("/lol-summoner"):
            return {"gameName": "Morvai", "tagLine": "EUNE", "summonerLevel": 312, "profileIconId": 588}
        return None


class GameDataTests(unittest.TestCase):
    def test_cdragon_paths_are_lowercased_and_stay_in_game_data(self):
        self.assertEqual(
            cdragon_url("/lol-game-data/assets/ASSETS/Characters/Ahri/Skins/Base/Images/ahri_splash_tile_0.jpg"),
            "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/"
            "assets/characters/ahri/skins/base/images/ahri_splash_tile_0.jpg")
        self.assertIsNone(cdragon_url("/lol-game-data/assets/../../etc/passwd"))
        self.assertIsNone(cdragon_url("/lol-summoner/v1/current-summoner"))
        self.assertIsNone(image_url("https://example.com/x.png"))

    def test_skins_mark_owned_favorite_and_rarity(self):
        game = GameData(FakeLCU())
        champ = game.champion(103, owned={103007}, favorites={103015})
        by_id = {s["id"]: s for s in champ["skins"]}
        self.assertTrue(by_id[103000]["owned"])  # the base skin is everyone's
        self.assertTrue(by_id[103007]["owned"])
        self.assertFalse(by_id[103015]["owned"])
        self.assertTrue(by_id[103015]["favorite"])
        self.assertEqual(by_id[103007]["rarity"], "Epic")
        self.assertEqual(by_id[103007]["chromas"], 2)
        self.assertTrue(by_id[103007]["tile"].startswith("/img?p=/lol-game-data/assets/"))

    def test_without_the_client_game_data_comes_from_communitydragon(self):
        lcu = FakeLCU()
        lcu.ok = False
        asked = []

        def http_get(url, timeout=None):
            asked.append(url)
            return FakeResponse(200, [{"id": 103, "name": "Ahri"}])

        champions = GameData(lcu, http_get=http_get).champions()
        self.assertEqual([c["name"] for c in champions], ["Ahri"])
        self.assertTrue(asked[0].endswith("/global/default/v1/champion-summary.json"))

    def test_champions_are_sorted_and_the_none_entry_dropped(self):
        names = [c["name"] for c in GameData(FakeLCU()).champions()]
        self.assertEqual(names, ["Ahri", "Annie"])

    def test_images_are_cached_on_disk(self):
        lcu = FakeLCU()
        lcu.ok = False
        calls = []

        def http_get(url, timeout=None):
            calls.append(url)
            return FakeResponse(200, content=b"\x89PNG")

        with tempfile.TemporaryDirectory() as tmp:
            game = GameData(lcu, cache_dir=Path(tmp), http_get=http_get)
            path = "/lol-game-data/assets/v1/champion-icons/103.png"
            self.assertEqual(game.image(path), (b"\x89PNG", "image/png"))
            self.assertEqual(game.image(path), (b"\x89PNG", "image/png"))
            self.assertEqual(len(calls), 1)
            self.assertIsNone(game.image("/lol-game-data/assets/v1/x.exe"))


class ClientDataTests(unittest.TestCase):
    def setUp(self):
        lcu = FakeLCU()
        self.client = ClientData(lcu, GameData(lcu))

    def test_ranked(self):
        ranked = self.client.ranked()
        self.assertEqual(ranked["solo"], {"tier": "Gold", "division": "II", "lp": 45, "wins": 3, "losses": 1, "winrate": 75})
        self.assertEqual(ranked["flex"]["division"], "")  # apex tiers have none
        self.assertIsNone(ranked["flex"]["winrate"])

    def test_matches_newest_first_with_names(self):
        matches = self.client.matches()
        self.assertEqual([m["gameId"] for m in matches], [2, 1])
        self.assertEqual(matches[1]["championName"], "Ahri")
        self.assertEqual(matches[1]["cs"], 160)
        self.assertEqual(matches[1]["queue"], "Ranked Solo/Duo")
        self.assertEqual(matches[0]["queue"], "ARAM")

    def test_nothing_without_the_client(self):
        self.client.lcu.ok = False
        self.assertEqual(self.client.matches(), [])
        self.assertIsNone(self.client.summoner())


class ServerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.history = {}
        lcu = FakeLCU()
        game = GameData(lcu, cache_dir=Path(tmp.name) / "cache")
        self.settings = {"windowOnStart": True}
        api = AppAPI(
            game, ClientData(lcu, game), Favorites(Path(tmp.name) / "favorites.json"),
            NextSkins(read_all=lambda: dict(self.history),
                      write=lambda c, s: self.history.__setitem__(str(c), s),
                      clear=lambda c: self.history.pop(str(c), None)),
            version="9.9.9", open_folder=lambda which: True,
            settings={"get": lambda: dict(self.settings), "set": lambda b: self.settings.update(b)},
        )
        web = Path(tmp.name) / "web"
        web.mkdir()
        (web / "index.html").write_text("<!doctype html><title>Proteus</title>", encoding="utf-8")
        (Path(tmp.name) / "secret.txt").write_text("secret", encoding="utf-8")
        self.server = AppServer(api, web_root=web)
        self.server.start()
        self.addCleanup(self.server.stop)

    def request(self, method, path, body=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.server.port}"}
        if token:
            headers["X-Proteus-Token"] = self.server.token
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response, data

    def test_the_api_needs_the_token(self):
        response, _ = self.request("GET", "/api/status", token=False)
        self.assertEqual(response.status, 403)
        response, data = self.request("GET", "/api/status")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(data)["version"], "9.9.9")

    def test_images_take_the_token_in_the_query(self):
        response, _ = self.request("GET", "/img?p=/lol-game-data/assets/v1/champion-icons/103.png", token=False)
        self.assertEqual(response.status, 403)

    def test_other_host_names_are_refused(self):
        response, _ = self.request("GET", "/api/status", host=f"evil.example:{self.server.port}")
        self.assertEqual(response.status, 403)
        response, _ = self.request("GET", "/", host="evil.example")
        self.assertEqual(response.status, 403)

    def test_static_files_stay_in_the_page_folder(self):
        response, data = self.request("GET", "/", token=False)
        self.assertEqual(response.status, 200)
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        response, _ = self.request("GET", "/../secret.txt", token=False)
        self.assertEqual(response.status, 404)
        response, _ = self.request("GET", "/%2e%2e/secret.txt", token=False)
        self.assertEqual(response.status, 404)

    def test_next_skin_writes_the_history_and_the_base_skin_clears_it(self):
        response, data = self.request("POST", "/api/next-skin", {"championId": 103, "skinId": 103015})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.history, {"103": 103015})
        _, data = self.request("GET", "/api/champions/103")
        self.assertEqual(json.loads(data)["nextSkinId"], 103015)
        self.request("POST", "/api/next-skin", {"championId": 103, "skinId": None})
        self.assertEqual(self.history, {})

    def test_a_skin_of_another_champion_is_refused(self):
        response, _ = self.request("POST", "/api/next-skin", {"championId": 103, "skinId": 1001})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.history, {})

    def test_posts_need_the_token_header(self):
        response, _ = self.request("POST", f"/api/favorite?t={self.server.token}", {"skinId": 103007, "favorite": True}, token=False)
        self.assertEqual(response.status, 403)

    def test_favorites_are_saved(self):
        response, data = self.request("POST", "/api/favorite", {"skinId": 103007, "favorite": True})
        self.assertEqual(json.loads(data), {"ok": True, "favorite": True})
        _, data = self.request("GET", "/api/favorites")
        skins = json.loads(data)["skins"]
        self.assertEqual([(s["id"], s["championName"]) for s in skins], [(103007, "Ahri")])

    def test_settings(self):
        _, data = self.request("POST", "/api/settings", {"windowOnStart": False})
        self.assertEqual(json.loads(data), {"windowOnStart": False})

    def test_only_known_folders_open(self):
        response, _ = self.request("POST", "/api/open-folder", {"folder": "C:/Windows"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/api/open-folder", {"folder": "logs"})
        self.assertEqual(response.status, 200)


class WindowTests(unittest.TestCase):
    def test_edge_opens_the_page_as_an_app_with_its_own_profile(self):
        args = edge_arguments("http://127.0.0.1:5000/#t=abc", Path("C:/data/window-profile"))
        self.assertIn("--app=http://127.0.0.1:5000/#t=abc", args)
        self.assertTrue(any(a.startswith("--user-data-dir=") and "window-profile" in a for a in args))


if __name__ == "__main__":
    unittest.main()
