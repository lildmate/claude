import unittest

from desktop.patchnotes import PatchNotes, change_effect, latest_patch_link, parse_notes, percent_change, verdict

PAGE = (
    '<header class="header-primary"><h2 id="patch-champions">Bajnokok</h2></header>'
    '<div class="patch-change-block"><div><p><a class="reference-link" href="x"><img src="a.jpg"></a></p>'
    '<h3 class="change-title" id="patch-Ahri"><a href="x">Ahri</a></h3>'
    '<blockquote class="blockquote context"><p>Erősítjük Ahrit.</p></blockquote>'
    '<h4 class="change-detail-title ability-title"><img src="q.png">Q - Gömb</h4>'
    '<ul><li><strong>Sebzés</strong>: 40/65/90 ⇒ <strong>50/75/100</strong></li>'
    '<li><strong>Töltődési idő</strong>: 7 ⇒ <strong>6</strong> mp</li></ul></div></div>'
    '<header class="header-primary"><h2 id="patch-items">Tárgyak</h2></header>'
    '<div class="patch-change-block"><div><p><a class="reference-link" href="x"><img src="b.jpg"></a></p>'
    '<h3 class="change-title" id="patch-Dorans-Bow"><a href="x">Doran íja</a></h3>'
    '<blockquote class="blockquote context"><p>Kis mértékben gyengítjük a Doran íját.</p></blockquote>'
    '<ul><li><strong>Sebzés</strong>: 8 ⇒ <strong>7</strong></li></ul><hr class="divider">'
    '<h3 class="change-title" id="patch-Boots"><a href="x">Csizma</a></h3>'
    '<ul><li><strong>Ár</strong>: 300 ⇒ <strong>250</strong></li></ul></div></div>'
    '<header class="header-primary"><h2 id="patch-aram">ARAM</h2></header>'
    '<ul><li><strong>Sebzés</strong>: 1 ⇒ 2</li></ul>'
)


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class PatchNotesTests(unittest.TestCase):
    def test_champions_and_items_with_their_changes(self):
        notes = parse_notes(PAGE)
        self.assertEqual([e["name"] for e in notes["champions"]], ["Ahri"])
        self.assertEqual([e["name"] for e in notes["items"]], ["Doran íja", "Csizma"])
        ahri = notes["champions"][0]
        self.assertEqual(ahri["context"], "Erősítjük Ahrit.")
        self.assertEqual(ahri["changes"][0]["detail"], "Q - Gömb")
        self.assertEqual((ahri["changes"][0]["old"], ahri["changes"][0]["new"]), ("40/65/90", "50/75/100"))
        self.assertEqual(ahri["verdict"], "buff")

    def test_other_sections_are_left_out(self):
        notes = parse_notes(PAGE)
        self.assertNotIn("ARAM", str(notes))

    def test_item_verdicts(self):
        bow, boots = parse_notes(PAGE)["items"]
        self.assertEqual(bow["verdict"], "nerf")
        self.assertEqual(bow["changes"][0]["percent"], -12)
        self.assertEqual(boots["changes"][0]["effect"], "better")  # cheaper is better
        self.assertEqual(boots["verdict"], "buff")

    def test_effects(self):
        self.assertEqual(change_effect("Damage", "40/65/90", "50/75/100"), "better")
        self.assertEqual(change_effect("Cooldown", "12", "14"), "worse")
        self.assertEqual(change_effect("Mana Cost", "60", "50"), "better")
        self.assertEqual(change_effect("Passive", "Old text", "New text"), "other")
        self.assertEqual(change_effect("Ratio", "1/2", "1/2/3"), "other")
        self.assertIsNone(percent_change("1/2", "2/3"))
        self.assertEqual(percent_change("30", "40"), 33)

    def test_the_explanation_decides_a_tie(self):
        entry = {"context": "We're nerfing it", "changes": [{"effect": "better"}, {"effect": "worse"}]}
        self.assertEqual(verdict(entry), "nerf")
        entry["context"] = ""
        self.assertEqual(verdict(entry), "adjust")

    def test_the_newest_patch_is_picked_by_number(self):
        html = ("/hu-hu/news/game-updates/league-of-legends-patch-26-9-notes "
                "/hu-hu/news/game-updates/league-of-legends-patch-26-22-notes/ "
                "/hu-hu/news/game-updates/league-of-legends-patch-26-21-notes")
        url, patch = latest_patch_link(html)
        self.assertEqual(patch, "26.22")
        self.assertTrue(url.endswith("/hu-hu/news/game-updates/league-of-legends-patch-26-22-notes/"))

    def test_fetch_falls_back_to_english_and_caches(self):
        calls = []

        def get(url):
            calls.append(url)
            if "/hu-hu/" in url:
                return FakeResponse("", 500)
            if url.endswith("/tags/patch-notes/"):
                return FakeResponse("/en-us/news/game-updates/league-of-legends-patch-26-22-notes/")
            return FakeResponse(PAGE)

        notes = PatchNotes(http_get=get)
        result = notes.latest()
        self.assertEqual((result["patch"], result["locale"]), ("26.22", "en-us"))
        count = len(calls)
        notes.latest()
        self.assertEqual(len(calls), count)


if __name__ == "__main__":
    unittest.main()
