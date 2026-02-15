"""Branch management operations."""

import json
import re
import subprocess
from typing import Optional

from lisa.clients.claude import claude
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.ui.output import error, log, success


def get_current_branch() -> str:
    """Get current git branch name."""
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def list_branches_matching(pattern: str) -> list[str]:
    """List git branches matching a pattern (e.g., 'eng-71-*')."""
    result = subprocess.run(["git", "branch", "--list", pattern], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    # Parse branch names (strip whitespace, * for current, + for worktree)
    branches = [b.strip().lstrip("*+ ") for b in result.stdout.strip().split("\n") if b.strip()]
    return sorted(branches)


def get_base_slug(branch: str, prefix: str) -> str:
    """Extract base slug from branch name, stripping any numeric suffix.

    e.g., 'eng-71-trade-mon-3' -> 'eng-71-trade-mon'
    """
    # Remove prefix to get slug part
    if branch.startswith(f"{prefix}-"):
        slug_part = branch[len(prefix) + 1 :]
    else:
        return branch

    # Check if ends with -N (numeric suffix)
    match = re.match(r"^(.+)-(\d+)$", slug_part)
    if match:
        return f"{prefix}-{match.group(1)}"
    return branch


def find_next_suffix(branches: list[str], base: str) -> int:
    """Find next available numeric suffix for base branch name."""
    max_suffix = 1
    for b in branches:
        if b == base:
            max_suffix = max(max_suffix, 1)
        elif b.startswith(f"{base}-"):
            suffix_part = b[len(base) + 1 :]
            if suffix_part.isdigit():
                max_suffix = max(max_suffix, int(suffix_part))
    return max_suffix + 1


def generate_slug(title: str, description: str, max_len: int) -> str:
    """Use Haiku to generate a short branch slug from title and description."""
    prompts = get_prompts()
    schemas = get_schemas()

    prompt = prompts["slug"]["template"].format(
        max_len=max_len,
        title=title,
        description=description[:500] if description else "N/A",
    )
    result = claude(prompt, model="haiku", allowed_tools="", json_schema=schemas["slug"])
    try:
        data = json.loads(result)
        slug = data.get("slug", "")[:max_len]
        return slug if slug else "work"
    except json.JSONDecodeError:
        slug = re.sub(r"[^a-z0-9-]", "", result.strip().lower())
        return slug[:max_len] or "work"


def determine_branch_name(ticket_id: str, title: str, description: str) -> tuple[str, bool]:
    """Determine branch name for this ticket without any git operations.

    Returns (branch_name, already_exists) where already_exists means we're on or have the branch.
    """
    prefix = ticket_id.lower()

    # Already on ticket branch?
    current = get_current_branch()
    if current.startswith(f"{prefix}-"):
        return current, True

    # Find existing branches for this ticket
    existing = list_branches_matching(f"{prefix}-*")

    if not existing:
        # No branches yet - generate slug
        max_slug_len = 24 - len(prefix) - 1
        slug = generate_slug(title, description, max_slug_len)
        branch_name = f"{prefix}-{slug}" if slug else prefix
    else:
        # Branches exist - find base and increment
        base = get_base_slug(existing[0], prefix)
        suffix = find_next_suffix(existing, base)
        branch_name = f"{base}-{suffix}"

    return branch_name, False


def create_or_get_branch(
    ticket_id: str, title: str, description: str, spice: bool = False
) -> Optional[str]:
    """Determine branch for this ticket. Returns branch name or None on failure.

    Logic:
    1. If on ticket branch -> return it
    2. If branches exist -> create next increment (eng-71-foo-2)
    3. If no branches -> generate slug, create new
    """
    prefix = ticket_id.lower()

    # Already on ticket branch?
    current = get_current_branch()
    if current.startswith(f"{prefix}-"):
        log(f"Already on ticket branch {current}")
        if spice:
            # Ensure branch is tracked by git-spice (idempotent)
            subprocess.run(["gs", "branch", "track"], capture_output=True, text=True)
        return current

    # Find existing branches for this ticket
    existing = list_branches_matching(f"{prefix}-*")

    if not existing:
        # No branches yet - generate slug
        max_slug_len = 24 - len(prefix) - 1
        slug = generate_slug(title, description, max_slug_len)
        branch_name = f"{prefix}-{slug}" if slug else prefix
        log(f"No existing branches, creating {branch_name}")
    else:
        # Branches exist - find base and increment
        base = get_base_slug(existing[0], prefix)
        suffix = find_next_suffix(existing, base)
        branch_name = f"{base}-{suffix}"
        log(f"Found {len(existing)} existing branches, creating {branch_name}")

    # Create the branch
    if spice:
        result = subprocess.run(
            ["gs", "branch", "create", branch_name], capture_output=True, text=True
        )
        if result.returncode != 0:
            error(f"gs branch create failed: {result.stderr}")
            return None
        success(f"Created spice branch {branch_name}")
    else:
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name], capture_output=True, text=True
        )
        if result.returncode != 0:
            error(f"git checkout -b failed: {result.stderr}")
            return None
        success(f"Created branch {branch_name}")
    return branch_name
