import unittest
from unittest import mock

from desktop import rank_display


class RankDisplayTests(unittest.TestCase):
    def setUp(self):
        self.config = {}
        patcher = mock.patch.object(rank_display, "_config", return_value=(
            lambda section, key, default="": self.config.get((section, key), default),
            lambda section, key, value: self.config.__setitem__((section, key), value)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(rank_display.set_peers, {})

    def test_clean(self):
        self.assertEqual(rank_display.clean({"tier": "challenger", "division": "IV"}), {"tier": "CHALLENGER", "division": "I"})
        self.assertEqual(rank_display.clean({"tier": "PLATINUM", "division": "III"}), {"tier": "PLATINUM", "division": "III"})
        self.assertIsNone(rank_display.clean({"tier": "WOOD"}))
        self.assertIsNone(rank_display.clean(None))

    def test_own_rank_is_saved_and_announced(self):
        calls = []
        rank_display.on_change(lambda: calls.append(1))
        rank_display.set_own({"tier": "CHALLENGER"})
        self.assertEqual(rank_display.own(), {"tier": "CHALLENGER", "division": "I"})
        rank_display.set_own(None)
        self.assertIsNone(rank_display.own())
        self.assertEqual(len(calls), 2)

    def test_peers(self):
        rank_display.set_peers({22: {"tier": "DIAMOND", "division": "II"}, 33: None, 44: {"tier": "?"}})
        self.assertEqual(rank_display.overrides()["peers"], [{"tier": "DIAMOND", "division": "II", "summonerId": 22}])


if __name__ == "__main__":
    unittest.main()
