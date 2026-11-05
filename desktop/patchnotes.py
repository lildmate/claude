#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The latest official patch notes, in Hungarian, with buff/nerf conclusions.

The notes come from leagueoflegends.com (hu-hu, else en-us). Each champion and
item there has the designers' own explanation (why, and what it means) and its
changes as "Label: old ⇒ new". The verdict per champion or item is drawn
from those numbers (more damage is better, a longer cooldown or a higher cost
is worse) and from the explanation's own words (buff/nerf).
"""

from __future__ import annotations

import json
import re
import threading
import time
from html.parser import HTMLParser
from typing import Callable, Dict, List, Optional, Tuple

import requests

from utils.core.logging import get_logger

log = get_logger()

SITE = "https://www.leagueoflegends.com"
INDEX_PATH = "/{locale}/news/tags/patch-notes/"
PATCH_LINK = re.compile(r"/([a-z]{2}-[a-z]{2})/news/game-updates/league-of-legends-patch-(\d+)-(\d+)-notes/?")
SECTIONS = {"patch-champions": "champions", "patch-items": "items"}
ARROW = "⇒"
CACHE_TTL_S = 60 * 60
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Proteus"}

# Labels where a smaller number is better for the champion or item
LOWER_IS_BETTER = re.compile(
    r"cooldown|cost|cast time|delay|recharge|lockout|"
    r"töltődési|visszatöltés|újratöltés|költség|ár\b|késleltetés|felkészülési idő|"
    r"mana|energia|energy",
    re.IGNORECASE,
)
# Words in the designers' explanation
BUFF_WORDS = re.compile(r"\bbuff|erősít|erősebb|erősöd|erősödik", re.IGNORECASE)
NERF_WORDS = re.compile(r"\bnerf|gyengít|gyengébb|gyengül", re.IGNORECASE)
NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


# -- parsing -------------------------------------------------------------------------

class _NotesParser(HTMLParser):
    """Champions and items with their explanation and changes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section: Optional[str] = None
        self.entries: Dict[str, List[dict]] = {"champions": [], "items": []}
        self.entry: Optional[dict] = None
        self.detail: str = ""
        self._capture: Optional[str] = None  # "h2", "title", "context", "detail", "line"
        self._depth = 0
        self._text: List[str] = []
        self._line_tag: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if self._capture:
            self._depth += 1 if tag not in ("br", "img", "hr") else 0
            return
        if tag == "h2":
            self.section = SECTIONS.get(attrs.get("id") or "")
            self.entry = None
            self._start("h2")
        elif self.section is None:
            return
        elif tag == "h3" and "change-title" in classes:
            self._start("title")
        elif tag == "blockquote" and "context" in classes and self.entry is not None:
            self._start("context")
        elif tag == "h4" and "change-detail-title" in classes:
            self._start("detail")
        elif tag in ("li", "p") and self.entry is not None:
            self._start("line")
            self._line_tag = tag

    def _start(self, what):
        self._capture = what
        self._depth = 1
        self._text = []

    def handle_endtag(self, tag):
        if not self._capture:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = re.sub(r"\s+", " ", "".join(self._text)).strip()
        what, self._capture = self._capture, None
        if what == "title" and text:
            self.entry = {"name": text, "context": "", "changes": []}
            self.entries[self.section].append(self.entry)
            self.detail = ""
        elif what == "context" and self.entry is not None and text:
            self.entry["context"] = (self.entry["context"] + " " + text).strip()
        elif what == "detail":
            self.detail = text
        elif what == "line" and self.entry is not None and ARROW in text:
            change = parse_change(text, self.detail)
            if change:
                self.entry["changes"].append(change)

    def handle_data(self, data):
        if self._capture:
            self._text.append(data)


def parse_change(text: str, detail: str = "") -> Optional[dict]:
    """'Label: old ⇒ new' with its direction for the champion or item."""
    left, _, right = text.partition(ARROW)
    label, sep, old = left.partition(":")
    if not sep:
        label, old = "", left
    label, old, new = label.strip(), old.strip(), right.strip()
    if not new:
        return None
    return {
        "detail": detail,
        "label": label,
        "old": old,
        "new": new,
        "effect": change_effect(label or detail, old, new),
        "percent": percent_change(old, new),
    }


def _numbers(text: str) -> List[float]:
    return [float(n.replace(",", ".")) for n in NUMBER.findall(text)]


def change_effect(label: str, old: str, new: str) -> str:
    """'better', 'worse' or 'other' for the champion or item."""
    a, b = _numbers(old), _numbers(new)
    if not a or not b or len(a) != len(b):
        return "other"
    diff = sum(b) - sum(a)
    if abs(diff) < 1e-9:
        return "other"
    up = diff > 0
    if LOWER_IS_BETTER.search(label or ""):
        up = not up
    return "better" if up else "worse"


def percent_change(old: str, new: str) -> Optional[int]:
    """The relative change when both sides are one number (8 ⇒ 7: -12)."""
    a, b = _numbers(old), _numbers(new)
    if len(a) != 1 or len(b) != 1 or a[0] == 0:
        return None
    return round((b[0] - a[0]) / abs(a[0]) * 100)


def verdict(entry: dict) -> str:
    """'buff', 'nerf' or 'adjust' for one champion or item."""
    score = 0
    for change in entry["changes"]:
        score += {"better": 1, "worse": -1}.get(change["effect"], 0)
    context = entry.get("context") or ""
    if BUFF_WORDS.search(context) and not NERF_WORDS.search(context):
        score += 2
    elif NERF_WORDS.search(context) and not BUFF_WORDS.search(context):
        score -= 2
    return "buff" if score > 0 else "nerf" if score < 0 else "adjust"


def parse_notes(html: str) -> Dict[str, List[dict]]:
    parser = _NotesParser()
    parser.feed(html)
    parser.close()
    result = {}
    for section, entries in parser.entries.items():
        kept = []
        for entry in entries:
            if not entry["changes"] and not entry["context"]:
                continue
            entry["verdict"] = verdict(entry)
            entry["better"] = sum(1 for c in entry["changes"] if c["effect"] == "better")
            entry["worse"] = sum(1 for c in entry["changes"] if c["effect"] == "worse")
            kept.append(entry)
        result[section] = kept
    return result


def latest_patch_link(index_html: str) -> Optional[Tuple[str, str]]:
    """The newest patch's (url, name) on the patch notes index."""
    best = None
    for match in PATCH_LINK.finditer(index_html):
        key = (int(match.group(2)), int(match.group(3)))
        if best is None or key > best[0]:
            best = (key, match.group(0))
    if not best:
        return None
    (season, number), path = best
    return SITE + path.rstrip("/") + "/", f"{season}.{number}"


# -- fetching -------------------------------------------------------------------------

class PatchNotes:
    def __init__(self, http_get: Optional[Callable] = None):
        self._get = http_get or (lambda url: requests.get(url, headers=HEADERS, timeout=20))
        self._cache: Optional[Tuple[float, dict]] = None
        self._lock = threading.Lock()

    def latest(self) -> Optional[dict]:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < CACHE_TTL_S:
                return self._cache[1]
        for locale in ("hu-hu", "en-us"):
            try:
                result = self._fetch(locale)
            except Exception as e:
                log.warning("[Window] Patch notes (%s) failed: %s", locale, e)
                continue
            if result:
                with self._lock:
                    self._cache = (time.monotonic(), result)
                return result
        return None

    def _fetch(self, locale: str) -> Optional[dict]:
        index = self._get(SITE + INDEX_PATH.format(locale=locale))
        if index.status_code != 200:
            return None
        link = latest_patch_link(index.text)
        if not link:
            return None
        url, patch = link
        page = self._get(url)
        if page.status_code != 200:
            return None
        notes = parse_notes(page.text)
        if not notes["champions"] and not notes["items"]:
            return None
        return {"patch": patch, "url": url, "locale": locale, **notes}


if __name__ == "__main__":  # prints the live notes (used on CI to check the parser)
    data = PatchNotes().latest()
    print(json.dumps(data, ensure_ascii=False, indent=1)[:20000] if data else "no notes")
