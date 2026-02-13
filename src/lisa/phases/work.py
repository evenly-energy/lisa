"""Work loop state machine for executing steps."""

import json
import os
import sys
import time
from typing import Callable, Optional

from lisa.clients.claude import token_tracker, work_claude
from lisa.clients.linear import fetch_subtask_details
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.git.commit import get_changed_files, get_diff_summary, git_commit, summarize_for_commit
from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import WorkContext, WorkState
from lisa.phases.conclusion import (
    format_conclusion_markdown,
    print_conclusion,
    run_conclusion_phase,
    save_conclusion_to_linear,
)
from lisa.phases.constants import MAX_FIX_ATTEMPTS, TURNS_QUICK, TURNS_WORK, calc_turns
from lisa.phases.verify import (
    detect_file_categories,
    run_coverage_fix_phase,
    run_coverage_gate,
    run_format_phase,
    run_review_phase,
    run_test_phase,
    verify_step,
)
from lisa.state.comment import save_state
from lisa.state.git import fetch_git_state
from lisa.ui.output import (
    BLUE,
    GREEN,
    NC,
    RED,
    YELLOW,
    error,
    hyperlink,
    log,
    success,
    success_with_conclusion,
    warn,
)
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import debug_log
from lisa.utils.formatting import fmt_cost, fmt_duration, fmt_tokens


def format_exploration_context(
    exploration: Optional[ExplorationFindings], assumptions: list[Assumption]
) -> str:
    """Format exploration findings and planning assumptions as context for work prompt.

    This helps the work phase:
    1. Know what patterns/templates to use (exploration)
    2. Follow already-made decisions (assumptions)
    """
    if not exploration and not assumptions:
        return ""

    lines = []

    if exploration:
        lines.append("## Exploration Context")

        if exploration.patterns:
            patterns_str = " | ".join(exploration.patterns[:5])
            lines.append(f"**Patterns to follow:** {patterns_str}")

        if exploration.relevant_modules:
            modules_str = ", ".join(exploration.relevant_modules[:5])
            lines.append(f"**Modules involved:** {modules_str}")

        if exploration.similar_implementations:
            refs = []
            for impl in exploration.similar_implementations[:3]:
                file_path = impl.get("file", "")
                relevance = impl.get("relevance", "")
                if file_path:
                    refs.append(f"{file_path} ({relevance[:40]})" if relevance else file_path)
            if refs:
                lines.append(f"**Reference files:** {', '.join(refs)}")

        lines.append("")

    # Include planning decisions (P.x)
    planning_assumptions = [a for a in assumptions if a.id.startswith("P.")]
    if planning_assumptions:
        lines.append("## Planning Decisions (follow these)")
        for a in planning_assumptions:
            if a.selected:
                rationale = f" ({a.rationale[:50]})" if a.rationale else ""
                lines.append(f"- {a.id}: {a.statement}{rationale}")
        lines.append("")

    return "\n".join(lines) if lines else ""


def format_step_files(files: list[dict]) -> str:
    """Format step files as context for work prompt."""
    if not files:
        return ""
    lines = ["## Files for This Step"]
    for f in files:
        op = f["op"].upper()
        parts = []
        if f.get("template"):
            parts.append(f"template: {f['template']}")
        if f.get("detail"):
            parts.append(f"detail: {f['detail']}")
        extra = ", ".join(parts)
        suffix = f" ({extra})" if extra else ""
        lines.append(f"- {op}: {f['path']}{suffix}")
    lines.append("")
    return "\n".join(lines)


def log_step_files(files: list[dict]) -> None:
    """Log step files with colored operation types."""
    if not files:
        return
    OP_COLORS = {"create": GREEN, "modify": YELLOW, "delete": RED}
    for f in files:
        op = f["op"]
        color = OP_COLORS.get(op, "")
        filename = os.path.basename(f["path"])
        detail = f.get("detail", "")
        suffix = f" {GRAY}({detail}){NC}" if detail else ""
        log(f"  {color}{op.upper()}{NC} {filename}{suffix}")


from lisa.ui.output import GRAY


def handle_select_step(ctx: WorkContext) -> WorkState:
    """Check if all steps done, select next step."""
    incomplete = [s for s in ctx.plan_steps if not s.get("done")]
    if not incomplete:
        return WorkState.ALL_DONE

    current_step_obj = incomplete[0]
    ctx.current_step = current_step_obj["id"]
    ctx.step_desc = current_step_obj["description"]
    ctx.commit_ticket = current_step_obj.get("ticket", ctx.ticket_id)

    log(f"Loaded step {ctx.current_step} ({ctx.commit_ticket}): {YELLOW}{ctx.step_desc}{NC}")

    step_files = current_step_obj.get("files", [])
    if step_files:
        log_step_files(step_files)

    if ctx.last_test_error:
        warn(f"Fixing: {ctx.last_test_error[:70]}{'...' if len(ctx.last_test_error) > 70 else ''}")
    elif ctx.last_completion_issues:
        warn(
            f"Incomplete: {ctx.last_completion_issues[:70]}{'...' if len(ctx.last_completion_issues) > 70 else ''}"
        )
    elif ctx.last_review_issues:
        warn(
            f"Fixing: {ctx.last_review_issues[:70]}{'...' if len(ctx.last_review_issues) > 70 else ''}"
        )
    log(f"Remaining: {len(incomplete)} steps")

    return WorkState.EXECUTE_WORK


def handle_execute_work(ctx: WorkContext) -> WorkState:
    """Build prompt and call Claude."""
    prompts = get_prompts()
    schemas = get_schemas()

    # Fetch subtask context if step is associated with a different ticket
    subtask_context = ""
    if ctx.commit_ticket and ctx.commit_ticket != ctx.ticket_id:
        subtask = fetch_subtask_details(ctx.commit_ticket)
        if subtask:
            subtask_context = f"""
## Subtask: {subtask["id"]} - {subtask["title"]}

{subtask["description"] or "(no description)"}

Focus on implementing THIS subtask's scope, not the entire ticket.
"""

    # Build prior context including test/review failures
    prior_context = ""

    # CRITICAL: Include previous test failure so Claude knows to fix it
    if ctx.last_test_error:
        prior_context += f"""
## ⚠️ PREVIOUS TEST FAILURE - FIX THIS FIRST

The previous iteration completed the code but **tests failed**:
```
{ctx.last_test_error}
```
You MUST fix this test failure before marking the step as done.
Do NOT just re-implement the same code. Investigate the error and fix it.

"""

    # Include completion check failure so Claude knows what's missing
    if ctx.last_completion_issues:
        prior_context += f"""
## ⚠️ STEP INCOMPLETE - FINISH THIS WORK

The completion check found the step's goal was NOT fully achieved:
```
{ctx.last_completion_issues}
```
Complete the missing work, then signal step_done.

"""

    # Include previous review issues if fix attempts were exhausted
    if ctx.last_review_issues:
        prior_context += f"""
## ⚠️ PREVIOUS REVIEW ISSUES - ADDRESS THESE

The previous iteration's code review found issues that weren't fully resolved:
```
{ctx.last_review_issues}
```
Address these review issues before marking the step as done.

"""

    if ctx.branch_name:
        git_state = fetch_git_state(ctx.branch_name)
        prior_iterations = git_state.get("iterations", [])
        if prior_iterations:
            prior_iterations.sort(key=lambda x: x.get("iteration", 0), reverse=True)
            prior_context += "\n## Prior Iteration History\n"
            for it in prior_iterations[:3]:
                iter_num = it.get("iteration", "?")
                files = ", ".join(it.get("files", [])) or "none"
                errors = it.get("errors", "none")
                prior_context += f"- Iter {iter_num}: {files} | errors: {errors}\n"

    # Build plan checklist for prompt
    plan_checklist = "\n".join(
        f"- [{'x' if s.get('done') else ' '}] **{s['id']}** ({s.get('ticket', '')}): {s['description']}"
        + (" ← YOU ARE HERE" if s["id"] == ctx.current_step else "")
        for s in ctx.plan_steps
    )

    # Build exploration context for work prompt
    exploration_context = format_exploration_context(ctx.exploration, ctx.all_assumptions)

    iteration_context = ""
    if ctx.iteration > 1:
        iteration_context = f"\n## Iteration {ctx.iteration}\nThis is iteration {ctx.iteration} on step {ctx.current_step}. If code changes are complete, signal step_done.\n"

    # Get files for current step
    current_step_obj = next((s for s in ctx.plan_steps if s["id"] == ctx.current_step), None)
    step_files = current_step_obj.get("files", []) if current_step_obj else []
    files_context = format_step_files(step_files)

    work_prompt = prompts["work"]["template"].format(
        ticket_id=ctx.ticket_id,
        title=ctx.title,
        description=ctx.description,
        exploration_context=exploration_context,
        files_context=files_context,
        subtask_context=subtask_context,
        prior_context=prior_context,
        iteration_context=iteration_context,
        plan_checklist=plan_checklist,
        current_step=ctx.current_step,
        step_desc=ctx.step_desc,
    )

    # Build context conclusion for timer
    if ctx.last_test_error:
        conclusion = f"Fixing tests in step {ctx.current_step}"
    elif ctx.last_review_issues:
        conclusion = f"Fixing review in step {ctx.current_step}"
    else:
        conclusion = f"Implementing step {ctx.current_step}"

    # Capture files changed before work starts
    ctx.iter_state["files_before"] = set(get_changed_files())

    timer = LiveTimer("Working...", ctx.total_start, print_final=False, conclusion=conclusion)
    timer.start()
    output = work_claude(
        work_prompt,
        ctx.config.model,
        ctx.config.yolo,
        ctx.config.fallback_tools,
        calc_turns(ctx.config.max_turns, TURNS_WORK),
        json_schema=schemas["work"],
    )
    ctx.iter_state["step_elapsed"] = timer.get_elapsed()
    timer.stop(print_final=False)

    # Debug log raw output
    debug_log(ctx.config, f"Work output (step {ctx.current_step})", output)

    # Parse structured JSON output
    try:
        ctx.work_result = json.loads(output)
        debug_log(ctx.config, f"Parsed work result (step {ctx.current_step})", ctx.work_result)
    except json.JSONDecodeError as e:
        error(f"Failed to parse work output as JSON: {e}")
        debug_log(ctx.config, f"JSON parse error (step {ctx.current_step})", str(e))
        debug_log(ctx.config, "Raw output that failed to parse", output[:2000])
        sys.exit(1)

    return WorkState.HANDLE_ASSUMPTIONS


def handle_assumptions(ctx: WorkContext) -> WorkState:
    """Extract and optionally edit assumptions."""
    work_assumptions = [
        Assumption(
            id=str(a["id"]),
            selected=a["selected"],
            statement=a["statement"],
            rationale=a.get("rationale", ""),
        )
        for a in ctx.work_result.get("assumptions", [])
    ]
    # Re-label work assumptions with iteration.N format
    for i, a in enumerate(work_assumptions, 1):
        a.id = f"{ctx.iteration}.{i}"

    if work_assumptions:
        if ctx.config.always_interactive:
            from lisa.ui.assumptions import edit_assumptions_curses

            # Let user edit assumptions with curses UI
            edited = edit_assumptions_curses(
                work_assumptions,
                context=f"{ctx.ticket_id} Step {ctx.current_step}: {ctx.step_desc}",
            )
            if edited is None:
                warn("User quit")
                sys.exit(1)
            work_assumptions = edited.assumptions
            success("Assumptions confirmed")
        else:
            display_assumptions(work_assumptions)
        # Accumulate work assumptions for commit and Linear
        ctx.assumptions.extend(work_assumptions)
        ctx.all_assumptions.extend(work_assumptions)

    return WorkState.CHECK_COMPLETION


def display_assumptions(assumptions: list[Assumption]) -> None:
    """Display assumptions in terminal."""
    if not assumptions:
        return
    print(f"\n{BLUE}📋 Assumptions made:{NC}")
    for a in assumptions:
        marker = "x" if a.selected else " "
        print(f"  [{marker}] {a.id}. {a.statement}")
        if a.rationale:
            print(f"       {GRAY}→ {a.rationale}{NC}")


def handle_check_completion(ctx: WorkContext) -> WorkState:
    """Evaluate work result: blocked, in-progress, or done."""
    ctx.step_done = False
    ctx.tests_passed = True
    ctx.review_status = "skipped"

    # Check for blocked status - record as manual action instead of exiting
    if ctx.work_result.get("blocked"):
        blocked_reason = ctx.work_result["blocked"]
        warn(f"Blocked: {blocked_reason}")

        # Record as manual action instead of exiting
        manual_action = Assumption(
            id=str(len(ctx.assumptions) + 1),
            selected=False,
            statement=f"MANUAL: {blocked_reason}",
            rationale="Blocked - requires manual action",
        )
        ctx.assumptions.append(manual_action)
        ctx.all_assumptions.append(manual_action)
        log("Recorded for manual action - continuing")

    # Check for step completion
    completed_step = ctx.work_result.get("step_done")
    if completed_step is None:
        log("Step in progress (will continue next iteration)")
        return WorkState.COMMIT_CHANGES
    elif completed_step != ctx.current_step:
        warn(f"Completed step {completed_step} but expected {ctx.current_step}")
        return WorkState.COMMIT_CHANGES
    else:
        # Step completed
        step_elapsed = ctx.iter_state.get("step_elapsed", "?")
        success_with_conclusion(
            f"Step {ctx.current_step} done ({step_elapsed})", get_diff_summary()
        )
        ctx.step_done = True
        return WorkState.VERIFY_STEP


def handle_verify_step(ctx: WorkContext) -> WorkState:
    """Run tests and review."""
    if ctx.config.skip_verify:
        ctx.tests_passed = True
        ctx.last_test_error = None
        ctx.last_review_issues = None
        ctx.last_completion_issues = None
        ctx.verify_attempts = 0
        # Mark step complete
        for step in ctx.plan_steps:
            if step["id"] == ctx.current_step:
                step["done"] = True
                break
        return WorkState.COMMIT_CHANGES

    # Get files for current step
    current_step_obj = next((s for s in ctx.plan_steps if s["id"] == ctx.current_step), None)
    step_files = current_step_obj.get("files", []) if current_step_obj else []

    verify = verify_step(
        ctx.step_desc,
        ctx.description,
        ctx.total_start,
        ctx.config.model,
        ctx.config.yolo,
        ctx.config.fallback_tools,
        ctx.config.max_turns,
        step_id=ctx.current_step,
        step_files=step_files,
        debug=ctx.config.debug,
    )
    ctx.tests_passed = verify.passed
    ctx.iter_state["test_errors"] = verify.test_errors
    ctx.iter_state["review_issues"] = verify.review_issues
    ctx.iter_state["fixes_applied"] = [f"fix attempt {i + 1}" for i in range(verify.fix_attempts)]

    if verify.passed:
        ctx.review_status = "APPROVED"
        ctx.last_test_error = None
        ctx.last_review_issues = None
        ctx.last_completion_issues = None
        ctx.verify_attempts = 0
        # Mark step complete
        for step in ctx.plan_steps:
            if step["id"] == ctx.current_step:
                step["done"] = True
                break
        return WorkState.COMMIT_CHANGES

    # Verification failed - check retry budget
    ctx.verify_attempts += 1
    if ctx.verify_attempts < ctx.max_verify_attempts:
        # Loop back to work with failure context
        if verify.completion_issues:
            ctx.last_completion_issues = "; ".join(verify.completion_issues)
            ctx.last_test_error = None
            ctx.last_review_issues = None
            log(f"Verify retry {ctx.verify_attempts}/{ctx.max_verify_attempts} (incomplete)")
        elif verify.test_errors:
            ctx.last_test_error = verify.test_errors[0]
            ctx.last_review_issues = None
            ctx.last_completion_issues = None
            log(f"Verify retry {ctx.verify_attempts}/{ctx.max_verify_attempts} (test failure)")
        else:
            ctx.last_test_error = None
            ctx.last_review_issues = (
                "; ".join(verify.review_issues) if verify.review_issues else None
            )
            ctx.last_completion_issues = None
            log(f"Verify retry {ctx.verify_attempts}/{ctx.max_verify_attempts} (review issues)")
        return WorkState.EXECUTE_WORK  # Retry from work phase

    # Exhausted retries - set error context and commit with [FAIL]
    if verify.completion_issues:
        ctx.review_status = "skipped (incomplete)"
        ctx.last_completion_issues = "; ".join(verify.completion_issues)
        ctx.last_test_error = None
        ctx.last_review_issues = None
    elif verify.test_errors:
        ctx.review_status = "skipped (tests failed)"
        ctx.last_test_error = verify.test_errors[0]
        ctx.last_review_issues = None
        ctx.last_completion_issues = None
    else:
        ctx.review_status = f"NEEDS_FIXES ({verify.fix_attempts} attempts)"
        ctx.last_test_error = None
        ctx.last_review_issues = "; ".join(verify.review_issues) if verify.review_issues else None
        ctx.last_completion_issues = None

    return WorkState.COMMIT_CHANGES


def handle_commit_changes(ctx: WorkContext) -> WorkState:
    """Git commit if changes exist."""
    files_before = ctx.iter_state.get("files_before", set())
    files_after = set(get_changed_files())
    files_this_step = list(files_after - files_before)
    ctx.iter_state["files_changed"] = files_this_step

    if files_this_step:
        # Run formatters before commit to avoid pre-commit hook failures
        run_format_phase(debug=ctx.config.debug)
        # Re-get changed files after formatting (formatters may have modified files)
        files_after_format = set(get_changed_files())
        files_this_step = list(files_after_format - files_before)

        fail_marker = "[FAIL] " if not ctx.tests_passed else ""
        short_desc = summarize_for_commit(ctx.step_desc)
        commit_title = f"{fail_marker}step {ctx.current_step}: {short_desc}"
        commit_body = ctx.step_desc
        commit_assumptions = ctx.assumptions if ctx.assumptions else None
        if not git_commit(
            ctx.commit_ticket,
            ctx.iteration,
            commit_title,
            task_body=commit_body,
            iter_state=ctx.iter_state,
            push=ctx.config.push,
            files_to_add=files_this_step,
            assumptions=commit_assumptions,
        ):
            warn("Commit failed - changes not committed")
        elif not ctx.tests_passed:
            warn("Committed with [FAIL] marker - tests did not pass")
        # Clear assumptions after commit
        ctx.assumptions = []
    else:
        log("No new files changed in this step")

    # Reset verify attempts after commit
    ctx.verify_attempts = 0

    return WorkState.SAVE_STATE


def handle_save_state(ctx: WorkContext) -> WorkState:
    """Persist to Linear."""
    # Build log entry
    log_entry = f"Iter {ctx.iteration}"
    if ctx.step_done:
        log_entry += (
            f" - step {ctx.current_step} {'✓' if ctx.tests_passed else '✗'} ({ctx.review_status})"
        )
    else:
        log_entry += f" - step {ctx.current_step} in progress"

    if ctx.branch_name and ctx.issue_uuid:
        with LiveTimer("Saving state...", ctx.total_start, print_final=False):
            remaining_steps = [s for s in ctx.plan_steps if not s.get("done")]
            next_step = remaining_steps[0]["id"] if remaining_steps else None
            new_comment_id = save_state(
                issue_uuid=ctx.issue_uuid,
                branch_name=ctx.branch_name,
                iteration=ctx.iteration,
                current_step=next_step,
                plan_steps=ctx.plan_steps,
                comment_id=ctx.comment_id,
                log_entry=log_entry,
                existing_log=ctx.log_entries,
                assumptions=ctx.all_assumptions if ctx.all_assumptions else None,
                exploration=ctx.exploration,
            )
            if new_comment_id:
                ctx.comment_id = new_comment_id
                ctx.log_entries.insert(0, f"{time.strftime('%H:%M', time.localtime())} {log_entry}")

    return WorkState.SELECT_STEP  # Next iteration


def handle_all_done(ctx: WorkContext) -> None:
    """Final review, coverage gate, conclusion."""
    # Run final comprehensive review with configured model
    final_review = None
    if not ctx.config.skip_verify:
        log("Running final comprehensive review...")
        final_review = run_review_phase(
            ctx.title,
            ctx.description,
            ctx.total_start,
            ctx.config.model,
            ctx.config.yolo,
            ctx.config.fallback_tools,
            calc_turns(ctx.config.max_turns, TURNS_QUICK),
            lightweight=False,
            assumptions=ctx.all_assumptions,
            debug=ctx.config.debug,
        )
        if not final_review["approved"]:
            warn(f"Final review: {final_review['summary'][:100]}...")

    # Commit any remaining uncommitted changes
    remaining_changes = get_changed_files()
    if remaining_changes:
        # Run formatters before final commit
        run_format_phase(debug=ctx.config.debug)
        remaining_changes = get_changed_files()  # Re-get after formatting

        commit_msg = final_review["summary"] if final_review else "final cleanup"
        log(f"Committing {len(remaining_changes)} remaining changed files...")
        if not git_commit(
            ctx.ticket_id,
            ctx.iteration,
            commit_msg,
            push=ctx.config.push,
            files_to_add=remaining_changes,
            allow_no_verify=False,
        ):
            warn("Final commit failed - changes not committed")

    # Run coverage gate before conclusion (backend only)
    all_changed = get_changed_files()
    categories = detect_file_categories(all_changed, get_prompts())
    if not ctx.config.skip_verify and categories.get("backend", False):
        coverage_passed, coverage_error = run_coverage_gate(ctx.total_start, ctx.config.debug)
        for attempt in range(MAX_FIX_ATTEMPTS):
            if coverage_passed:
                break
            log(f"Coverage fix attempt {attempt + 1}/{MAX_FIX_ATTEMPTS}")
            run_coverage_fix_phase(get_changed_files(), coverage_error, ctx.total_start, ctx.config)
            # Run tests to verify new tests pass
            test_failure = run_test_phase(
                ctx.title,
                ctx.total_start,
                ctx.config.model,
                ctx.config.yolo,
                ctx.config.fallback_tools,
                debug=ctx.config.debug,
            )
            if test_failure:
                warn(f"Tests failed after coverage fix: {test_failure.summary}")
                continue
            # Commit test additions before re-checking coverage
            test_changes = get_changed_files()
            if test_changes:
                run_format_phase(debug=ctx.config.debug)
                test_changes = get_changed_files()  # Re-get after formatting
                git_commit(
                    ctx.ticket_id,
                    ctx.iteration,
                    "add tests for coverage",
                    push=ctx.config.push,
                    files_to_add=test_changes,
                )
            coverage_passed, coverage_error = run_coverage_gate(ctx.total_start, ctx.config.debug)

        if not coverage_passed:
            warn("Coverage still below 80% after fixes - review manually")

    # Generate and display conclusion (review guide)
    if ctx.branch_name:
        conclusion = run_conclusion_phase(
            ticket_id=ctx.ticket_id,
            title=ctx.title,
            description=ctx.description,
            plan_steps=ctx.plan_steps,
            assumptions=ctx.all_assumptions,
            exploration=ctx.exploration,
            branch_name=ctx.branch_name,
            total_start=ctx.total_start,
            config=ctx.config,
        )
        print_conclusion(conclusion, ctx.ticket_id, ctx.title)

        # Save conclusion to Linear comment
        if ctx.issue_uuid:
            conclusion_md = format_conclusion_markdown(conclusion)
            if save_conclusion_to_linear(ctx.issue_uuid, ctx.branch_name, conclusion_md):
                link = hyperlink(ctx.comment_url, "Linear")
                success(f"Review guide saved to {link}")
            else:
                warn("Failed to save review guide to Linear")

    ticket_elapsed = fmt_duration(time.time() - ctx.total_start)
    ticket_tokens = fmt_tokens(token_tracker.total.total)
    ticket_cost = fmt_cost(token_tracker.total.cost_usd)

    # Surface any manual actions required
    manual_actions = [a for a in ctx.all_assumptions if a.statement.startswith("MANUAL:")]
    if manual_actions:
        warn("Manual actions required:")
        for action in manual_actions:
            log(f"  - {action.statement.replace('MANUAL: ', '')}")

    success_with_conclusion(
        f"All steps complete! ({ticket_elapsed}) | {ticket_tokens} tokens ({ticket_cost})",
        get_diff_summary(),
    )


def handle_max_iterations(ctx: WorkContext) -> None:
    """Handle max iterations reached."""
    total_elapsed = fmt_duration(time.time() - ctx.total_start)
    total_tokens = fmt_tokens(token_tracker.total.total)
    total_cost = fmt_cost(token_tracker.total.cost_usd)

    # Surface any manual actions required
    manual_actions = [a for a in ctx.all_assumptions if a.statement.startswith("MANUAL:")]
    if manual_actions:
        warn("Manual actions required:")
        for action in manual_actions:
            log(f"  - {action.statement.replace('MANUAL: ', '')}")

    warn(
        f"Max iterations ({ctx.config.max_iterations}) reached for {ctx.ticket_id} "
        f"after {total_elapsed} | {total_tokens} tokens ({total_cost})"
    )


# State handler dispatch table
STATE_HANDLERS: dict[WorkState, Callable[[WorkContext], WorkState]] = {
    WorkState.SELECT_STEP: handle_select_step,
    WorkState.EXECUTE_WORK: handle_execute_work,
    WorkState.HANDLE_ASSUMPTIONS: handle_assumptions,
    WorkState.CHECK_COMPLETION: handle_check_completion,
    WorkState.VERIFY_STEP: handle_verify_step,
    WorkState.COMMIT_CHANGES: handle_commit_changes,
    WorkState.SAVE_STATE: handle_save_state,
}


def process_ticket_work(ctx: WorkContext) -> bool:
    """Run work loop state machine. Returns True if successful."""
    state = WorkState.SELECT_STEP

    for ctx.loop_iter in range(1, ctx.config.max_iterations + 1):
        ctx.iter_start = time.time()
        token_tracker.reset_iteration()

        print(f"\n{BLUE}{'━' * 50}{NC}")
        ticket_link = hyperlink(ctx.issue_url, ctx.ticket_id)
        title = ctx.title[:30] + "…" if len(ctx.title) > 30 else ctx.title
        log(f"Iteration {ctx.iteration}/{ctx.config.max_iterations} · {ticket_link}: {title}")
        print(f"{BLUE}{'━' * 50}{NC}")

        # Initialize iteration state for commit trailers
        ctx.iter_state = {
            "files_changed": [],
            "test_errors": [],
            "review_issues": [],
            "fixes_applied": [],
        }

        # Run state machine until we hit SAVE_STATE or ALL_DONE
        while state not in (WorkState.SAVE_STATE, WorkState.ALL_DONE):
            handler = STATE_HANDLERS.get(state)
            if handler is None:
                error(f"Unknown state: {state}")
                return False
            state = handler(ctx)

        if state == WorkState.ALL_DONE:
            handle_all_done(ctx)
            return True

        # SAVE_STATE reached - save and continue to next iteration
        handle_save_state(ctx)
        state = WorkState.SELECT_STEP

        iter_elapsed = fmt_duration(time.time() - ctx.iter_start)
        iter_tokens = fmt_tokens(token_tracker.iteration.total)
        iter_cost = fmt_cost(token_tracker.iteration.cost_usd)
        log(
            f"Iteration {ctx.iteration} completed in {iter_elapsed} | {iter_tokens} tokens ({iter_cost})"
        )

        time.sleep(1)

    # Max iterations reached
    handle_max_iterations(ctx)
    return False
