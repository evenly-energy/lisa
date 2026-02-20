"""Git worktree management."""

import os
import shutil
import subprocess
from typing import Optional

from lisa.ui.output import error, log, success, warn


def create_session_worktree(session_name: str) -> Optional[str]:
    """Create detached worktree for multi-ticket session. Returns path or None."""
    worktree_path = f"/tmp/lisa/{session_name}"

    # Remove stale worktree if exists
    if os.path.exists(worktree_path):
        log(f"Removing stale worktree at {worktree_path}")
        if not remove_worktree(worktree_path):
            error(f"Failed to clean up stale worktree at {worktree_path}")
            return None

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
    """Remove worktree and its directory with aggressive fallback cleanup."""
    if not worktree_path or not worktree_path.startswith("/tmp/lisa/"):
        return False  # Safety check

    log(f"Removing worktree at {worktree_path}")

    # Step 1: Try git worktree remove --force
    result = subprocess.run(
        ["git", "worktree", "remove", worktree_path, "--force"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return True

    # Step 2: Fallback - forcibly remove directory
    warn(f"git worktree remove failed: {result.stderr}")

    directory_removed = True
    if os.path.exists(worktree_path):
        log(f"Forcing directory cleanup: {worktree_path}")
        try:
            shutil.rmtree(worktree_path, ignore_errors=False)
        except OSError as e:
            error(f"Failed to remove worktree directory: {e}")
            directory_removed = False

    # Step 3: Clean up git metadata regardless of directory removal
    # Get repository root to find .git/worktrees
    repo_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )

    if repo_root_result.returncode == 0:
        repo_root = repo_root_result.stdout.strip()
        worktree_name = os.path.basename(worktree_path)
        metadata_path = os.path.join(repo_root, ".git", "worktrees", worktree_name)

        if os.path.exists(metadata_path):
            log(f"Removing orphaned worktree metadata: {metadata_path}")
            try:
                shutil.rmtree(metadata_path)
            except OSError as e:
                warn(f"Failed to remove worktree metadata: {e}")

    return directory_removed
