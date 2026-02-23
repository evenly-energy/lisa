"""Update check against GitHub releases API."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

RELEASES_URL = "https://api.github.com/repos/evenly-energy/lisa/releases/latest"
CACHE_DIR = Path.home() / ".config" / "lisa"
CACHE_FILE = CACHE_DIR / "update-check.json"
CACHE_TTL = 86400  # 24 hours


def parse_version(s: str) -> Optional[tuple[int, ...]]:
    """Parse version string like '0.4.1' or 'v0.4.1' into tuple. Returns None for dev/pre-release."""
    s = s.strip().lstrip("v")
    if not s or "dev" in s or "+" in s or "rc" in s or "alpha" in s or "beta" in s:
        return None
    try:
        parts = tuple(int(p) for p in s.split("."))
        return parts if parts else None
    except ValueError:
        return None


def _load_cache() -> Optional[dict]:
    """Read cached update check result."""
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(version: str) -> None:
    """Write update check result to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"last_check": time.time(), "latest_version": version}))


def _fetch_latest_version() -> Optional[str]:
    """Fetch latest release tag from GitHub. Returns version without v prefix."""
    req = urllib.request.Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "lisa-update-check"},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=3
        ) as resp:  # nosemgrep: dynamic-urllib-use-detected
            data = json.loads(resp.read())
            tag = data.get("tag_name", "")
            return tag.lstrip("v") if tag else None
    except Exception:
        return None


def check_for_update(current_version: str) -> Optional[str]:
    """Check if a newer version is available. Returns latest version string if newer, else None."""
    current = parse_version(current_version)
    if current is None:
        return None

    # Check cache first
    cache = _load_cache()
    if cache and time.time() - cache.get("last_check", 0) < CACHE_TTL:
        cached_ver: str = cache.get("latest_version", "")
        latest = parse_version(cached_ver)
        if latest and latest > current:
            return cached_ver
        return None

    # Fetch from GitHub
    fetched_ver = _fetch_latest_version()
    if fetched_ver:
        _save_cache(fetched_ver)
        latest = parse_version(fetched_ver)
        if latest and latest > current:
            return fetched_ver

    return None


REPO_URL = "git+https://github.com/evenly-energy/lisa"


def run_upgrade(main: bool = False, version: Optional[str] = None) -> None:
    """Upgrade lisa. Default: latest release. --main: latest main snapshot. Explicit version: pin to that tag."""
    if main:
        print("Upgrading lisa to latest main...")
        cmd = ["uv", "tool", "upgrade", "lisa"]
    else:
        if version:
            tag = version.lstrip("v")
        else:
            fetched = _fetch_latest_version()
            if not fetched:
                print("Failed to fetch latest release from GitHub.")
                sys.exit(1)
            tag = fetched
        print(f"Upgrading lisa to v{tag}...")
        cmd = ["uv", "tool", "install", f"{REPO_URL}@v{tag}", "--force"]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)
