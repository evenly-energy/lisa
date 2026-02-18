"""Git worktree management."""

import os
import subprocess
from typing import Optional

from lisa.ui.output import error, log, success, warn


def create_session_worktree(session_name: str) -> Optional[str]:
    """Create detached worktree for multi-ticket session. Returns path or None."""
    worktree_path = f"/tmp/lisa/{session_name}"

    # If dir exists, try to remove stale worktree first
    if os.path.exists(worktree_path):
        log(f"Removing stale worktree at {worktree_path}")
        subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"],
            capture_output=True,
            text=True,
        )

    # Create detached worktree at HEAD
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", worktree_path, "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"git worktree add failed: {result.stderr}")
        return None

    success(f"Created session worktree at {worktree_path}")

    return worktree_path


def remove_worktree(worktree_path: str) -> bool:
    """Remove worktree and its directory."""
    if not worktree_path or not worktree_path.startswith("/tmp/lisa/"):
        return False  # Safety check

    log(f"Removing worktree at {worktree_path}")
    result = subprocess.run(
        ["git", "worktree", "remove", worktree_path, "--force"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"git worktree remove failed: {result.stderr}")
        return False

    return True
