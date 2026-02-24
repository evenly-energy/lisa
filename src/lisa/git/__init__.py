"""Git operations for branch management and commits."""

from lisa.git.branch import (
    create_or_get_branch,
    determine_branch_name,
    find_next_suffix,
    get_base_slug,
    get_current_branch,
    list_branches_matching,
)
from lisa.git.commit import (
    format_assumptions_trailer,
    get_changed_files,
    get_diff_stat,
    get_diff_summary,
    git_commit,
    summarize_for_commit,
)
from lisa.git.worktree import create_session_worktree, remove_worktree

__all__ = [
    # Branch
    "get_current_branch",
    "list_branches_matching",
    "get_base_slug",
    "find_next_suffix",
    "determine_branch_name",
    "create_or_get_branch",
    # Commit
    "get_changed_files",
    "get_diff_stat",
    "get_diff_summary",
    "summarize_for_commit",
    "git_commit",
    "format_assumptions_trailer",
    # Worktree
    "create_session_worktree",
    "remove_worktree",
]
