#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Saját beállítások (branding) – EZT A FÁJLT SZERKESZD.

Minden, ami azt határozza meg, hogy "kié" az app (honnan frissül, honnan
tölti le a skineket, milyen linkek jelennek meg, küld-e statisztikát),
itt van egy helyen.

A Python oldal közvetlenül innen olvas. A League kliensben futó JS pluginok
nem tudnak Pythont importálni, ezért módosítás után futtasd:

    python scripts/apply_branding.py

(a scripts/build_all.py ezt magától is lefuttatja buildelés előtt).
"""

# -----------------------------------------------------------------------------
# Frissítések
# -----------------------------------------------------------------------------
# Ebből a GitHub repóból keresi az app az új verziókat (Releases).
# Új verzió kiadása: lásd SAJAT_VERZIO.md.
UPDATE_REPO = "lildmate/claude"

# -----------------------------------------------------------------------------
# Skin könyvtár
# -----------------------------------------------------------------------------
# Innen szinkronizálja a skin fájlokat. Alapból az eredeti Rose skin repója,
# mert ennek a karbantartása (minden patch után) óriási munka. Ha saját
# forkot csinálsz belőle (ugyanazzal a "manifest" ággal), írd át ide.
SKINS_REPO = "Alban1911/LeagueSkins"

# -----------------------------------------------------------------------------
# Linkek a beállítások panelen és a hibaüzenetekben
# -----------------------------------------------------------------------------
# Üres string ("") = a link nem jelenik meg.
GITHUB_URL = f"https://github.com/{UPDATE_REPO}"
DISCORD_URL = ""
DONATE_URL = ""
DONATE_LABEL = "Ko-Fi"

# -----------------------------------------------------------------------------
# Statisztika
# -----------------------------------------------------------------------------
# Az eredeti Rose a saját szerverére küldött használati pingeket.
# Saját verzióban ennek nincs értelme, ezért alapból ki van kapcsolva.
ANALYTICS_ENABLED = False
