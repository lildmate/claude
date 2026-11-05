import json
import unittest

from desktop.opgg import champion_keys, flight, parse_rows, parse_runes, parse_tier_list


def page(*chunks):
    """An op.gg-like page: the flight data split into self.__next_f pushes."""
    return "".join('<script>self.__next_f.push([1,%s])</script>' % json.dumps(c) for c in chunks)


TIER = ('26:["$","$L29",null,{"type":"ranked","data":[{"key":"darius","id":122,"name":"Darius","positions":["TOP","JUNGLE"]},'
        '{"key":"garen","id":86,"name":"Garen","positions":["TOP"]}]}]\n'
        '30:{"rows":[{"key":"darius","name":"Darius","positionName":"TOP","positionWinRate":51.4516,"positionPickRate":7.16851,'
        '"positionBanRate":13.6362,"positionTierData":{"tier":1,"rank":2,"rank_prev":3},"positionCounters":[{"champion_id":34}]},'
        '{"key":"garen","name":"Garen","positionName":"TOP","positionWinRate":50.2,"positionPickRate":5.0,"positionBanRate":2.0,'
        '"positionTierData":{"tier":2,"rank":9,"rank_prev":9},"positionCounters":[]}]}')

RUNES = ('7c:["$","$L7c",null,{"data":{"rune_pages":[{"id":8010,"play":229,"pick_rate":0.428,"builds":[{"id":8010,'
         '"primary_perk_style":{"id":8000},"perk_sub_style":{"id":8200},'
         '"main_runes":[[{"id":8005,"isActive":false},{"id":8010,"isActive":true}],[{"id":9111,"isActive":true}],'
         '[{"id":9104,"isActive":true}],[{"id":8299,"isActive":true}]],'
         '"sub_runes":[[{"id":8224,"isActive":true}],[{"id":8234,"isActive":true}]],'
         '"shards":[[{"id":5005,"isActive":true}],[{"id":5008,"isActive":true}],[{"id":5001,"isActive":true}]]}]}]}}]')

ROWS = ('80:["$","tr","core_items_0",{"children":[{"metaType":"item","metaId":3142},{"metaType":"item","metaId":3742},'
        '{"children":["61"," ","Games"]},{"children":"63.93%"}]}]\n'
        '81:["$","tr","starter_items_0",{"children":[{"metaType":"item","metaId":1055},{"metaType":"item","metaId":2003},'
        '{"children":["1,422"," ","Games"]},{"children":"57.82%"}]}]')


class OpGGTests(unittest.TestCase):
    def test_flight_joins_the_pushes(self):
        self.assertEqual(flight(page("a\n", "b")), "a\nb")

    def test_tier_list(self):
        data = flight(page(TIER))
        keys = champion_keys(data)
        self.assertEqual(keys, {"darius": 122, "garen": 86})
        rows = parse_tier_list(data, keys)
        self.assertEqual([r["championId"] for r in rows], [122, 86])
        self.assertEqual(rows[0]["tier"], "S")
        self.assertEqual(rows[0]["rankDelta"], 1)
        self.assertEqual(rows[0]["winRate"], 51.5)
        self.assertEqual(rows[0]["counters"], [34])

    def test_runes_are_the_active_ones(self):
        runes = parse_runes(flight(page(RUNES)))
        self.assertEqual(runes[0]["games"], 229)
        self.assertEqual(runes[0]["runes"], {"primaryStyle": 8000, "primary": [8010, 9111, 9104, 8299], "subStyle": 8200,
                                             "secondary": [8224, 8234], "shards": [5005, 5008, 5001]})

    def test_rows(self):
        rows = parse_rows(flight(page(ROWS)))
        self.assertEqual(rows["core_items"][0], {"ids": [3142, 3742], "skills": [], "games": 61, "winRate": 63.93})
        self.assertEqual(rows["starter_items"][0]["games"], 1422)


if __name__ == "__main__":
    unittest.main()
