#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Custom skins and other mods dropped on the Proteus window.

They go through the same import as champion select's Mods menu
(injection.mods.storage): a skin mod into its champion's folder, tied to the
skins it replaces, any other mod into its category. Champion select's Mods
button then lists them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from utils.core.logging import get_logger

log = get_logger()

SUFFIXES = (".fantome", ".zip", ".modpkg")
CATEGORIES = {
    "maps": "Pálya",
    "fonts": "Betűtípus",
    "announcers": "Bemondó",
    "ui": "Felület",
    "voiceover": "Hangok",
    "loading_screen": "Betöltőképernyő",
    "vfx": "Effektek",
    "sfx": "Hangeffektek",
    "others": "Egyéb",
}


def safe_upload_name(name: str) -> str:
    """The dropped file's name, without folders or odd characters, keeping its type."""
    name = Path(str(name or "").replace("\\", "/")).name.strip()
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    if suffix not in SUFFIXES:
        raise ValueError("Csak .fantome, .zip és .modpkg fájl tölthető fel")
    stem = re.sub(r"[^\w .()\[\]+-]", "_", stem, flags=re.UNICODE).strip(" .") or "mod"
    return stem[:120] + suffix


class Mods:
    def __init__(self, storage_factory: Optional[Callable[[], object]] = None):
        self._factory = storage_factory
        self._storage = None

    @property
    def storage(self):
        if self._storage is None:
            if self._factory is not None:
                self._storage = self._factory()
            else:
                from injection.mods.storage import ModStorageService

                self._storage = ModStorageService()
        return self._storage

    def import_file(self, path: Path, kind: str, champion_id: Optional[int] = None,
                    skin_ids: Iterable[int] = ()) -> dict:
        if kind == "skin":
            skin_ids = sorted({int(s) for s in skin_ids if int(s) > 0})
            if not champion_id or not skin_ids:
                raise ValueError("Válaszd ki a championt és a skint")
            if any(s // 1000 != int(champion_id) for s in skin_ids):
                raise ValueError("A skin nem ehhez a championhöz tartozik")
            folder, _manifest, name = self.storage.import_mod_file(int(champion_id), path, skin_ids)
            log.info("[Window] Imported skin mod %s for champion %s (skins %s)", name, champion_id, skin_ids)
            return {"ok": True, "name": name, "kind": kind}
        if kind not in CATEGORIES:
            raise ValueError("Ismeretlen modtípus")
        _folder, name = self.storage.import_category_mod_file(kind, path)
        log.info("[Window] Imported %s mod %s", kind, name)
        return {"ok": True, "name": name, "kind": kind}

    def champion_mods(self, champion_id: int) -> List[dict]:
        result = []
        for entry in self.storage.list_mods_for_champion(int(champion_id)):
            result.append({
                "name": entry.display_name or entry.mod_name,
                "skinIds": list(entry.target_skin_ids or (entry.skin_id,)),
            })
        return result
