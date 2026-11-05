#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opens the Proteus window.

The window is Microsoft Edge in app mode (no tabs or address bar), which every
Windows 10/11 has, with a profile of its own under Proteus's data folder.
Proteus runs as administrator, and Edge started from it would be too (Edge
warns about that), so it is started through a shortcut the Windows shell
(explorer) opens: the shell runs it as the desktop user, unelevated.
Without Edge, the default browser opens the page instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from utils.core.logging import get_logger

log = get_logger()

WINDOW_SIZE = (1280, 820)
CREATE_NO_WINDOW = 0x08000000


def find_edge() -> Optional[Path]:
    """msedge.exe: App Paths in the registry, else its usual folders."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
                    value, _ = winreg.QueryValueEx(key, "")
                    if value and Path(value).is_file():
                        return Path(value)
            except OSError:
                continue
    except ImportError:
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def edge_arguments(url: str, profile_dir: Path) -> List[str]:
    width, height = WINDOW_SIZE
    return [
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        f"--window-size={width},{height}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeSidebarV2,msHubApps,msUndersideButton",
    ]


def _is_elevated() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_shortcut(link: Path, target: Path, arguments: List[str], icon: Optional[Path]) -> bool:
    """A .lnk to Edge with the window's arguments (made with the shell's COM object)."""
    args = subprocess.list2cmdline(arguments)
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _quote_ps(str(link)) + "); "
        "$s.TargetPath = " + _quote_ps(str(target)) + "; "
        "$s.Arguments = " + _quote_ps(args) + "; "
        + ("$s.IconLocation = " + _quote_ps(str(icon)) + "; " if icon else "")
        + "$s.Save()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            log.warning("[Window] Could not write the window shortcut: %s", (result.stderr or "").strip()[:300])
            return False
        return link.is_file()
    except Exception as e:
        log.warning("[Window] Could not write the window shortcut: %s", e)
        return False


def open_window(url: str, data_dir: Path, icon: Optional[Path] = None) -> bool:
    """Open the window on url. Returns whether something was started."""
    edge = find_edge()
    if edge is not None:
        profile_dir = data_dir / "window-profile"
        arguments = edge_arguments(url, profile_dir)
        try:
            if _is_elevated():
                link = data_dir / "Proteus window.lnk"
                if _write_shortcut(link, edge, arguments, icon):
                    subprocess.Popen(["explorer.exe", str(link)], creationflags=CREATE_NO_WINDOW)
                    log.info("[Window] Opened the window (Edge, unelevated through the shell)")
                    return True
                log.warning("[Window] Opening the window in the default browser instead")
            else:
                subprocess.Popen([str(edge), *arguments], creationflags=CREATE_NO_WINDOW)
                log.info("[Window] Opened the window (Edge)")
                return True
        except Exception as e:
            log.warning("[Window] Could not start Edge: %s", e)
    # The default browser, through the shell when elevated (it then runs as the user)
    try:
        if sys.platform == "win32" and _is_elevated():
            subprocess.Popen(["explorer.exe", url], creationflags=CREATE_NO_WINDOW)
        else:
            webbrowser.open(url)
        log.info("[Window] Opened the window in the default browser")
        return True
    except Exception as e:
        log.error("[Window] Could not open the window: %s", e)
        return False
