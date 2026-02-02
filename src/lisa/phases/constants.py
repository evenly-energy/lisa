"""Constants for phase execution."""

from typing import Optional

# Turn multipliers - relative to max_turns base
TURNS_LIGHTWEIGHT = 0.4  # 40 at 100 (quick reviews, loop fixes - need room to reason)
TURNS_QUICK = 0.25  # 25 at 100 (re-review phases)
TURNS_REVIEW = 0.50  # 50 at 100 (standard review/fix)
TURNS_PLANNING = 1.0  # 100 at 100 (planning phase - exploration needs room)
TURNS_WORK = 1.0  # 100 at 100 (main work)

# Limits
MAX_FIX_ATTEMPTS = 4  # Complex issues often need 3-5 attempts
MAX_ISSUE_REPEATS = 3  # Only exit after same issue repeats this many times
DEFAULT_TEST_TIMEOUT = 600


def calc_turns(base: int, multiplier: float) -> Optional[int]:
    """Calculate turns from base. Returns None if base is -1 (unlimited)."""
    if base == -1:
        return None
    assert base >= 0, f"base must be >= -1, got {base}"
    return max(1, int(base * multiplier))
