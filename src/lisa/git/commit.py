"""Git commit operations with trailers."""

import subprocess
from typing import Optional

from lisa.clients.claude import claude, work_claude
from lisa.models.core import Assumption
from lisa.phases.constants import MAX_HOOK_FIX_ATTEMPTS
from lisa.ui.output import (
    error,
    error_with_conclusion,
    log,
    success_with_conclusion,
    warn,
    warn_with_conclusion,
)


def get_changed_files() -> list[str]:
    """Get list of files with uncommitted changes (modified + untracked)."""
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    files = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            # Format: "XY filename" or "XY filename -> newname"
            # Skip the 2-char status, then strip any leading spaces
            rest = line[2:].lstrip()  # Handle variable spacing after status
            filename = rest.split(" -> ")[-1]  # Handle renames
            files.append(filename)
    return files


def get_diff_summary() -> str:
    """Get diff content for Haiku to summarize."""
    # Get diff stat and actual diff for context
    stat = subprocess.run(["git", "diff", "--stat", "HEAD"], capture_output=True, text=True)
    diff = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True)
    # Also check for new files
    status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)

    context = ""
    if stat.stdout.strip():
        context += stat.stdout.strip()[:300] + "\n"
    if diff.stdout.strip():
        context += diff.stdout.strip()[:700]
    if not context and status.stdout.strip():
        # Fallback for untracked files
        context = "New files:\n" + status.stdout.strip()[:500]
    return context or "no changes"


def summarize_for_commit(full_desc: str) -> str:
    """Ask Claude to generate a short commit title summary."""
    prompt = f"""Summarize this step description for a git commit title.
Max 40 chars. Be concise, no fluff.

Step: {full_desc}

Reply with ONLY the summary, nothing else."""
    return claude(prompt, model="haiku", allowed_tools="").strip()


def format_assumptions_trailer(assumptions: list[Assumption]) -> str:
    """Format assumptions for git commit trailer (statements only, no rationale)."""
    if not assumptions:
        return ""
    selected = [a.statement[:50] for a in assumptions if a.selected]
    if not selected:
        return ""
    return "; ".join(selected)


def _get_staged_files() -> list[str]:
    """Return list of staged file paths from git diff --cached --name-only."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def git_commit(
    commit_ticket_id: str,
    iteration: int,
    task_title: str,
    task_body: str = "",
    iter_state: Optional[dict] = None,
    push: bool = False,
    files_to_add: Optional[list[str]] = None,
    assumptions: Optional[list[Assumption]] = None,
    allow_no_verify: bool = True,
    max_hook_fix_attempts: int = MAX_HOOK_FIX_ATTEMPTS,
    model: Optional[str] = None,
    yolo: bool = False,
    fallback_tools: bool = False,
) -> bool:
    """Commit changes, optionally push. Returns True on success.

    Uses Lisa-* trailers (new format) for state tracking.
    """
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.returncode != 0:
        error(f"git status failed: {result.stderr}")
        return False
    if not result.stdout.strip():
        log("No changes to commit")
        return True

    # Add specific files or all
    if files_to_add:
        result = subprocess.run(["git", "add", "--"] + files_to_add, capture_output=True, text=True)
    else:
        result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
    if result.returncode != 0:
        error(f"git add failed: {result.stderr}")
        return False

    # Build commit message with metadata (use Lisa-* trailers now)
    msg = f"feat(lisa): [{commit_ticket_id}] {task_title}"
    if task_body:
        msg += f"\n\n{task_body}"
    if iter_state:
        status = "PASS" if not iter_state.get("test_errors") else "FAIL"
        # Sanitize trailers: replace newlines, limit length
        test_error = iter_state["test_errors"][0] if iter_state.get("test_errors") else "none"
        test_error = test_error.replace("\n", " ").replace("\r", "")[:500]
        review_issues = (
            "; ".join(iter_state.get("review_issues", []))
            if iter_state.get("review_issues")
            else "none"
        )
        review_issues = review_issues.replace("\n", " ").replace("\r", "")[:500]
        msg += f"\n\nLisa-Iteration: {iteration}"
        msg += f"\nLisa-Status: {status}"
        msg += f"\nLisa-Test-Error: {test_error}"
        msg += f"\nLisa-Review-Issues: {review_issues}"

    # Add assumptions trailer if present
    if assumptions:
        assumptions_summary = format_assumptions_trailer(assumptions)
        if assumptions_summary:
            msg += f"\nLisa-Assumptions: {assumptions_summary}"

    result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    if result.returncode != 0:
        hook_output = result.stderr.strip()

        # Try fix loop if model is available
        if model and max_hook_fix_attempts > 0:
            for attempt in range(1, max_hook_fix_attempts + 1):
                staged_files = _get_staged_files()
                if not staged_files:
                    staged_files = files_to_add or []
                files_list = "\n".join(staged_files)

                warn(f"Pre-commit hook failed (fix attempt {attempt}/{max_hook_fix_attempts})")

                fix_prompt = (
                    f"Pre-commit hooks failed on commit. Fix the lint/format issues.\n\n"
                    f"Hook output:\n```\n{hook_output}\n```\n\n"
                    f"Staged files:\n{files_list}\n\n"
                    f"Read the failing files, fix ONLY hook/lint/format issues. "
                    f"Do NOT change functionality. Do NOT run git commit."
                )
                work_claude(fix_prompt, model, yolo, fallback_tools, effort="low")

                # Re-stage the fixed files
                if staged_files:
                    subprocess.run(
                        ["git", "add", "--"] + staged_files, capture_output=True, text=True
                    )

                # Retry commit
                result = subprocess.run(
                    ["git", "commit", "-m", msg], capture_output=True, text=True
                )
                if result.returncode == 0:
                    break
                hook_output = result.stderr.strip()

        # If still failing after fix attempts
        if result.returncode != 0:
            if not allow_no_verify:
                error_with_conclusion("Commit failed", result.stderr.strip(), raw=True)
                return False
            # Fall back to --no-verify
            warn_with_conclusion(
                "Commit failed", "retrying with --no-verify (hooks bypassed)", raw=True
            )
            msg_lines = msg.split("\n", 1)
            msg_lines[0] += " [no verify]"
            msg = "\n".join(msg_lines)
            result = subprocess.run(
                ["git", "commit", "--no-verify", "-m", msg], capture_output=True, text=True
            )
            if result.returncode != 0:
                error(f"git commit failed: {result.stderr}")
                return False

    # Get short SHA for display
    sha_result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    short_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else "?"
    success_with_conclusion(f"Committed ({commit_ticket_id})", short_sha, raw=True)

    if push:
        result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if result.returncode != 0:
            error(f"git push failed: {result.stderr}")
            return False
        from lisa.ui.output import success

        success("Pushed to remote")
    return True
