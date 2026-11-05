import unittest

from desktop.server import AppAPI

RUNES = {"primaryStyle": 8000, "primary": [8010, 9111, 9104, 8299], "subStyle": 8200, "secondary": [8224, 8234],
         "shards": [5005, 5008, 5001]}


class Game:
    def champions(self):
        return [{"id": 122, "name": "Darius", "icon": None}, {"id": 86, "name": "Garen", "icon": None},
                {"id": 64, "name": "Lee Sin", "icon": None}]


class OpGG:
    def __init__(self):
        self.asked = []

    def champion_positions(self):
        return {122: ["Top"], 86: ["Top"], 64: ["Jungle"]}

    def build(self, champion_id, position, opponent_id=None, rank=None):
        self.asked.append((champion_id, position, opponent_id, rank))
        return {"runes": RUNES, "runePages": [{"runes": RUNES, "games": 9}], "items": [], "startItems": [], "spells": [],
                "skills": [], "skillOrder": [], "games": 31, "version": "16.22", "rank": "Grandmaster+"}

    def counters(self, champion_id, position, rank=None):
        return {"entry": {"championId": 86, "tier": "S", "winRate": 51.0, "counters": [122, 64],
                          "counterDetails": [{"championId": 64, "winRate": 50.5}, {"championId": 122, "winRate": 54.2}]},
                "position": "Top", "lane": "Top", "rank": "Master+"}


class ChampSelect:
    def __init__(self):
        self.pick = {"championId": 122, "locked": False, "position": "Top", "enemies": [64, 86]}
        self.applied = []

    def locked(self):
        return dict(self.pick) if self.pick else None

    def apply_runes(self, name, runes):
        self.applied.append((name, runes))

    def apply_spells(self, spells):
        pass


class GameTests(unittest.TestCase):
    def setUp(self):
        self.cs, self.opgg = ChampSelect(), OpGG()
        self.settings = {"autoRunes": True, "buildRank": "challenger"}
        self.api = AppAPI(Game(), None, None, None, settings={"get": lambda: dict(self.settings), "set": None},
                          champ_select=self.cs, opgg=self.opgg)

    def test_runes_go_in_once_the_champion_is_locked(self):
        self.api.auto_runes_tick()
        self.assertEqual(self.cs.applied, [])  # only hovered
        self.cs.pick["locked"] = True
        self.api.auto_runes_tick()
        self.api.auto_runes_tick()
        self.assertEqual(len(self.cs.applied), 1)
        self.assertEqual(self.cs.applied[0][0], "Darius Top")
        self.assertIn((122, "Top", 86, "challenger"), self.opgg.asked)  # against the lane opponent
        self.assertTrue(self.api._auto_status["ok"])

    def test_off_in_the_settings(self):
        self.settings["autoRunes"] = False
        self.cs.pick["locked"] = True
        self.api.auto_runes_tick()
        self.assertEqual(self.cs.applied, [])

    def test_next_champion_select_applies_again(self):
        self.cs.pick["locked"] = True
        self.api.auto_runes_tick()
        self.cs.pick = None
        self.api.auto_runes_tick()
        self.cs.pick = {"championId": 122, "locked": True, "position": "Top", "enemies": [64, 86]}
        self.api.auto_runes_tick()
        self.assertEqual(len(self.cs.applied), 2)

    def test_counters(self):
        c = self.api.counters(86, "Top")
        self.assertEqual([x["name"] for x in c["counters"]], ["Darius", "Lee Sin"])  # the strongest first
        self.assertEqual(c["rank"], "Master+")


if __name__ == "__main__":
    unittest.main()


LIVE = {
    "activePlayer": {"riotId": "Me#EUNE"},
    "gameData": {"gameTime": 754.3},
    "allPlayers": [
        {"riotId": "Me#EUNE", "championName": "Darius", "rawChampionName": "game_character_displayname_Darius",
         "team": "ORDER", "position": "TOP", "level": 9, "scores": {"kills": 3, "deaths": 1, "assists": 2, "creepScore": 88},
         "items": [{"itemID": 3071}, {"itemID": 1055}]},
        {"riotId": "Them#EUW", "championName": "Garen", "rawChampionName": "game_character_displayname_Garen",
         "team": "CHAOS", "position": "TOP", "level": 8, "scores": {"kills": 1, "deaths": 3}, "items": []},
        {"riotId": "Jungler#EUW", "championName": "Lee Sin", "rawChampionName": "game_character_displayname_LeeSin",
         "team": "CHAOS", "position": "JUNGLE", "level": 8, "scores": {}, "items": []},
    ],
}


class LiveGameTests(unittest.TestCase):
    def test_parse(self):
        from desktop.meta import parse_live_game

        live = parse_live_game(LIVE)
        self.assertEqual(live["gameTime"], 754)
        me = live["players"][0]
        self.assertEqual((me["alias"], me["position"], me["me"], me["kills"], me["cs"], me["items"]),
                         ("Darius", "Top", True, 3, 88, [3071, 1055]))
        self.assertFalse(live["players"][1]["me"])

    def test_in_game_the_lane_opponent_comes_from_the_game(self):
        from desktop.meta import parse_live_game

        class InGame:
            def game_state(self):
                return {"phase": "InProgress", "live": parse_live_game(LIVE), "currentRunes": None}

        class GameWithAliases(Game):
            def champions(self):
                return [{"id": 122, "name": "Darius", "alias": "Darius", "icon": None},
                        {"id": 86, "name": "Garen", "alias": "Garen", "icon": None},
                        {"id": 64, "name": "Lee Sin", "alias": "LeeSin", "icon": None}]

            def lookup(self, kind):
                return {}

        api = AppAPI(GameWithAliases(), None, None, None, champ_select=InGame(), opgg=OpGG())
        state = api.game_state()
        self.assertEqual((state["championId"], state["position"], state["opponentGuess"]), (122, "Top", 86))
        self.assertEqual(sorted(state["enemies"]), [64, 86])
