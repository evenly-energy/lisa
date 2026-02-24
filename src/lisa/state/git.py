"""Git state recovery from commit trailers with backwards compatibility."""

import subprocess
from typing import Optional

# Trailer prefixes - Lisa (new) and Tralph (legacy) for backwards compat
TRAILER_PREFIXES = ["Lisa-", "Tralph-"]


def fetch_git_state(branch_name: str, subtask_id: Optional[str] = None) -> dict:
    """Parse state from lisa/tralph commits on branch.

    Supports both Lisa-* and Tralph-* trailers for backwards compatibility.

    Returns dict with:
    - iterations: list of iteration dicts (for history display, max 3)
    - last_test_error: test error from most recent commit (or None)
    - last_review_issues: review issues from most recent commit (or None)
    """
    # Search for commits matching subtask or all tralph/lisa commits
    # Support both legacy "type(tralph):" and new "type(lisa):" prefixes
    if subtask_id:
        grep_pattern = f"\\w+\\((tralph|lisa)\\): \\[{subtask_id}\\]"
    else:
        # Match either Lisa-Iteration or Tralph-Iteration trailers
        grep_pattern = "(Lisa|Tralph)-Iteration:"

    # Use main..branch_name to only get commits unique to this branch (not shared ancestry)
    result = subprocess.run(
        [
            "git",
            "log",
            f"--grep={grep_pattern}",
            "--extended-regexp",
            "--format=%B%x00",
            f"main..{branch_name}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"iterations": [], "last_test_error": None, "last_review_issues": None}

    iterations = []
    last_test_error: Optional[str] = None
    last_review_issues: Optional[str] = None
    is_first_commit = True

    for commit_body in result.stdout.split("\x00"):
        if not commit_body.strip():
            continue
        state = {}
        for line in commit_body.split("\n"):
            # Check for both Lisa-* and Tralph-* prefixes
            for prefix in TRAILER_PREFIXES:
                if line.startswith(f"{prefix}Iteration:"):
                    try:
                        state["iteration"] = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif line.startswith(f"{prefix}Files:"):
                    files_str = line.split(":", 1)[1].strip()
                    state["files"] = [f.strip() for f in files_str.split(",") if f.strip()]  # type: ignore[assignment]
                elif line.startswith(f"{prefix}Errors:"):
                    state["errors"] = line.split(":", 1)[1].strip()  # type: ignore[assignment]
                elif line.startswith(f"{prefix}Fixes:"):
                    state["fixes"] = line.split(":", 1)[1].strip()  # type: ignore[assignment]
                elif line.startswith(f"{prefix}Test-Error:"):
                    val = line.split(":", 1)[1].strip()
                    if is_first_commit and val != "none":
                        last_test_error = val
                elif line.startswith(f"{prefix}Review-Issues:"):
                    val = line.split(":", 1)[1].strip()
                    if is_first_commit and val != "none":
                        last_review_issues = val
        if state:
            iterations.append(state)
        is_first_commit = False

    return {
        "iterations": iterations[:3],  # Keep last 3 for history display
        "last_test_error": last_test_error,
        "last_review_issues": last_review_issues,
    }
