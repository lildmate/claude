import http.client
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from desktop.data import ClientData, GameData
from desktop.mods import Mods, safe_upload_name
from desktop.server import AppAPI, AppServer
from desktop.store import Favorites, NextSkins


class FakeStorage:
    def __init__(self):
        self.imported = []

    def import_mod_file(self, champion_id, path, skin_ids):
        self.imported.append(("skin", champion_id, Path(path).name, Path(path).read_bytes(), list(skin_ids)))
        return Path("x"), Path("y"), Path(path).stem

    def import_category_mod_file(self, category, path):
        self.imported.append((category, None, Path(path).name, Path(path).read_bytes(), []))
        return Path("x"), Path(path).stem

    def list_mods_for_champion(self, champion_id):
        return [SimpleNamespace(display_name=None, mod_name="Neon Ahri", target_skin_ids=(103015,), skin_id=103000)]


class ModsTests(unittest.TestCase):
    def test_upload_names(self):
        self.assertEqual(safe_upload_name("C:\\\\Users\\\\me\\\\Neon Ahri.fantome"), "Neon Ahri.fantome")
        self.assertEqual(safe_upload_name("../../evil<>.ZIP"), "evil__.zip")
        with self.assertRaises(ValueError):
            safe_upload_name("virus.exe")

    def test_a_skin_mod_needs_its_champion_and_skins(self):
        mods = Mods(FakeStorage)
        with self.assertRaises(ValueError):
            mods.import_file(Path("a.zip"), "skin", 103, [])
        with self.assertRaises(ValueError):
            mods.import_file(Path("a.zip"), "skin", 103, [157001])
        with self.assertRaises(ValueError):
            mods.import_file(Path("a.zip"), "trojan")


class UploadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = FakeStorage()
        game = GameData(None)
        api = AppAPI(game, ClientData(None, game), Favorites(Path(tmp.name) / "f.json"),
                     NextSkins(read_all=dict, write=lambda c, s: None, clear=lambda c: None),
                     mods=Mods(lambda: self.storage), upload_dir=Path(tmp.name) / "uploads")
        self.uploads = Path(tmp.name) / "uploads"
        self.server = AppServer(api, web_root=Path(tmp.name))
        self.server.start()
        self.addCleanup(self.server.stop)

    def post(self, query, body, token=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        headers = {"Host": f"127.0.0.1:{self.server.port}", "Content-Length": str(len(body))}
        if token:
            headers["X-Proteus-Token"] = self.server.token
        conn.request("POST", "/api/mods/upload?" + query, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {"text": raw.decode("utf-8", "replace")}
        conn.close()
        return response.status, data

    def test_a_skin_mod_is_imported_with_its_name_and_the_temporary_file_removed(self):
        body = b"PK" + b"x" * (3 * 1024 * 1024)  # several chunks
        status, data = self.post("name=Neon%20Ahri.fantome&kind=skin&champion=103&skins=103015,103016", body)
        self.assertEqual(status, 200, data)
        kind, champ, name, content, skins = self.storage.imported[0]
        self.assertEqual((kind, champ, name, skins), ("skin", 103, "Neon Ahri.fantome", [103015, 103016]))
        self.assertEqual(content, body)
        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_category_mod(self):
        status, _ = self.post("name=map.zip&kind=maps", b"PK..")
        self.assertEqual(status, 200)
        self.assertEqual(self.storage.imported[0][0], "maps")

    def test_refusals(self):
        self.assertEqual(self.post("name=a.exe&kind=maps", b"MZ")[0], 400)
        self.assertEqual(self.post("name=a.zip&kind=skin&champion=103&skins=1001", b"PK")[0], 400)
        self.assertEqual(self.post("name=a.zip&kind=maps", b"PK", token=False)[0], 403)
        self.assertEqual(self.storage.imported, [])

    def test_the_champions_mods_are_listed(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        conn.request("GET", "/api/mods?champion=103", headers={"Host": f"127.0.0.1:{self.server.port}", "X-Proteus-Token": self.server.token})
        data = json.loads(conn.getresponse().read())
        self.assertEqual(data, {"mods": [{"name": "Neon Ahri", "skinIds": [103015]}]})


if __name__ == "__main__":
    unittest.main()
