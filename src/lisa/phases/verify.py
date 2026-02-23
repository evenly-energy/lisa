"""Verification phases: test, review, and fix."""

import fnmatch
import json
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from lisa.clients.claude import claude, work_claude
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.config.settings import get_config
from lisa.constants import (
    DEFAULT_TEST_TIMEOUT,
    EFFORT_LIGHTWEIGHT,
    EFFORT_REVIEW,
    MAX_FIX_ATTEMPTS,
    MAX_ISSUE_REPEATS,
    resolve_effort,
)
from lisa.git.commit import get_changed_files
from lisa.models.core import Assumption
from lisa.models.results import TestFailure, VerifyResult
from lisa.models.state import RunConfig
from lisa.ui.output import (
    GRAY,
    NC,
    log,
    success,
    success_with_conclusion,
    warn,
    warn_with_conclusion,
)
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import debug_log


def _expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^}]+)\}", pattern)
    if not m:
        return [pattern]
    prefix, suffix = pattern[: m.start()], pattern[m.end() :]
    return [prefix + alt + suffix for alt in m.group(1).split(",")]


def should_run_command(cmd: dict, changed_files: list[str]) -> bool:
    """Check if command should run based on its paths globs vs changed files.

    No paths = always run. Otherwise, run if any changed file matches any glob.
    """
    paths = cmd.get("paths", [])
    if not paths:
        return True
    expanded = [p for pattern in paths for p in _expand_braces(pattern)]
    return any(fnmatch.fnmatch(f, p) for f in changed_files for p in expanded)


def _run_preflight_command(cmd: dict, timeout: int) -> tuple[str, bool, str]:
    """Run a single preflight command. Returns (name, passed, output)."""
    cmd_name = cmd["name"]
    run_cmd = cmd["run"]

    try:
        result = subprocess.run(
            run_cmd,
            shell=True,  # nosemgrep: subprocess-shell-true
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return cmd_name, False, f"timed out after {timeout}s"

    if result.returncode != 0:
        output = result.stdout[-3000:] if result.stdout else "(no output)"
        return cmd_name, False, output

    return cmd_name, True, ""


def run_setup() -> bool:
    """Run setup commands serially after worktree creation. Returns True if all pass."""
    config = get_config()
    commands = config.get("setup", [])
    if not commands:
        return True
    log(f"Setup: running {len(commands)} commands...")
    for cmd in commands:
        cmd_name = cmd["name"]
        run_cmd = cmd["run"]
        log(f"Setup: {cmd_name}...")
        try:
            result = subprocess.run(
                run_cmd,
                shell=True,  # nosemgrep: subprocess-shell-true
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            warn(f"Setup FAIL: {cmd_name} timed out")
            return False
        if result.returncode != 0:
            warn(f"Setup FAIL: {cmd_name}")
            print(result.stdout[-3000:] if result.stdout else "(no output)")
            return False
        success(f"Setup PASS: {cmd_name}")
    return True


def run_preflight() -> bool:
    """Run test commands marked for preflight in parallel. Returns True if all pass."""
    config = get_config()

    test_commands = config.get("tests", [])
    preflight_commands = [
        (c, DEFAULT_TEST_TIMEOUT) for c in test_commands if c.get("preflight", True)
    ]

    if not preflight_commands:
        log("Preflight: no commands configured")
        return True

    log(f"Preflight: running {len(preflight_commands)} commands...")

    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=len(preflight_commands)) as executor:
        futures = {
            executor.submit(_run_preflight_command, cmd, timeout): cmd["name"]
            for cmd, timeout in preflight_commands
        }
        for future in as_completed(futures):
            name, passed, output = future.result()
            if passed:
                success_with_conclusion(f"Preflight PASS: {name}", "", raw=True)
            else:
                failures.append((name, output))

    for name, output in failures:
        warn(f"Preflight FAIL: {name}")
        if output:
            print(output)

    return len(failures) == 0


def run_format_phase(debug: bool = False) -> bool:
    """Run format commands before commit. Returns True on success."""
    config = get_config()

    commands = config.get("format", [])
    if not commands:
        return True

    changed = get_changed_files()
    if not changed:
        return True

    ran_any = False
    for cmd in commands:
        if not should_run_command(cmd, changed):
            continue

        cmd_name = cmd["name"]
        run_cmd = cmd["run"]
        ran_any = True

        debug_log(debug, f"Running format: {cmd_name}", run_cmd)

        try:
            result = subprocess.run(
                run_cmd,
                shell=True,  # nosemgrep: subprocess-shell-true
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                debug_log(debug, f"Format {cmd_name} failed", result.stdout[-2000:])
                return False
        except subprocess.TimeoutExpired:
            debug_log(debug, f"Format {cmd_name} timed out", "")
            return False

    if ran_any:
        debug_log(debug, "Format phase complete", "")

    return True


def run_test_phase(
    task_title: str,
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    failed_tests: Optional[list[str]] = None,
    debug: bool = False,
) -> Optional[TestFailure]:
    """Run tests directly. Returns None on success, TestFailure on failure.

    Args:
        failed_tests: If provided, only run these test classes (for faster retries)
    """
    prompts = get_prompts()
    schemas = get_schemas()
    cfg = get_config()

    timer = LiveTimer("Testing...", total_start)
    timer.start()

    changed = get_changed_files()

    commands = cfg.get("tests", [])
    failure: Optional[TestFailure] = None
    ran_commands = []

    for cmd in commands:
        if not should_run_command(cmd, changed):
            continue

        cmd_name = cmd["name"]
        run_cmd = cmd["run"]

        # On retry, append filter for failing tests if command supports it
        cmd_filter = cmd.get("filter")
        if failed_tests and cmd_filter:
            filters = " ".join(cmd_filter.format(test=t) for t in failed_tests)
            run_cmd = f"{run_cmd} {filters}"
            cmd_name = f"{cmd_name} ({len(failed_tests)} failing)"

        ran_commands.append(cmd_name)
        timer.set_label(f"Running: {cmd_name}...")

        # Safe: commands from static YAML config, test names escaped with shlex.quote()
        try:
            result = subprocess.run(
                run_cmd,
                shell=True,  # nosemgrep: subprocess-shell-true
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=DEFAULT_TEST_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            output = (
                (e.stdout or "")[-5000:]
                if e.stdout
                else f"Test command timed out after {DEFAULT_TEST_TIMEOUT}s"
            )
            failure = TestFailure(
                command_name=cmd_name,
                output=str(output),
                summary=f"Timed out after {DEFAULT_TEST_TIMEOUT}s",
                failed_tests=[],
            )
            break

        if result.returncode != 0:
            full_output = result.stdout[-1500000:]  # Keep up to 1.5M chars for extraction

            # Use structured Haiku extraction
            extract_prompt = prompts["test"]["extract_prompt"].format(output=full_output)
            extracted_json = claude(
                extract_prompt,
                model="haiku",
                allowed_tools="",
                json_schema=schemas["test_extraction"],
            )
            debug_log(debug, "Test extraction output", extracted_json)

            try:
                extraction = json.loads(extracted_json)
                debug_log(debug, "Parsed test extraction", extraction)
                output = extraction["extracted_output"]
                summary = extraction["summary"]
                extracted_tests = extraction["failed_tests"]
            except json.JSONDecodeError:
                output = full_output[:5000]
                summary = ""
                extracted_tests = []

            # Write debug log with extracted output
            failure_log = Path(".lisa/test-failure.log")
            failure_log.parent.mkdir(exist_ok=True)
            output_str = str(output) if isinstance(output, bytes) else output
            failure_log.write_text(f"=== {cmd_name} failure ===\n\n{output_str}\n")

            failure = TestFailure(
                command_name=cmd_name,
                output=output_str,
                summary=summary,
                failed_tests=extracted_tests,
            )
            break  # Stop on first failure

    timer.stop(print_final=False)

    if not failure:
        checks = ", ".join(ran_commands) if ran_commands else "no checks configured"
        success_with_conclusion("Tests PASS", checks, raw=True)
        return None

    warn_with_conclusion(
        f"Tests FAIL ({failure.command_name})", failure.summary or "extraction failed", raw=True
    )
    return failure


def run_review_phase(
    task_title: str,
    task_description: str,
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: Optional[str],
    lightweight: bool = False,
    assumptions: Optional[list[Assumption]] = None,
    debug: bool = False,
) -> dict:
    """Code review. Returns dict with approved, findings, summary.

    Args:
        effort: Effort level for the review (use resolve_effort with appropriate constant).
        lightweight: If True, use fast sanity-check prompt (for loop iterations).
                    If False, use full review prompt (for final review).
        assumptions: List of assumptions to validate (only used in full review mode).

    Returns:
        dict with:
        - approved: bool
        - findings: list of {category, status, detail}
        - summary: str
    """
    prompts = get_prompts()
    schemas = get_schemas()

    if lightweight:
        prompt = prompts["review_light"]["template"].format(task_title=task_title)
        review_model = model
        timer_label = "Quick review..."
        schema_name = "review_light"
    else:
        # Format assumptions section if provided
        assumptions_section = ""
        if assumptions:
            assumptions_text = "\n".join(
                f"- [{a.id}] {a.statement}"
                + (f" (rationale: {a.rationale})" if a.rationale else "")
                for a in assumptions
                if a.selected
            )
            assumptions_section = f"\n## Assumptions Made\n{assumptions_text}\n"

        prompt = prompts["review"]["template"].format(
            task_title=task_title,
            task_description=task_description,
            assumptions_section=assumptions_section,
        )
        review_model = model
        timer_label = "Reviewing..."
        schema_name = "review"

    timer = LiveTimer(timer_label, total_start)
    timer.start()

    output = work_claude(
        prompt, review_model, yolo, fallback_tools, effort, json_schema=schemas[schema_name]
    )
    debug_log(debug, "Review output", output)

    timer.stop(print_final=False)

    try:
        result = json.loads(output)
        debug_log(debug, "Parsed review result", result)
        approved = result.get("approved", False)

        if lightweight:
            # Convert review_light schema to full review format
            issue = result.get("issue")
            summary = "approved" if approved else (issue or "unknown issue")[:100]
            if approved:
                success_with_conclusion("Review APPROVED", summary, raw=True)
            else:
                warn_with_conclusion("Review NEEDS_FIXES", summary, raw=True)
            return {"approved": approved, "findings": [], "summary": summary}
        else:
            # Full review schema already has findings/summary
            summary = result.get("summary") or "review completed"
            if approved:
                success_with_conclusion("Review APPROVED", summary, raw=True)
            else:
                warn_with_conclusion("Review NEEDS_FIXES", summary, raw=True)
            return {
                "approved": approved,
                "findings": result.get("findings", []),
                "summary": summary,
            }
    except json.JSONDecodeError:
        warn("Review: JSON parse failed, treating as NEEDS_FIXES")
        return {"approved": False, "findings": [], "summary": "review output unparseable"}


def try_pr_review_skill(
    ticket_id: str,
    title: str,
    description: str,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: str,
    assumptions: list[Assumption],
    plan_steps: list[dict],
    subtasks: list[dict],
    debug: bool = False,
) -> Optional[dict]:
    """Try to invoke pr-review-toolkit:review-pr skill.

    Returns dict {approved: bool, issues: str|None, summary: str} on success.
    Returns None if skill not available or fails.
    """
    prompts = get_prompts()
    schemas = get_schemas()

    # Format assumptions for template
    assumptions_text = (
        "\n".join(f"- {a.id}: {a.statement}" for a in assumptions if a.selected)
        if assumptions
        else "None"
    )

    # Format plan steps for context
    plan_steps_text = (
        "\n".join(f"{step['id']}. {step['description']}" for step in plan_steps)
        if plan_steps
        else "None"
    )

    # Format subtasks context with full details
    subtasks_context = ""
    if subtasks:
        subtask_lines = ["**Subtasks:**"]
        for st in subtasks:
            # Subtask dict has: {identifier, title, description, ...}
            st_id = st.get("identifier", st.get("id", ""))
            st_title = st.get("title", "")
            st_desc = st.get("description", "")
            subtask_lines.append(f"\n- **{st_id}**: {st_title}")
            if st_desc:
                subtask_lines.append(f"  {st_desc}")
        subtasks_context = "\n".join(subtask_lines)

    # Get commit messages for THIS ticket only (filter by ticket ID in commit message)
    try:
        # Get all commits from current branch
        result = subprocess.run(
            ["git", "log", "main..HEAD", "--oneline", "--no-decorate"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Filter commits that mention this ticket ID
            all_commits = result.stdout.strip().split("\n")
            ticket_commits = [c for c in all_commits if ticket_id in c]

            if ticket_commits:
                commit_messages = "```\n" + "\n".join(ticket_commits) + "\n```"
            else:
                commit_messages = "(No commits for this ticket yet)"
        else:
            commit_messages = "(No commits yet)"
    except Exception:
        commit_messages = "(Could not retrieve commits)"

    # Use final_review template with skill invocation
    prompt = prompts["final_review"]["template"].format(
        ticket_id=ticket_id,
        title=title,
        description=description,
        plan_steps=plan_steps_text,
        assumptions=assumptions_text,
        subtasks_context=subtasks_context,
        commit_messages=commit_messages,
    )

    # Prepend skill invocation instruction
    prompt = f"""Use the pr-review-toolkit:review-pr skill to perform this review.
If skill unavailable, return: {{"skill_available": false}}

{prompt}"""

    try:
        output = work_claude(
            prompt,
            model,
            yolo,
            fallback_tools,
            effort,
            json_schema=schemas["final_review_result"],
        )

        review_result: dict[str, Any] = json.loads(output)
        if not review_result.get("skill_available"):
            return None
        return review_result

    except (subprocess.CalledProcessError, json.JSONDecodeError, Exception) as e:
        debug_log(debug, "PR review skill failed", str(e))
        return None


def run_fix_phase(
    issues: str,
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: Optional[str],
    fix_model: Optional[str] = None,
) -> None:
    """Fix issues from code review.

    Args:
        effort: Effort level for the fix (use resolve_effort with appropriate constant).
        fix_model: Override model for fixes. If None, uses `model` param.
    """
    prompts = get_prompts()
    prompt = prompts["fix"]["template"].format(issues=issues)
    use_model = fix_model or model
    with LiveTimer("Fixing...", total_start, print_final=False):
        work_claude(prompt, use_model, yolo, fallback_tools, effort)
    log("Fixes applied")


def run_test_fix_phase(
    failure: TestFailure,
    step_desc: str,
    task_description: str,
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: Optional[str],
) -> None:
    """Fix test/lint failures. Uses configured model for better reasoning on test failures.

    Args:
        task_description: Full task context for the fix agent.
        model: Model to use for fixes (from config).
        effort: Effort level for the fix (use resolve_effort with appropriate constant).
    """
    prompts = get_prompts()

    # Capture git diff for fix context
    diff_result = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True)
    git_diff = diff_result.stdout[:15000] if diff_result.returncode == 0 else "(no diff available)"
    if len(diff_result.stdout) > 15000:
        git_diff += "\n... (truncated)"

    fix_prompt = prompts["test"].get("fix_prompt", "Fix this error:\n{output}")
    prompt = fix_prompt.format(
        command_name=failure.command_name,
        step_desc=step_desc,
        task_description=task_description,
        git_diff=git_diff,
        output=failure.output,
    )
    with LiveTimer(f"Fixing {failure.command_name}...", total_start, print_final=False):
        work_claude(prompt, model, yolo, fallback_tools, effort)
    log(f"Test fix applied for {failure.command_name}")


def run_completion_check(
    step_id: int,
    step_desc: str,
    step_files: list[dict],
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: str,
    debug: bool = False,
) -> dict:
    """Check if a step's described goal was actually achieved in the code changes.

    Returns dict with {complete: bool, missing: str|null}.
    """
    prompts = get_prompts()
    schemas = get_schemas()

    # Format step files as context
    if step_files:
        lines = []
        for f in step_files:
            op = f["op"].upper()
            parts = []
            if f.get("template"):
                parts.append(f"template: {f['template']}")
            if f.get("detail"):
                parts.append(f"detail: {f['detail']}")
            extra = ", ".join(parts)
            suffix = f" ({extra})" if extra else ""
            lines.append(f"- {op}: {f['path']}{suffix}")
        files_context = "\n".join(lines)
    else:
        files_context = "(no planned files)"

    prompt = prompts["completion_check"]["template"].format(
        step_id=step_id,
        step_desc=step_desc,
        files_context=files_context,
    )

    timer = LiveTimer("Completion check...", total_start, print_final=False)
    timer.start()
    output = work_claude(
        prompt,
        model,
        yolo,
        fallback_tools,
        resolve_effort(EFFORT_LIGHTWEIGHT, effort),
        json_schema=schemas["completion_check"],
    )
    timer.stop(print_final=False)

    debug_log(debug, "Completion check output", output)

    try:
        result = json.loads(output)
        debug_log(debug, "Parsed completion check", result)
        if result.get("complete", False):
            success_with_conclusion("Completion check PASS", "step goal achieved", raw=True)
        else:
            missing = result.get("missing", "unknown")
            warn_with_conclusion(
                "Completion check FAIL", missing[:100] if missing else "unknown", raw=True
            )
        return result  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        warn("Completion check: JSON parse failed, treating as complete")
        return {"complete": True, "missing": None}


def verify_step(
    step_desc: str,
    task_description: str,
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    effort: str,
    step_id: int = 0,
    step_files: Optional[list[dict]] = None,
    debug: bool = False,
) -> VerifyResult:
    """Run test/review/fix cycle with early returns."""
    # Completion check: verify step goal was achieved before running tests
    if step_id and step_desc:
        completion = run_completion_check(
            step_id,
            step_desc,
            step_files or [],
            total_start,
            model,
            yolo,
            fallback_tools,
            effort,
            debug,
        )
        if not completion.get("complete", True):
            return VerifyResult(
                passed=False, completion_issues=[completion.get("missing", "unknown")]
            )

    # Calculate turn limits for this verification cycle
    lightweight_effort = resolve_effort(EFFORT_LIGHTWEIGHT, effort)

    # Test phase with fix loop
    test_failure = run_test_phase(step_desc, total_start, model, yolo, fallback_tools, debug=debug)
    for fix_attempt in range(MAX_FIX_ATTEMPTS):
        if test_failure is None:
            break  # Tests passed
        # Try to fix the test failure and re-test (only failing tests for speed)
        log(f"Test fix attempt {fix_attempt + 1}/{MAX_FIX_ATTEMPTS}")
        run_test_fix_phase(
            test_failure,
            step_desc,
            task_description,
            total_start,
            model,
            yolo,
            fallback_tools,
            lightweight_effort,
        )
        test_failure = run_test_phase(
            step_desc,
            total_start,
            model,
            yolo,
            fallback_tools,
            failed_tests=test_failure.failed_tests or None,
            debug=debug,
        )

    # If tests still fail after fix attempts, return failure
    if test_failure is not None:
        return VerifyResult(passed=False, test_errors=[test_failure.summary])

    # Review + fix loop (lightweight review, early exit on repeated issues)
    review_issues: list[str] = []
    issue_counts: dict[str, int] = {}
    for attempt in range(MAX_FIX_ATTEMPTS):
        # Use lightweight review in loop - fast sanity check
        review_result = run_review_phase(
            step_desc,
            task_description,
            total_start,
            model,
            yolo,
            fallback_tools,
            lightweight_effort,
            lightweight=True,
            debug=debug,
        )

        if review_result["approved"]:
            return VerifyResult(passed=True, fix_attempts=attempt, review_issues=review_issues)

        # Needs fixes - track and check for repeats
        issue = review_result["summary"][:100]
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

        # Only exit after same issue repeats MAX_ISSUE_REPEATS times
        if issue_counts[issue] >= MAX_ISSUE_REPEATS:
            warn(f"Issue repeated {issue_counts[issue]}x, deferring to next iteration")
            return VerifyResult(
                passed=False, review_issues=review_issues + [issue], fix_attempts=attempt + 1
            )
        review_issues.append(issue)

        # Fix review issues in loop
        run_fix_phase(
            review_result["summary"],
            total_start,
            model,
            yolo,
            fallback_tools,
            lightweight_effort,
        )

        # Re-test after fix
        test_failure = run_test_phase(
            step_desc, total_start, model, yolo, fallback_tools, debug=debug
        )
        for test_fix_attempt in range(MAX_FIX_ATTEMPTS):
            if test_failure is None:
                break
            log(f"Post-review test fix attempt {test_fix_attempt + 1}/{MAX_FIX_ATTEMPTS}")
            run_test_fix_phase(
                test_failure,
                step_desc,
                task_description,
                total_start,
                model,
                yolo,
                fallback_tools,
                lightweight_effort,
            )
            test_failure = run_test_phase(
                step_desc,
                total_start,
                model,
                yolo,
                fallback_tools,
                failed_tests=test_failure.failed_tests or None,
                debug=debug,
            )

        if test_failure is not None:
            return VerifyResult(
                passed=False,
                test_errors=[test_failure.summary],
                fix_attempts=attempt + 1,
                review_issues=review_issues,
            )

    # Max fix attempts reached
    return VerifyResult(passed=False, review_issues=review_issues, fix_attempts=MAX_FIX_ATTEMPTS)


def run_coverage_gate(total_start: float, debug: bool = False) -> tuple[bool, str]:
    """Run coverage verification. Returns (passed, error_output)."""
    cfg = get_config()
    coverage_cmd = cfg.get("coverage", {}).get("run", "")
    if not coverage_cmd:
        return True, ""

    timer = LiveTimer("Coverage check...", total_start)
    timer.start()

    cmd = coverage_cmd
    try:
        result = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        timer.stop(print_final=False)
        warn("Coverage check timed out")
        return False, "Timeout after 300s"

    timer.stop(print_final=False)
    output = result.stdout + result.stderr
    debug_log(debug, "Coverage gate output", output)

    if result.returncode == 0:
        success("Coverage gate PASS (80%+ achieved)")
        return True, ""
    else:
        warn("Coverage gate FAIL - below 80%")
        for line in output.split("\n"):
            if "coverage" in line.lower() or "kover" in line.lower():
                print(f"  {GRAY}{line}{NC}")
        return False, output


def run_coverage_fix_phase(
    changed_files: list[str],
    error_output: str,
    total_start: float,
    config: RunConfig,
) -> None:
    """Prompt Claude to add tests to reach coverage threshold."""
    prompts = get_prompts()

    fix_prompt = prompts["coverage_fix"]["template"].format(
        changed_files="\n".join(changed_files) if changed_files else "(no changed files)",
        error_output=error_output[:3000] if error_output else "(no output)",
    )
    timer = LiveTimer("Adding tests for coverage...", total_start)
    timer.start()
    work_claude(
        fix_prompt,
        config.model,
        config.yolo,
        config.fallback_tools,
        resolve_effort(EFFORT_REVIEW, config.effort),
    )
    timer.stop(print_final=False)
