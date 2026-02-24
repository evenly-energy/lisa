"""CLI entry point and argument parsing."""

import argparse
import atexit
import os
import signal
import subprocess
import sys
import time
import uuid
from importlib.metadata import version as get_version
from pathlib import Path
from typing import Optional

try:
    __version__ = get_version("lisa")
except Exception:
    __version__ = "dev"

from lisa.clients.claude import token_tracker
from lisa.clients.linear import fetch_ticket
from lisa.constants import EFFORT_QUICK, resolve_effort
from lisa.git.branch import (
    create_or_get_branch,
    determine_branch_name,
    find_next_suffix,
    get_base_slug,
    get_current_branch,
    get_default_branch,
    list_branches_matching,
)
from lisa.git.commit import get_diff_summary
from lisa.git.worktree import create_session_worktree, remove_worktree
from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import RunConfig, WorkContext
from lisa.phases.conclusion import print_conclusion, run_conclusion_phase
from lisa.phases.planning import run_planning_phase, sort_by_dependencies
from lisa.phases.verify import run_preflight, run_review_phase, run_setup
from lisa.phases.work import process_ticket_work
from lisa.state.comment import fetch_state, find_state_comment, save_state
from lisa.state.git import fetch_git_state
from lisa.ui.assumptions import edit_assumptions_curses
from lisa.ui.output import (
    BLUE,
    GREEN,
    NC,
    YELLOW,
    error,
    hyperlink,
    log,
    success,
    success_with_conclusion,
    warn,
)
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import DEBUG_LOG
from lisa.utils.formatting import fmt_cost, fmt_duration, fmt_tokens

# Defaults
DEFAULT_MAX_ITERATIONS = 30


def parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        prog="lisa",
        description="Lisa - Looping Implementor Saving Assumptions. Autonomous AI loop driven by Linear tickets.",
        epilog="""
Commands:
  lisa init                         Set up .lisa/ config for this project
  lisa login                        Authenticate with Linear (OAuth)
  lisa logout                       Clear stored Linear tokens
  lisa upgrade                      Upgrade to latest release
  lisa upgrade --main               Upgrade to latest main snapshot
  lisa upgrade <version>            Pin to specific version (e.g. 0.4.1)

Examples:
  %(prog)s ENG-123                    Run with project permissions
  %(prog)s ENG-123 -n 50              Run 50 iterations
  %(prog)s ENG-123 --effort medium     Cap effort level (reduce work per session)
  %(prog)s ENG-123 --skip-plan        Skip planning, use subtasks directly
  %(prog)s ENG-123 --push             Enable push after each commit
  %(prog)s ENG-123 --dry-run          Show ticket status without executing
  %(prog)s ENG-123 --fallback-tools   Use explicit tool allowlist
  %(prog)s ENG-123 --yolo              Skip all permission checks (unsafe)
  %(prog)s ENG-123 --skip-verify      Skip test and review phases

How it works:
  1. Fetches the Linear ticket, subtasks, and blocking relations
  2. Creates/checks out branch (reuses slug from existing branches)
  3. Loads state from comment on ticket (🤖 lisa · {branch})
  4. PLANNING PHASE: Claude analyzes ticket and creates granular step checklist
  5. Picks the first incomplete step from the plan
  6. Runs Claude Code to work on that step (effort controlled by --effort)
  7. When step done: runs tests, code review, fix loop (unless --skip-verify)
  8. Commits with: feat(lisa): [ENG-456] step N - description
  9. Updates state comment on ticket (checkboxes for each step)
  10. Repeats until max iterations reached

Planning phase:
  - Claude reads codebase and creates 5-20 granular steps
  - Steps are smaller than subtasks (5-15 min each)
  - Plan is stored in Linear comment with checkboxes
  - Use --skip-plan to bypass and use subtasks directly

Context management:
  - --effort low/medium/high controls Claude's work intensity (default: high)
  - Lower effort = faster but less thorough sessions
  - Each phase has a default effort that gets capped by the user flag

Verification (after step done):
  1. TEST: runs configured test commands (see prompts.yaml)
     - If tests fail, Claude tries to fix and re-test (max 2 attempts)
  2. REVIEW: checks conventions, security, test quality
  3. FIX: if review finds issues, fixes and re-tests (max 2 attempts)
     - After review fixes, tests are re-run with their own fix loop
  4. COMMIT: only commits if tests pass
  Use --skip-verify to bypass verification phases

Branch handling:
  - On ticket branch (eng-123-*): stays on current branch
  - Not on ticket branch: creates new incremental branch
  - Example: eng-123-foo exists -> creates eng-123-foo-2

State tracking:
  - Each branch has its own comment on the ticket
  - Comment shows plan with checkboxes and progress
  - Resumes from saved iteration count when re-running

Backwards compatibility:
  - Reads both Lisa-* and Tralph-* git trailers
  - Reads both lisa and tralph comment headers
  - Writes Lisa-* trailers and lisa headers for new state

Safety:
  - Uses project .claude/settings.json permissions by default
  - Use --fallback-tools for explicit allowlist if project not configured
  - Use --yolo to disable all checks (unsafe)
  - No push by default (use --push to enable)

Linear API:
  - Run `lisa login` for browser-based OAuth (recommended)
  - Or set LINEAR_API_KEY env var for API key auth
  - Run `lisa logout` to clear stored OAuth tokens

Completion signals (Claude outputs JSON with structured schema):
  {"step_done": N, ...}              Step N complete, move to next step
  {"blocked": "reason", ...}         Cannot proceed, exit loop with error

Tips:
  - Create subtasks on your Linear ticket as a checklist
  - Run in tmux/screen for long-running sessions
  - Check the lisa comment on your ticket for plan progress
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "tickets",
        metavar="TICKET_ID",
        nargs="+",
        help="Linear ticket ID(s) (e.g., ENG-123 ENG-456)",
    )
    parser.add_argument(
        "-n",
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        metavar="N",
        help=f"Maximum iterations before stopping (default: {DEFAULT_MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch ticket and show plan without executing work",
    )
    parser.add_argument(
        "-p",
        "--push",
        action="store_true",
        help="Push to remote after each commit (disabled by default for safety)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="opus",
        help="Claude model to use (default: opus)",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Skip all permission checks (unsafe, use only in isolated environments)",
    )
    parser.add_argument(
        "--fallback-tools",
        action="store_true",
        help="Use explicit tool allowlist instead of project settings",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (show raw API responses)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip test and review phases (faster but less safe)",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default="high",
        help="Effort level cap for Claude sessions (default: high)",
    )
    parser.add_argument(
        "--skip-plan",
        action="store_true",
        help="Skip planning phase, use Linear subtasks directly",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt to confirm assumptions after planning phase",
    )
    parser.add_argument(
        "-I",
        "--always-interactive",
        action="store_true",
        help="Prompt to confirm assumptions in both planning and work phases",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=f"Enable debug mode - logs all work JSON outputs to {DEBUG_LOG}",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Run only final review on current changes, output report",
    )
    parser.add_argument(
        "--conclusion",
        action="store_true",
        help="Generate review guide for current branch and exit (console only)",
    )
    parser.add_argument(
        "-w",
        "--worktree",
        action="store_true",
        help="Run in a temporary worktree (auto-cleaned on exit)",
    )
    parser.add_argument(
        "-c",
        "--preflight",
        action="store_true",
        help="Run all tests/linting before starting to verify clean codebase state",
    )
    parser.add_argument(
        "-s",
        "--spice",
        action="store_true",
        help="Use git-spice for stacked branches (requires gs)",
    )
    args = parser.parse_args()
    return RunConfig(
        ticket_ids=args.tickets,
        max_iterations=args.max_iterations,
        effort=args.effort,
        model=args.model,
        dry_run=args.dry_run,
        push=args.push,
        yolo=args.yolo,
        fallback_tools=args.fallback_tools,
        verbose=args.verbose,
        skip_verify=args.skip_verify,
        skip_plan=args.skip_plan,
        interactive=args.interactive,
        always_interactive=args.always_interactive,
        debug=args.debug,
        review_only=args.review_only,
        conclusion=args.conclusion,
        worktree=args.worktree,
        preflight=args.preflight,
        spice=args.spice,
    )


def validate_env() -> None:
    """Validate Linear authentication. Supports env var or OAuth token."""
    if os.environ.get("LINEAR_API_KEY"):
        return

    from lisa.auth import get_token, run_login_flow

    if get_token():
        return

    # No auth available — prompt user
    log("No Linear authentication found.")
    log("Options: set LINEAR_API_KEY env var or login via browser.")
    try:
        answer = input("Login via browser now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)

    if answer in ("", "y", "yes"):
        if run_login_flow():
            success("Logged in to Linear successfully.")
            return
        else:
            error("Login failed.")
    else:
        error("Linear authentication required. Run `lisa login` or set LINEAR_API_KEY.")
    sys.exit(1)


def log_config(config: RunConfig) -> None:
    """Log configuration status."""
    from lisa.config import get_config, get_config_loaded_sources, get_loaded_sources, get_prompts

    if len(config.ticket_ids) > 1:
        ticket_chain = " → ".join(config.ticket_ids)
        log(f"Running {len(config.ticket_ids)} tickets in series: {YELLOW}{ticket_chain}{NC}")
    else:
        log(f"Starting Lisa for {YELLOW}{config.ticket_ids[0]}{NC}")
    log(f"Max iterations: {config.max_iterations}, effort: {config.effort}, model: {config.model}")

    # Trigger loading so sources are populated
    get_prompts()
    get_config()
    prompt_overrides = [s for s in get_loaded_sources() if s != "defaults"]
    config_overrides = [s for s in get_config_loaded_sources() if s != "defaults"]
    all_overrides = list(dict.fromkeys(prompt_overrides + config_overrides))  # dedupe, keep order
    if all_overrides:
        log(f"Config overrides: {', '.join(all_overrides)}")

    if config.yolo:
        warn("YOLO MODE - all permission checks disabled")
    elif config.fallback_tools:
        log("Using fallback tool allowlist")
    if config.verbose:
        log("Verbose mode enabled")
    if config.skip_verify:
        warn("SKIP-VERIFY MODE - test and review phases disabled")
    if config.skip_plan:
        log("Planning phase disabled, using subtasks directly")
    if config.debug:
        log(f"Debug logging to {DEBUG_LOG}")
    if config.preflight:
        log("Preflight checks enabled")
    if config.spice:
        log("git-spice stacking enabled")
    if config.dry_run:
        log(f"{YELLOW}DRY RUN MODE - no changes will be made{NC}")
    if not config.push:
        log("Git: commit only (no push)")


def show_dry_run_status(
    ticket_id: str,
    ticket: dict,
    plan_steps: list[dict],
    current_step: Optional[int],
    state_iteration: int,
) -> None:
    """Display dry-run status and exit."""
    from lisa.ui.output import RED

    title = ticket.get("title", "Unknown")
    description = ticket.get("description", "")
    prefix = ticket_id.lower()
    existing_branches = list_branches_matching(f"{prefix}-*")

    print(f"\n{GREEN}Ticket:{NC} {title}")
    desc_display = f"{description[:200]}..." if len(description) > 200 else description
    print(f"{GREEN}Description:{NC} {desc_display}")
    print(f"\n{GREEN}Existing branches:{NC} {existing_branches or 'None'}")
    print(f"{GREEN}Current branch:{NC} {get_current_branch() or 'N/A'}")
    print(f"{GREEN}State iteration:{NC} {state_iteration}")

    done_count = sum(1 for s in plan_steps if s.get("done"))
    print(f"{GREEN}Progress:{NC} {done_count}/{len(plan_steps)} steps done")
    print(f"\n{GREEN}Plan steps:{NC}")

    for step in plan_steps:
        status = "✓" if step.get("done") else "○"
        marker = " ← current" if step["id"] == current_step else ""
        ticket_str = f" ({step.get('ticket', '')})" if step.get("ticket") else ""
        print(f"  {status} {step['id']}{ticket_str}: {step['description']}{marker}")
        for f in step.get("files", []):
            op_colors = {"create": GREEN, "modify": YELLOW, "delete": RED}
            color = op_colors.get(f["op"], "")
            parts = []
            if f.get("template"):
                parts.append(f"template: {f['template']}")
            if f.get("detail"):
                parts.append(f"detail: {f['detail']}")
            extra = ", ".join(parts)
            suffix = f" ({extra})" if extra else ""
            print(f"      {color}{f['op']}{NC}: {f['path']}{suffix}")

    incomplete = [s for s in plan_steps if not s.get("done")]
    next_step = incomplete[0] if incomplete else None
    print(f"\n{GREEN}Next step:{NC} {next_step['description'] if next_step else 'All done!'}")
    print(f"{GREEN}Remaining:{NC} {len(incomplete)} steps")
    sys.exit(0)


def print_review_report(result: dict) -> None:
    """Print structured review report to stdout."""
    from lisa.ui.output import RED

    status = f"{GREEN}APPROVED{NC}" if result["approved"] else f"{RED}NEEDS_FIXES{NC}"
    print(f"\n{BLUE}{'━' * 50}{NC}")
    print(f"Review: {status}")
    print(f"{BLUE}{'━' * 50}{NC}")

    if result.get("findings"):
        print("\nFindings:")
        for f in result["findings"]:
            icon = "✓" if f["status"] == "pass" else "✗" if f["status"] == "issue" else "~"
            print(f"  {icon} [{f['category']}] {f['detail']}")

    print(f"\nSummary: {result.get('summary', 'n/a')}")


def main() -> None:
    # Handle login/logout before argparse (which expects positional ticket IDs)
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        from lisa.auth import run_login_flow

        if run_login_flow():
            print("Logged in to Linear successfully.")
        else:
            print("Login failed.")
            sys.exit(1)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "logout":
        from lisa.auth import clear_tokens

        clear_tokens()
        print("Logged out. Stored tokens cleared.")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        from lisa.init import run_init

        run_init()
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "upgrade":
        from lisa.update import run_upgrade

        main = "--main" in sys.argv or "-m" in sys.argv
        # Find explicit version arg (not a flag, not "upgrade" itself)
        version = None
        for arg in sys.argv[2:]:
            if not arg.startswith("-"):
                version = arg
                break
        run_upgrade(main=main, version=version)
        sys.exit(0)

    config = parse_args()
    validate_env()
    log_config(config)

    if not Path(".lisa/config.yaml").exists():
        warn("No .lisa/config.yaml found. Run `lisa init` to configure this project.")

    try:
        from lisa.update import check_for_update

        latest = check_for_update(__version__)
        if latest:
            warn(f"Update available: {__version__} -> {latest}  (run: lisa upgrade)")
    except Exception:
        pass

    if config.spice:
        import shutil

        if not shutil.which("gs"):
            error("--spice requires git-spice (gs). Install: brew install git-spice")
            sys.exit(1)

    total_start = time.time()

    num_tickets = len(config.ticket_ids)
    failed_tickets: list[str] = []

    # Session worktree for multi-ticket mode
    session_worktree_path: Optional[str] = None
    session_preflight_branch: Optional[str] = None
    base_branch: Optional[str] = None
    session_original_cwd = os.getcwd()
    session_worktree_cleaned = False

    def cleanup_session_worktree() -> None:
        nonlocal session_worktree_cleaned
        if session_worktree_path and not session_worktree_cleaned:
            session_worktree_cleaned = True
            os.chdir(session_original_cwd)
            remove_worktree(session_worktree_path)

    def session_signal_handler(sig: int, frame: object) -> None:
        cleanup_session_worktree()
        sys.exit(128 + sig)

    if config.worktree and not config.dry_run:
        if config.spice:
            base_branch = get_default_branch()
            if not base_branch:
                error("Could not determine default branch for spice mode")
                sys.exit(1)

        session_name = "_".join(config.ticket_ids) + "_" + uuid.uuid4().hex[:8]
        session_worktree_path = create_session_worktree(session_name)
        if not session_worktree_path:
            error("Failed to create session worktree")
            sys.exit(1)
        os.chdir(session_worktree_path)

        atexit.register(cleanup_session_worktree)
        signal.signal(signal.SIGINT, session_signal_handler)
        signal.signal(signal.SIGTERM, session_signal_handler)

        # Create temp branch (detached HEAD causes issues for some test suites)
        preflight_branch = f"lisa-preflight-{uuid.uuid4().hex[:8]}"
        checkout = subprocess.run(
            ["git", "checkout", "-b", preflight_branch], capture_output=True, text=True
        )
        if checkout.returncode == 0:
            session_preflight_branch = preflight_branch

        # Setup: install deps in fresh worktree
        with LiveTimer("Setting up work...", total_start, print_final=False):
            setup_success = run_setup()
        if not setup_success:
            error("Setup failed - cannot continue")
            sys.exit(1)

        # Preflight: verify codebase is clean
        if config.preflight:
            with LiveTimer("Running preflight checks...", total_start, print_final=False):
                preflight_success = run_preflight()
            if not preflight_success:
                error("Preflight failed - fix issues before running lisa")
                sys.exit(1)
            success("Preflight passed")

    else:
        # No worktree: preflight runs in original dir (no setup needed)
        if config.preflight:
            with LiveTimer("Running preflight checks...", total_start, print_final=False):
                preflight_success = run_preflight()
            if not preflight_success:
                error("Preflight failed - fix issues before running lisa")
                sys.exit(1)
            success("Preflight passed")

    # Process tickets serially
    for ticket_idx, ticket_id in enumerate(config.ticket_ids, 1):
        if num_tickets > 1:
            print(f"\n{BLUE}{'═' * 60}{NC}")
            log(f"Starting ticket {ticket_idx}/{num_tickets}: {YELLOW}{ticket_id}{NC}")
            print(f"{BLUE}{'═' * 60}{NC}")

        # 1. Fetch ticket
        with LiveTimer("Fetching ticket...", total_start, print_final=False):
            ticket = fetch_ticket(ticket_id, verbose=config.verbose)
        if not ticket:
            error("Failed to fetch ticket")
            sys.exit(1)

        title = ticket.get("title", "Unknown")
        description = ticket.get("description", "")
        issue_uuid = ticket.get("uuid", "")
        issue_url = ticket.get("url", "")
        subtasks = ticket.get("subtasks", [])
        log(f"Ticket: {title}")

        # Review-only mode: run final review and exit
        if config.review_only:
            log("Review-only mode - running final review on current changes")
            # Load assumptions from Linear state if available
            assumptions: list[Assumption] = []
            branch_name = get_current_branch()
            if issue_uuid and branch_name:
                state = fetch_state(issue_uuid, branch_name)
                if state and state.get("assumptions"):
                    assumptions = state["assumptions"]
                    log(f"Loaded {len(assumptions)} assumptions from state")
            result = run_review_phase(
                title,
                description,
                total_start,
                config.model,
                config.yolo,
                config.fallback_tools,
                resolve_effort(EFFORT_QUICK, config.effort),
                lightweight=False,
                assumptions=assumptions if assumptions else None,
                debug=config.debug,
            )
            print_review_report(result)
            sys.exit(0 if result["approved"] else 1)

        # Conclusion mode: generate review guide for current branch and exit
        if config.conclusion:
            branch_name = get_current_branch()
            prefix = ticket_id.lower()
            if not branch_name.startswith(f"{prefix}-"):
                error(f"Not on ticket branch (current: {branch_name}, expected: {prefix}-*)")
                sys.exit(1)

            log(f"Conclusion mode - generating review guide for {branch_name}")

            # Load state from Linear to get plan steps, assumptions, and exploration
            plan_steps: list[dict] = []
            all_assumptions: list[Assumption] = []
            exploration: Optional[ExplorationFindings] = None

            if issue_uuid:
                state = fetch_state(issue_uuid, branch_name)
                if state:
                    plan_steps = state.get("plan_steps", [])
                    all_assumptions = state.get("assumptions", [])
                    log(
                        f"Loaded {len(plan_steps)} steps, {len(all_assumptions)} assumptions from state"
                    )

                # Try to load exploration from comment body
                comment = find_state_comment(issue_uuid, branch_name)
                if comment:
                    body = comment["body"]
                    # Parse exploration from markdown (simplified)
                    if "## Exploration" in body:
                        exploration = ExplorationFindings()
                        for line in body.split("\n"):
                            if line.startswith("**Patterns:**"):
                                exploration.patterns = [
                                    p.strip() for p in line.replace("**Patterns:**", "").split("|")
                                ]
                            elif line.startswith("**Modules:**"):
                                exploration.relevant_modules = [
                                    m.strip() for m in line.replace("**Modules:**", "").split(",")
                                ]

            conclusion = run_conclusion_phase(
                ticket_id=ticket_id,
                title=title,
                description=description,
                plan_steps=plan_steps,
                assumptions=all_assumptions,
                exploration=exploration,
                branch_name=branch_name,
                total_start=total_start,
                config=config,
            )
            print_conclusion(conclusion, ticket_id, title)
            sys.exit(0)

        # 2. Determine branch (skip in dry-run mode)
        branch_name = None  # type: ignore[assignment]

        if not config.dry_run:
            if config.worktree:
                # Session worktree already exists - just create/checkout branch
                branch_name, on_ticket_branch = determine_branch_name(ticket_id, title, description)
                if on_ticket_branch:
                    prefix = ticket_id.lower()
                    existing = list_branches_matching(f"{prefix}-*")
                    base = get_base_slug(branch_name, prefix)
                    suffix = find_next_suffix(existing, base)
                    branch_name = f"{base}-{suffix}"
                    log(f"Creating branch {branch_name}")

                # Create branch and checkout in worktree
                if config.spice:
                    cmd = ["gs", "branch", "create", "--no-commit", branch_name]
                    if config.worktree and base_branch:
                        cmd += ["--target", base_branch]
                    checkout = subprocess.run(cmd, capture_output=True, text=True)
                    if checkout.returncode != 0:
                        error(f"gs branch create failed: {checkout.stderr}")
                        sys.exit(1)
                    success(f"Created spice branch {branch_name}")
                else:
                    checkout = subprocess.run(
                        ["git", "checkout", "-B", branch_name], capture_output=True, text=True
                    )
                    if checkout.returncode != 0:
                        error(f"git checkout -B failed: {checkout.stderr}")
                        sys.exit(1)
                    success(f"Checked out branch {branch_name}")
            else:
                # Normal mode: checkout branch
                branch_name = create_or_get_branch(
                    ticket_id, title, description, spice=config.spice
                )  # type: ignore[assignment]
                if not branch_name:
                    error("Failed to create/get branch")
                    sys.exit(1)

        # Delete preflight temp branch now that we're on the ticket branch
        if session_preflight_branch:
            subprocess.run(
                ["git", "branch", "-D", session_preflight_branch],
                capture_output=True,
                text=True,
            )
            session_preflight_branch = None

        # 3. Fetch or initialize state
        state_iteration = 0
        comment_id: Optional[str] = None
        plan_steps = []
        current_step: Optional[int] = None
        log_entries: list[str] = []
        last_test_error: Optional[str] = None  # Track test errors between iterations
        last_review_issues: Optional[str] = None  # Track review issues between iterations

        if branch_name and issue_uuid:
            with LiveTimer("Fetching state...", total_start, print_final=False):
                # Fetch plan state from Linear comment
                state = fetch_state(issue_uuid, branch_name)
                # Fetch test/review state from last commit
                git_state = fetch_git_state(branch_name)

            if state:
                state_iteration = state.get("iterations", 0)
                comment_id = state.get("comment_id")
                plan_steps = state.get("plan_steps", [])
                current_step = state.get("current_step")
                done_count = sum(1 for s in plan_steps if s.get("done"))
                log(
                    f"Resuming from iteration {state_iteration}, {done_count}/{len(plan_steps)} steps done"
                )
            else:
                log("No existing state, starting fresh")

            # Read test/review state from last commit (not Linear)
            last_test_error = git_state.get("last_test_error")
            last_review_issues = git_state.get("last_review_issues")
            if last_test_error:
                warn(f"Previous test failure: {last_test_error[:80]}...")
            if last_review_issues:
                warn(f"Previous review issues: {last_review_issues[:80]}...")

        # 4. Run planning phase if needed
        assumptions = []
        all_assumptions = []
        prior_assumptions: Optional[list[Assumption]] = None
        exploration = None
        if not config.skip_plan and not plan_steps and not config.dry_run:
            while True:
                plan_steps, assumptions, exploration = run_planning_phase(
                    ticket_id=ticket_id,
                    title=title,
                    description=description,
                    subtasks=subtasks,
                    total_start=total_start,
                    model=config.model,
                    yolo=config.yolo,
                    fallback_tools=config.fallback_tools,
                    config=config,
                    prior_assumptions=prior_assumptions,
                )

                # Re-label planning assumptions with P.N format
                for i, a in enumerate(assumptions, 1):
                    a.id = f"P.{i}"

                # Interactive mode: let user edit assumption selections (-i or -I)
                if (config.interactive or config.always_interactive) and assumptions:
                    edit_result = edit_assumptions_curses(
                        assumptions, context=f"{ticket_id}: {title}"
                    )
                    if edit_result is None:
                        warn("User quit")
                        sys.exit(1)
                    assumptions = edit_result.assumptions
                    if edit_result.action == "replan":
                        prior_assumptions = assumptions
                        log("Re-planning with edited assumptions...")
                        continue
                    success("Assumptions confirmed")
                break

            # Copy planning assumptions to accumulated list
            all_assumptions.extend(assumptions)

            # Create initial comment with plan
            if branch_name and issue_uuid and plan_steps:
                current_step = plan_steps[0]["id"] if plan_steps else None
                comment_id = save_state(
                    issue_uuid=issue_uuid,
                    branch_name=branch_name,
                    iteration=0,
                    current_step=current_step,
                    plan_steps=plan_steps,
                    log_entry="Plan created",
                    assumptions=assumptions,
                    exploration=exploration,
                )
                log_entries.append(f"{time.strftime('%H:%M', time.localtime())} Plan created")
                comment_fragment = f"#comment-{comment_id[:8]}" if comment_id else ""
                comment_url = f"{issue_url}{comment_fragment}"
                plan_summary = ", ".join(s["description"][:30] for s in plan_steps[:3])
                link = hyperlink(comment_url, "Linear")
                success_with_conclusion(f"Plan saved to {link}", plan_summary, raw=True)

        # If skip_plan or no plan generated, fall back to subtasks as steps
        if not plan_steps and subtasks:
            sorted_subtasks = sort_by_dependencies(subtasks)
            plan_steps = [
                {"id": i + 1, "description": s["title"], "done": False, "ticket": s["id"]}
                for i, s in enumerate(sorted_subtasks)
            ]
            log(f"Using {len(plan_steps)} subtasks as plan steps")

        # Dry run: show status and exit
        if config.dry_run:
            show_dry_run_status(ticket_id, ticket, plan_steps, current_step, state_iteration)

        # Check if already done
        incomplete_steps = [s for s in plan_steps if not s.get("done")]
        if plan_steps and not incomplete_steps:
            total_elapsed = fmt_duration(time.time() - total_start)
            log(f"All plan steps complete, skipping work ({total_elapsed})")
            continue  # Move to next ticket

        # Build WorkContext and run state machine
        ctx = WorkContext(
            ticket_id=ticket_id,
            title=title,
            description=description,
            issue_uuid=issue_uuid,
            issue_url=issue_url,
            branch_name=branch_name or "",
            subtasks=subtasks,
            plan_steps=plan_steps,
            all_assumptions=all_assumptions,
            assumptions=assumptions,
            exploration=exploration,
            state_iteration=state_iteration,
            loop_iter=0,
            iter_start=0.0,
            total_start=total_start,
            current_step=current_step,
            step_desc=None,
            commit_ticket=ticket_id,
            work_result=None,
            last_test_error=last_test_error,
            last_review_issues=last_review_issues,
            last_completion_issues=None,
            iter_state={},
            tests_passed=True,
            step_done=False,
            review_status="skipped",
            comment_id=comment_id,
            log_entries=log_entries,
            config=config,
        )

        ticket_success = process_ticket_work(ctx)

        if ticket_success and num_tickets > 1:
            ticket_elapsed = fmt_duration(time.time() - total_start)
            ticket_tokens = fmt_tokens(token_tracker.total.total)
            ticket_cost = fmt_cost(token_tracker.total.cost_usd)
            success_with_conclusion(
                f"Ticket {ticket_idx}/{num_tickets} complete ({ticket_id}) ({ticket_elapsed}) | {ticket_tokens} tokens ({ticket_cost})",
                get_diff_summary(),
            )

        if not ticket_success:
            failed_tickets.append(ticket_id)

    # Submit entire stack if spice + push + multi-ticket + no failures
    if config.spice and config.push and num_tickets > 1 and not failed_tickets:
        log("Submitting stack via git-spice...")
        stack_result = subprocess.run(["gs", "stack", "submit"], capture_output=True, text=True)
        if stack_result.returncode != 0:
            error(f"gs stack submit failed: {stack_result.stderr}")
        else:
            success("Stack submitted")

    # Report results
    if failed_tickets:
        if len(failed_tickets) < num_tickets:
            # Partial success
            warn(
                f"Completed {num_tickets - len(failed_tickets)}/{num_tickets} tickets. Failed: {', '.join(failed_tickets)}"
            )
        else:
            error(f"All tickets failed: {', '.join(failed_tickets)}")
        sys.exit(1)
    elif num_tickets > 1:
        total_elapsed = fmt_duration(time.time() - total_start)
        total_tokens = fmt_tokens(token_tracker.total.total)
        total_cost = fmt_cost(token_tracker.total.cost_usd)
        success(
            f"All {num_tickets} tickets completed! ({total_elapsed}) | {total_tokens} tokens ({total_cost})"
        )


if __name__ == "__main__":
    main()
