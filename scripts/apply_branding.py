#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Copy the values of branding.py into the Pengu Loader plugins.

The plugins run inside the League client and cannot import Python, so their
constants are rewritten in place. Safe to run any number of times.

    python scripts/apply_branding.py           # rewrite the plugins
    python scripts/apply_branding.py --check   # exit 1 if they are out of date
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import branding  # noqa: E402

PLUGINS = ROOT / "Pengu Loader" / "plugins"

# file -> {JS constant name: value}
CONSTANTS = {
    PLUGINS / "PROTEUS-SettingsPanel" / "index.js": {
        "DISCORD_INVITE_URL": branding.DISCORD_URL,
        "KOFI_URL": branding.DONATE_URL,
        "KOFI_LABEL": branding.DONATE_LABEL,
        "GITHUB_URL": branding.GITHUB_URL,
    },
    PLUGINS / "PROTEUS-UI" / "index.js": {
        "DISCORD_INVITE_URL": branding.DISCORD_URL,
        "PROTEUS_GITHUB_REPO_API_URL": f"https://api.github.com/repos/{branding.UPDATE_REPO}",
    },
}


def apply(check_only: bool = False) -> bool:
    """Rewrite the constants; return True if every file was already up to date."""
    up_to_date = True
    for path, values in CONSTANTS.items():
        text = path.read_text(encoding="utf-8")
        new_text = text
        for name, value in values.items():
            # const NAME = "..."; (the value may sit on the next line)
            pattern = re.compile(r'(const\s+' + re.escape(name) + r'\s*=\s*)"(?:[^"\\]|\\.)*"(;)')
            new_text, count = pattern.subn(lambda m: m.group(1) + json.dumps(value) + m.group(2), new_text)
            if count != 1:
                raise SystemExit(f"[branding] {name} found {count} times in {path.relative_to(ROOT)} (expected 1)")
        if new_text != text:
            up_to_date = False
            if check_only:
                print(f"[branding] out of date: {path.relative_to(ROOT)}")
            else:
                path.write_text(new_text, encoding="utf-8", newline="")
                print(f"[branding] updated: {path.relative_to(ROOT)}")
    # Inno Setup installer: #define MyAppURL "..."
    iss = ROOT / "installer.iss"
    text = iss.read_text(encoding="utf-8")
    new_text, count = re.subn(r'(#define MyAppURL )"[^"]*"', lambda m: m.group(1) + f'"{branding.GITHUB_URL}"', text)
    if count != 1:
        raise SystemExit(f"[branding] MyAppURL found {count} times in installer.iss (expected 1)")
    if new_text != text:
        up_to_date = False
        if check_only:
            print("[branding] out of date: installer.iss")
        else:
            iss.write_bytes(new_text.encode("utf-8"))
            print("[branding] updated: installer.iss")
    return up_to_date


if __name__ == "__main__":
    check = "--check" in sys.argv[1:]
    ok = apply(check_only=check)
    if check and not ok:
        print("Run: python scripts/apply_branding.py")
        sys.exit(1)
    if ok:
        print("[branding] plugins already match branding.py")
