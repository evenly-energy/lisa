"""Execution phases: planning, work, verification, and conclusion."""

from lisa.phases.conclusion import (
    format_conclusion_markdown,
    gather_conclusion_context,
    print_conclusion,
    run_conclusion_phase,
    save_conclusion_to_linear,
)
from lisa.phases.planning import run_planning_phase, sort_by_dependencies
from lisa.phases.verify import (
    run_coverage_fix_phase,
    run_coverage_gate,
    run_fix_phase,
    run_review_phase,
    run_test_fix_phase,
    run_test_phase,
    verify_step,
)
from lisa.phases.work import (
    format_exploration_context,
    format_step_files,
    handle_all_done,
    handle_assumptions,
    handle_check_completion,
    handle_commit_changes,
    handle_execute_work,
    handle_max_iterations,
    handle_save_state,
    handle_select_step,
    handle_verify_step,
    log_step_files,
    process_ticket_work,
)

__all__ = [
    # Planning
    "run_planning_phase",
    "sort_by_dependencies",
    # Work
    "format_exploration_context",
    "format_step_files",
    "log_step_files",
    "handle_select_step",
    "handle_execute_work",
    "handle_assumptions",
    "handle_check_completion",
    "handle_verify_step",
    "handle_commit_changes",
    "handle_save_state",
    "handle_all_done",
    "handle_max_iterations",
    "process_ticket_work",
    # Verify
    "run_test_phase",
    "run_review_phase",
    "run_fix_phase",
    "run_test_fix_phase",
    "verify_step",
    "run_coverage_gate",
    "run_coverage_fix_phase",
    # Conclusion
    "gather_conclusion_context",
    "run_conclusion_phase",
    "print_conclusion",
    "format_conclusion_markdown",
    "save_conclusion_to_linear",
]
