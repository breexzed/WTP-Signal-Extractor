"""Where an installed `wtp` keeps things, which version it is, and how it updates.

Installed tools can't assume the working directory is the repo, so config and
data live in per-user directories (XDG). Releases are GitHub tags; updating
reinstalls the latest tag with `uv tool install --force`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from dotenv import load_dotenv

PACKAGE = "wtp-signal-extractor"
REPO = "breexzed/WTP-Signal-Extractor"
INSTALL_SOURCE = f"git+https://github.com/{REPO}"


def _xdg(env: str, fallback: str) -> Path:
    return Path(os.getenv(env) or Path.home() / fallback)


def config_dir() -> Path:
    return Path(os.getenv("WTP_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / "wtp")


def data_dir() -> Path:
    return Path(os.getenv("WTP_DATA_DIR") or _xdg("XDG_DATA_HOME", ".local/share") / "wtp")


def load_config() -> list[str]:
    """Load .env from the working directory, then the user config file. Real
    environment variables win over both; the working directory wins over the
    user file. Returns the files that were found."""
    loaded = []
    for path in (Path.cwd() / ".env", config_dir() / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(str(path))
    return loaded


def current_version() -> str:
    try:
        return package_version(PACKAGE)
    except PackageNotFoundError:
        return "0.0.0+source"


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text.split("+")[0])[:3])


def installed_as_uv_tool() -> bool:
    return f"{os.sep}uv{os.sep}tools{os.sep}" in sys.prefix


def latest_release(timeout: float = 5.0) -> dict[str, str] | None:
    """The newest GitHub release, or None if there is none. Raises OSError on network failure."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"{PACKAGE}/{current_version()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return {"tag": data["tag_name"], "url": data["html_url"], "published_at": data.get("published_at")}


def check_update() -> dict[str, object]:
    current = current_version()
    release = latest_release()
    latest = release["tag"] if release else None
    available = bool(latest) and version_tuple(latest) > version_tuple(current)
    return {
        "current": current,
        "latest": latest,
        "update_available": available,
        "release_url": release["url"] if release else None,
        "installed_as_uv_tool": installed_as_uv_tool(),
        "upgrade_command": f"uv tool install --force {INSTALL_SOURCE}@{latest}" if latest else None,
    }


def self_update() -> dict[str, object]:
    info = check_update()
    if not info["update_available"]:
        return {**info, "updated": False, "reason": "already up to date"}
    if not info["installed_as_uv_tool"]:
        return {**info, "updated": False,
                "reason": "not installed with `uv tool install` (a source checkout updates with git pull)"}
    uv = shutil.which("uv")
    if not uv:
        return {**info, "updated": False, "reason": "uv not found on PATH; run upgrade_command by hand"}
    proc = subprocess.run([uv, "tool", "install", "--force", f"{INSTALL_SOURCE}@{info['latest']}"],
                          capture_output=True, text=True)
    return {**info, "updated": proc.returncode == 0,
            "reason": None if proc.returncode == 0 else proc.stderr.strip()[-500:]}
