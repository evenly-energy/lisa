"""Verification phases: test, review, and fix."""

import fnmatch
import json
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from lisa.clients.claude import claude, work_claude
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.git.commit import get_changed_files
from lisa.models.core import Assumption
from lisa.models.results import TestFailure, VerifyResult
from lisa.models.state import RunConfig
from lisa.phases.constants import (
    DEFAULT_TEST_TIMEOUT,
    EFFORT_LIGHTWEIGHT,
    EFFORT_REVIEW,
    MAX_FIX_ATTEMPTS,
    MAX_ISSUE_REPEATS,
    resolve_effort,
)
from lisa.ui.output import log, success_with_conclusion, warn, warn_with_conclusion
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import debug_log


def run_preflight() -> bool:
    """Run all test and format commands unconditionally. Returns True if all pass."""
    prompts = get_prompts()

    test_commands = prompts.get("test", {}).get("commands", [])
    format_commands = prompts.get("format", {}).get("commands", [])
    all_commands = [(c, DEFAULT_TEST_TIMEOUT) for c in test_commands] + [
        (c, 120) for c in format_commands
    ]

    if not all_commands:
        log("Preflight: no commands configured")
        return True

    for cmd, timeout in all_commands:
        cmd_name = cmd["name"]
        run_cmd = cmd["run"]
        log(f"Preflight: {cmd_name}...")

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
            warn(f"Preflight FAIL: {cmd_name} timed out after {timeout}s")
            return False

        if result.returncode != 0:
            warn(f"Preflight FAIL: {cmd_name}")
            # Print last 3000 chars of output for context
            output = result.stdout[-3000:] if result.stdout else "(no output)"
            print(output)
            return False

        success_with_conclusion(f"Preflight PASS: {cmd_name}", "", raw=True)

    return True


def matches_pattern(filepath: str, pattern: str) -> bool:
    """Check if filepath matches a glob pattern."""
    return fnmatch.fnmatch(filepath, pattern)


def detect_file_categories(changed: list[str], prompts: dict) -> dict[str, bool]:
    """Detect which file categories are present in changed files.

    Returns dict like {"backend": True, "frontend": False}
    """
    config = prompts.get("config", {})
    path_patterns = config.get("path_patterns", {"frontend": "frontend/**", "backend": "**"})
    frontend_extensions = config.get("frontend_extensions", [".ts", ".tsx", ".js", ".jsx"])

    categories = {}

    # Check frontend first (more specific)
    frontend_pattern = path_patterns.get("frontend", "frontend/**")
    categories["frontend"] = any(
        matches_pattern(f, frontend_pattern) and any(f.endswith(ext) for ext in frontend_extensions)
        for f in changed
    )

    # Backend is anything not matching frontend pattern
    categories["backend"] = any(not matches_pattern(f, frontend_pattern) for f in changed)

    return categories


def run_format_phase(debug: bool = False) -> bool:
    """Run format commands before commit. Returns True on success."""
    prompts = get_prompts()

    # Get format config
    format_config = prompts.get("format", {})
    commands = format_config.get("commands", [])
    if not commands:
        return True

    # Detect file categories
    changed = get_changed_files()
    if not changed:
        return True

    categories = detect_file_categories(changed, prompts)

    ran_any = False
    for cmd in commands:
        condition = cmd.get("condition", "always")
        if condition != "always" and not categories.get(condition, False):
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
    config = prompts.get("config", {})

    timer = LiveTimer("Testing...", total_start)
    timer.start()

    # Determine what changed using configurable patterns
    changed = get_changed_files()
    categories = detect_file_categories(changed, prompts)

    # Run configured test commands
    commands = prompts["test"].get("commands", [])
    failure: Optional[TestFailure] = None
    ran_commands = []

    # Get test filter config
    filter_templates = config.get("test_filter_templates", {})
    filter_format = config.get("test_filter_format", '--tests "*{test_name}"')

    for cmd in commands:
        condition = cmd.get("condition", "always")
        if condition != "always" and not categories.get(condition, False):
            continue

        cmd_name = cmd["name"]
        run_cmd = cmd["run"]

        # Optimization: on retry, only run failing tests if template exists
        if failed_tests:
            for base_cmd, template in filter_templates.items():
                if base_cmd in run_cmd:
                    test_filters = " ".join(filter_format.format(test_name=t) for t in failed_tests)
                    run_cmd = template.format(test_filters=test_filters)
                    cmd_name = f"{cmd_name} ({len(failed_tests)} failing)"
                    break

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
                output=output,
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
            failure_log.write_text(f"=== {cmd_name} failure ===\n\n{output}\n")

            failure = TestFailure(
                command_name=cmd_name,
                output=output,
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
                success_with_conclusion("Review APPROVED", summary)
            else:
                warn_with_conclusion("Review NEEDS_FIXES", summary)
            return {
                "approved": approved,
                "findings": result.get("findings", []),
                "summary": summary,
            }
    except json.JSONDecodeError:
        warn("Review: JSON parse failed, treating as NEEDS_FIXES")
        return {"approved": False, "findings": [], "summary": "review output unparseable"}


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
        return result
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
    """Run Kover coverage verification. Returns (passed, error_output)."""
    prompts = get_prompts()

    timer = LiveTimer("Coverage check...", total_start)
    timer.start()

    cmd = prompts["coverage_fix"]["run"]
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

    from lisa.ui.output import GRAY, NC, success

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
