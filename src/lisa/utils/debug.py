"""Debug logging utilities."""

import json
import time
from pathlib import Path

from lisa.models.state import RunConfig
from lisa.ui.output import GRAY, MAGENTA, NC

DEBUG_LOG = Path(".lisa/debug.log")


def debug_log(config_or_debug: RunConfig | bool, label: str, data) -> None:
    """Append debug info to log file if debug mode enabled."""
    enabled = config_or_debug.debug if isinstance(config_or_debug, RunConfig) else config_or_debug
    if not enabled:
        return

    DEBUG_LOG.parent.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with open(DEBUG_LOG, "a") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"[{timestamp}] {label}\n")
        f.write(f"{'=' * 60}\n")
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                f.write(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                f.write(data)
        else:
            f.write(json.dumps(data, indent=2))
        f.write("\n")
    print(f"\r\033[K{MAGENTA}[debug]{NC} {label}  {GRAY}-> {DEBUG_LOG}{NC}")
