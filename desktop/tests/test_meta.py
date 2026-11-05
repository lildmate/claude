import unittest

from desktop.meta import ChampSelect, DeepLol, parse_build

RANK = {"champion_data_list": [
    {"champion_id": 266, "performance_dict": {
        "Total": {"tier": 0, "win_rate": 0, "rank": 0},
        "Top": {"tier": 3, "win_rate": 0.496, "pick_rate": 0.037, "ban_rate": 0.016, "rank": 17, "rank_delta": 8},
        "Jungle": {"tier": 5, "win_rate": 0.493, "pick_rate": 0.005, "ban_rate": 0.002, "rank": 46}}},
    {"champion_id": 103, "performance_dict": {
        "Middle": {"tier": 1, "win_rate": 0.514, "pick_rate": 0.047, "ban_rate": 0.008, "rank": 5}}},
]}
BUILD = {"build_by_lane": {"Middle": {"build_lst": [{
    "rune": {"main_build": [8100, 8112, 8139, 8140, 8106], "sub_build": [8200, 8226, 8210], "stat_build": [5001, 5008, 5005]},
    "item": {"build": [3118, 3020, 4645]}, "spell": {"build": [14, 4]}, "start_item": {"build": [1056, 2003]},
    "skill": {"build": [1, 2, 3], "detail": [2, 1, 3, 1]}}, {"rune": {"main_build": [1]}}]}}}


LIVE = {"ready": False}
RANK_LIVE = {"champion_data_list": [
    {"champion_id": i, "performance_dict": {"Middle": {"tier": 2, "win_rate": 0.5, "rank": i}}} for i in range(1, 61)]}


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data, self.status_code = data, status_code

    def json(self):
        return self._data


def fake_get(url, params):
    if url.endswith("/champion/version"):
        return FakeResponse({"recent_version": "16.22", "game_version_list": ["16.21", "16.20"]})
    if url.endswith("/champion/rank"):
        if params["game_version"] == "16.22":
            # what deeplol.gg answers for a patch it has no data for yet
            return FakeResponse(RANK_LIVE) if LIVE["ready"] else FakeResponse({"msg": "Internal Server Error"}, 500)
        return FakeResponse(RANK)
    if url.endswith("/champion/build"):
        return FakeResponse(BUILD)
    return FakeResponse({}, 404)


class DeepLolTests(unittest.TestCase):
    def test_tier_list_per_position_sorted_by_rank(self):
        data = DeepLol(fake_get).tier_list()
        self.assertEqual(data["version"], "16.21")
        positions = {p["key"]: p["champions"] for p in data["positions"]}
        self.assertEqual([c["championId"] for c in positions["Top"]], [266])
        self.assertEqual(positions["Middle"][0], {"championId": 103, "tier": "S", "tierNumber": 1, "rank": 5,
                                                  "rankDelta": 0, "winRate": 51.4, "pickRate": 4.7, "banRate": 0.8})
        self.assertNotIn("Total", positions)
        self.assertEqual(data["currentVersion"], "16.22")

    def test_the_live_patch_once_it_has_enough_games(self):
        LIVE["ready"] = True
        try:
            data = DeepLol(fake_get).tier_list()
        finally:
            LIVE["ready"] = False
        self.assertEqual(data["version"], "16.22")

    def test_builds_skip_incomplete_ones(self):
        data = DeepLol(fake_get).builds(103)
        self.assertEqual([l["key"] for l in data["lanes"]], ["Middle"])  # noqa: E741
        build = data["lanes"][0]["builds"]
        self.assertEqual(len(build), 1)
        self.assertEqual(build[0]["runes"], {"primaryStyle": 8100, "primary": [8112, 8139, 8140, 8106],
                                             "subStyle": 8200, "secondary": [8226, 8210], "shards": [5001, 5008, 5005]})
        self.assertEqual(build[0]["spells"], [14, 4])

    def test_incomplete_build(self):
        self.assertIsNone(parse_build({"rune": {"main_build": [8100]}}))


class FakeSession:
    def __init__(self, pages, owned=2):
        self.pages, self.owned, self.calls = pages, owned, []

    def get(self, url, timeout=None):
        if url.endswith("/pages"):
            return FakeResponse(self.pages)
        return FakeResponse({"ownedPageCount": self.owned})

    def delete(self, url, timeout=None):
        self.calls.append(("delete", url.rsplit("/", 1)[1]))
        return FakeResponse({}, 204)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("post", json))
        return FakeResponse({}, 200)


class FakeLCU:
    ok = True
    base = "https://127.0.0.1:1"

    def __init__(self, session):
        self.s = session
        self.patched = []

    def patch(self, path, data, timeout=None):
        self.patched.append((path, data))


RUNES = {"primaryStyle": 8100, "primary": [8112, 8139, 8140, 8106], "subStyle": 8200, "secondary": [8226, 8210],
         "shards": [5001, 5008, 5005]}


class ChampSelectTests(unittest.TestCase):
    def test_the_previous_proteus_page_is_replaced(self):
        session = FakeSession([{"id": 7, "name": "Proteus: Lux Support", "isDeletable": True},
                               {"id": 8, "name": "My page", "isDeletable": True, "current": True}], owned=5)
        ChampSelect(FakeLCU(session)).apply_runes("Ahri Mid", RUNES)
        self.assertEqual(session.calls[0], ("delete", "7"))
        kind, body = session.calls[1]
        self.assertEqual(body["name"], "Proteus: Ahri Mid")
        self.assertEqual(body["selectedPerkIds"], [8112, 8139, 8140, 8106, 8226, 8210, 5001, 5008, 5005])
        self.assertTrue(body["current"])

    def test_when_all_pages_are_used_the_current_one_makes_room(self):
        session = FakeSession([{"id": 1, "name": "A", "isDeletable": True},
                               {"id": 2, "name": "B", "isDeletable": True, "current": True},
                               {"id": 99, "name": "Default", "isDeletable": False}], owned=2)
        ChampSelect(FakeLCU(session)).apply_runes("Ahri Mid", RUNES)
        self.assertEqual(session.calls[0], ("delete", "2"))

    def test_spells(self):
        lcu = FakeLCU(FakeSession([]))
        ChampSelect(lcu).apply_spells([14, 4])
        self.assertEqual(lcu.patched, [("/lol-champ-select/v1/session/my-selection", {"spell1Id": 14, "spell2Id": 4})])


if __name__ == "__main__":
    unittest.main()
