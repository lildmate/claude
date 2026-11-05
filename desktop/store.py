#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What the Proteus window remembers: favorite skins and the next game's skins.

The skin picked for a champion's next game goes into the same history file
champion select already reads (utils.core.historic): when that champion is
locked, Proteus puts the skin on, and hovering another skin still overrides it.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, Optional, Set

from utils.core.atomic_file import atomic_write
from utils.core.logging import get_logger

log = get_logger()


class Favorites:
    """Favorite skin ids, in favorites.json."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def all(self) -> Set[int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {int(s) for s in data.get("skins", []) if int(s) > 0}
        except FileNotFoundError:
            return set()
        except (OSError, ValueError, TypeError, AttributeError) as e:
            log.warning("[Window] Could not read favorites: %s", e)
            return set()

    def set(self, skin_id: int, favorite: bool) -> Set[int]:
        with self._lock:
            skins = self.all()
            if favorite:
                skins.add(int(skin_id))
            else:
                skins.discard(int(skin_id))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with atomic_write(self.path) as f:
                json.dump({"skins": sorted(skins)}, f)
            return skins


class NextSkins:
    """The skin each champion gets in its next game (the history file)."""

    def __init__(self, read_all: Optional[Callable[[], Dict[str, object]]] = None,
                 write: Optional[Callable[[int, int], None]] = None,
                 clear: Optional[Callable[[int], None]] = None):
        if read_all is None or write is None or clear is None:
            from utils.core.historic import clear_historic_entry, load_historic_map, write_historic_entry
            read_all = read_all or load_historic_map
            write = write or write_historic_entry
            clear = clear or clear_historic_entry
        self._read_all, self._write, self._clear = read_all, write, clear

    def for_champion(self, champion_id: int) -> Optional[int]:
        """The official skin set for the champion (a custom mod there counts as none)."""
        value = self._read_all().get(str(int(champion_id)))
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def set(self, champion_id: int, skin_id: Optional[int]) -> None:
        if skin_id is None or int(skin_id) == int(champion_id) * 1000:
            self._clear(int(champion_id))  # the base skin needs no entry
        else:
            self._write(int(champion_id), int(skin_id))
