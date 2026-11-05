#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The rank shown on your profile and lobby banner in the client, in place of
your real one (a cosmetic, like a skin).

Only Proteus users see it: the PROTEUS-Profile plugin swaps it in in your own
client, and party mode shares it with the friends in your party, whose
plugins show it for you. Nothing is sent to Riot: players without Proteus
see your real rank.

The window sets your own rank (set_own); party mode reports your friends'
(set_peers); the plugin is sent overrides() whenever either changes.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]
APEX = {"MASTER", "GRANDMASTER", "CHALLENGER"}  # no divisions
DIVISIONS = ["IV", "III", "II", "I"]
OPTION_TIER = ("Profile", "rank_tier")
OPTION_DIVISION = ("Profile", "rank_division")

_lock = threading.Lock()
_listeners: List[Callable[[], None]] = []
_peers: Dict[int, dict] = {}


def clean(value) -> Optional[dict]:
    """A valid {tier, division}, or None (no override)."""
    if not isinstance(value, dict):
        return None
    tier = str(value.get("tier") or "").upper()
    if tier not in TIERS:
        return None
    division = str(value.get("division") or "").upper()
    if tier in APEX:
        division = "I"
    elif division not in DIVISIONS:
        division = "I"
    return {"tier": tier, "division": division}


def _config():
    from config import get_config_option, set_config_option

    return get_config_option, set_config_option


def own() -> Optional[dict]:
    try:
        get, _ = _config()
        return clean({"tier": get(*OPTION_TIER, ""), "division": get(*OPTION_DIVISION, "")})
    except Exception:
        return None


def set_own(value) -> Optional[dict]:
    """Save your own rank (None or an unknown tier: your real one is shown)."""
    rank = clean(value)
    _, put = _config()
    put(*OPTION_TIER, rank["tier"] if rank else "")
    put(*OPTION_DIVISION, rank["division"] if rank else "")
    _notify()
    return rank


def set_peers(peers: Dict[int, Optional[dict]]) -> None:
    """Your party friends' ranks by summoner id, as they shared them."""
    fresh = {int(sid): rank for sid, rank in ((s, clean(r)) for s, r in peers.items()) if rank}
    with _lock:
        if fresh == _peers:
            return
        _peers.clear()
        _peers.update(fresh)
    _notify()


def overrides() -> dict:
    """What the plugin shows: your rank ('self') and your friends' by summoner id."""
    with _lock:
        peers = [dict(rank, summonerId=sid) for sid, rank in _peers.items()]
    return {"self": own(), "peers": peers}


def on_change(callback: Callable[[], None]) -> None:
    with _lock:
        _listeners.append(callback)


def _notify() -> None:
    with _lock:
        listeners = list(_listeners)
    for callback in listeners:
        try:
            callback()
        except Exception:
            pass
