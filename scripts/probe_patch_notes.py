#!/usr/bin/env python3
"""Temporary: prints the structure of the official patch notes pages (run on CI)."""

import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Proteus-probe"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def main():
    for locale in ("hu-hu", "en-us"):
        index = f"https://www.leagueoflegends.com/{locale}/news/tags/patch-notes/"
        status, final, html = get(index)
        print(f"== INDEX {locale}: {status} {final} {len(html)} chars, __NEXT_DATA__: {'__NEXT_DATA__' in html}")
        links = sorted(set(re.findall(r'/(?:[a-z]{2}-[a-z]{2})/news/game-updates/[a-z0-9-]*patch[a-z0-9-]*/?', html)))
        print("links:", links[:15])
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if m:
            data = json.loads(m.group(1))
            text = json.dumps(data)
            urls = re.findall(r'"url":\s*"([^"]*patch[^"]*)"', text)
            print("next urls:", urls[:10])
            titles = re.findall(r'"title":\s*"([^"]*[Pp]atch[^"]*)"', text)
            print("next titles:", titles[:10])
            dates = re.findall(r'"publishedAt":\s*"([^"]+)"', text)
            print("dates:", dates[:5])
        if not links:
            continue
        page_url = "https://www.leagueoflegends.com" + links[-1] if False else None
        # newest: take first patch link in document order
        order = re.findall(r'/(?:[a-z]{2}-[a-z]{2})/news/game-updates/[a-z0-9-]*patch[a-z0-9-]*/?', html)
        page_url = "https://www.leagueoflegends.com" + order[0]
        status, final, page = get(page_url)
        print(f"== PAGE {locale}: {status} {final} {len(page)} chars")
        for cls in ("patch-change-block", "change-title", "change-detail-title", "ability-title", "attribute-change",
                    "attribute-before", "attribute-after", "summary", "blockquote", "context", "header-primary",
                    "content-border", "⇒", "&rArr;", "\\u21d2", "patch-champions", "patch-items", "patch-runes",
                    "__NEXT_DATA__", "richText", "<h2", "<h3", "<h4", "<li"):
            print(f"  count {cls!r}: {page.count(cls)}")
        for hid in re.findall(r'<h2[^>]*id="([^"]+)"', page)[:30]:
            print("  h2 id:", hid)
        i = page.find("patch-change-block")
        if i < 0:
            i = page.find("⇒")
        print("---- SAMPLE ----")
        print(page[max(0, i - 400): i + 5000])
        print("---- SAMPLE ITEMS ----")
        j = page.find('id="patch-items"')
        if j >= 0:
            print(page[j: j + 3500])
        print("---- END ----")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("probe failed:", repr(e))
        sys.exit(0)
