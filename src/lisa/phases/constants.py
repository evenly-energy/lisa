"""Constants for phase execution."""

from typing import Optional

# Effort levels for Claude CLI --effort flag
EFFORT_WORK = "high"  # main implementation
EFFORT_PLANNING = "high"  # planning phase - exploration needs room
EFFORT_REVIEW = "medium"  # standard review/fix, conclusion, coverage
EFFORT_LIGHTWEIGHT = "low"  # completion checks, loop fixes
EFFORT_QUICK = "low"  # final review, review-only mode

# Ranking for resolve_effort (lower = less effort)
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}

# Limits
MAX_FIX_ATTEMPTS = 4  # Complex issues often need 3-5 attempts
MAX_HOOK_FIX_ATTEMPTS = 2  # Pre-commit hook fix attempts before --no-verify fallback
MAX_ISSUE_REPEATS = 3  # Only exit after same issue repeats this many times
DEFAULT_TEST_TIMEOUT = 600


def resolve_effort(phase: str, user_cap: Optional[str] = None) -> str:
    """Return the lower of phase default and user cap."""
    if user_cap is None:
        return phase
    if EFFORT_RANK.get(user_cap, 2) < EFFORT_RANK.get(phase, 2):
        return user_cap
    return phase
