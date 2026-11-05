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

    def tier_list(self, rank=None):
        return {"rank": "Challenger", "positions": [{"key": "Top", "name": "Top", "champions": [
            {"championId": 86, "tier": "S", "winRate": 51.0, "counters": [122],
             "counterDetails": [{"championId": 122, "winRate": 54.2}]}]}]}


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
        self.assertEqual(c["counters"], [{"championId": 122, "winRate": 54.2, "name": "Darius", "icon": None}])


if __name__ == "__main__":
    unittest.main()
