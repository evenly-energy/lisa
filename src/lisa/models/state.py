"""State models for iteration and work context."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from lisa.models.core import Assumption, ExplorationFindings


class WorkState(Enum):
    """States in the work loop state machine."""

    SELECT_STEP = auto()  # Check completion, select next step
    EXECUTE_WORK = auto()  # Call Claude
    HANDLE_ASSUMPTIONS = auto()  # Process assumptions
    CHECK_COMPLETION = auto()  # Evaluate work result
    VERIFY_STEP = auto()  # Run tests/review
    COMMIT_CHANGES = auto()  # Git commit
    SAVE_STATE = auto()  # Persist to Linear
    ALL_DONE = auto()  # Terminal: run conclusion
    FINAL_REVIEW = auto()  # Final review with fix loop
    MAX_ITERATIONS = auto()  # Terminal: failed


@dataclass
class IterationState:
    """State tracked during a single iteration."""

    files_changed: list[str] = field(default_factory=list)
    test_errors: list[str] = field(default_factory=list)
    review_issues: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)


@dataclass
class RunConfig:
    """CLI arguments bundled together."""

    ticket_ids: list[str]
    max_iterations: int
    effort: str
    model: str
    dry_run: bool = False
    push: bool = False
    yolo: bool = False
    fallback_tools: bool = False
    verbose: bool = False
    skip_verify: bool = False
    skip_plan: bool = False
    interactive: bool = False
    always_interactive: bool = False
    debug: bool = False
    review_only: bool = False
    conclusion: bool = False
    worktree: bool = False
    preflight: bool = False
    spice: bool = False


@dataclass
class WorkContext:
    """State tracked across the work loop state machine."""

    # Ticket info (immutable for this ticket)
    ticket_id: str
    title: str
    description: str
    issue_uuid: str
    issue_url: str
    branch_name: str
    subtasks: list[dict]

    # Mutable state
    plan_steps: list[dict]
    all_assumptions: list[Assumption]
    assumptions: list[Assumption]  # current iteration, cleared on commit
    exploration: Optional[ExplorationFindings]

    # Iteration tracking
    state_iteration: int  # Resumed iteration count
    loop_iter: int  # Current loop iteration (1-based)
    iter_start: float
    total_start: float

    # Current step info
    current_step: Optional[int]
    step_desc: Optional[str]
    commit_ticket: str  # Ticket for commit message
    work_result: Optional[dict]

    # Error context for retry
    last_test_error: Optional[str]
    last_review_issues: Optional[str]
    last_completion_issues: Optional[str]

    # Iteration state for commit
    iter_state: dict

    # Verification results
    tests_passed: bool
    step_done: bool
    review_status: str

    # Persistence
    comment_id: Optional[str]
    log_entries: list[str]

    # Config
    config: RunConfig

    # Verification retry tracking (defaults at end for dataclass compat)
    verify_attempts: int = 0
    max_verify_attempts: int = 3

    # Final review tracking
    final_review_attempts: int = 0
    final_review_status: Optional[str] = None  # "APPROVED" | "NEEDS_FIXES" | "SKIPPED"
    final_review_summary: Optional[str] = None
    final_review_issues: Optional[str] = None

    @property
    def iteration(self) -> int:
        """Current absolute iteration number."""
        return self.state_iteration + self.loop_iter

    @property
    def comment_url(self) -> str:
        """URL to the state comment (or issue if no comment)."""
        if self.comment_id:
            return f"{self.issue_url}#comment-{self.comment_id[:8]}"
        return self.issue_url
