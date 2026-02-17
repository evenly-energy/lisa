"""Git worktree management."""

import os
import subprocess
from typing import Optional

from lisa.ui.output import error, log, success, warn


def create_session_worktree(session_name: str, base_branch: Optional[str] = None) -> Optional[str]:
    """Create detached worktree for multi-ticket session. Returns path or None.

    If base_branch provided, checkout it after creation (for git-spice compatibility).
    """
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

    # If base_branch provided, checkout it in the worktree
    if base_branch:
        result = subprocess.run(
            ["git", "-C", worktree_path, "checkout", base_branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error(f"Failed to checkout {base_branch} in worktree: {result.stderr}")
            return None
        log(f"Checked out {base_branch} in worktree")

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
