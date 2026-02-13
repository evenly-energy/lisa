"""Conclusion phase: generate review guide."""

import json
import subprocess
import textwrap
from typing import Optional

from lisa.clients.claude import work_claude
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import RunConfig
from lisa.phases.constants import EFFORT_REVIEW, resolve_effort
from lisa.state.comment import find_state_comment, update_comment
from lisa.ui.output import BLUE, GREEN, NC, RED, YELLOW, warn
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import debug_log


def gather_conclusion_context(branch_name: str) -> dict:
    """Get git diff and commit log for conclusion phase."""
    # Changed files vs main
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", f"main..{branch_name}"],
        capture_output=True,
        text=True,
    )
    changed_files = (
        diff_result.stdout.strip().split("\n")
        if diff_result.returncode == 0 and diff_result.stdout.strip()
        else []
    )

    # Commit log for branch
    log_result = subprocess.run(
        ["git", "log", f"main..{branch_name}", "--oneline"],
        capture_output=True,
        text=True,
    )
    commit_log = log_result.stdout.strip() if log_result.returncode == 0 else ""

    return {"changed_files": changed_files, "commit_log": commit_log}


def run_conclusion_phase(
    ticket_id: str,
    title: str,
    description: str,
    plan_steps: list[dict],
    assumptions: list[Assumption],
    exploration: Optional[ExplorationFindings],
    branch_name: str,
    total_start: float,
    config: RunConfig,
) -> dict:
    """Generate code review guide for the implementation."""
    prompts = get_prompts()
    schemas = get_schemas()

    # Gather git context
    git_context = gather_conclusion_context(branch_name)

    # Format exploration context
    exploration_context = ""
    if exploration:
        if exploration.patterns:
            exploration_context += f"Patterns: {' | '.join(exploration.patterns[:5])}\n"
        if exploration.relevant_modules:
            exploration_context += f"Modules: {', '.join(exploration.relevant_modules[:5])}\n"
        if exploration.similar_implementations:
            templates = [impl.get("file", "") for impl in exploration.similar_implementations[:3]]
            exploration_context += f"Templates used: {', '.join(templates)}\n"
    exploration_context = exploration_context or "No exploration data available"

    # Format plan steps
    plan_steps_summary = (
        "\n".join(
            f"- [{'x' if s.get('done') else ' '}] {s['id']} ({s.get('ticket', ticket_id)}): {s['description']}"
            for s in plan_steps
        )
        if plan_steps
        else "No plan steps recorded"
    )

    # Format assumptions
    assumptions_summary = (
        "\n".join(
            f"- [{a.id}] {a.statement}" + (f" ({a.rationale})" if a.rationale else "")
            for a in assumptions
            if a.selected
        )
        if assumptions
        else "No assumptions recorded"
    )

    # Format changed files
    changed_files = (
        "\n".join(git_context["changed_files"])
        if git_context["changed_files"]
        else "No files changed"
    )

    prompt = prompts["conclusion_summary"]["template"].format(
        ticket_id=ticket_id,
        title=title,
        description=description,
        exploration_context=exploration_context,
        plan_steps_summary=plan_steps_summary,
        assumptions_summary=assumptions_summary,
        changed_files=changed_files,
        commit_log=git_context["commit_log"] or "No commits",
    )

    timer = LiveTimer("Generating review guide...", total_start)
    timer.start()
    output = work_claude(
        prompt,
        config.model,
        config.yolo,
        config.fallback_tools,
        resolve_effort(EFFORT_REVIEW, config.effort),
        json_schema=schemas["conclusion_summary"],
    )
    timer.stop(print_final=False)
    debug_log(config, "Conclusion output", output)

    try:
        result = json.loads(output)
        debug_log(config, "Parsed conclusion result", result)
        return result
    except json.JSONDecodeError as e:
        debug_log(config, "Conclusion JSON parse error", str(e))
        warn(f"Failed to parse conclusion output: {e}")
        return {
            "purpose": "Parse error",
            "entry_point": "?",
            "flow": output[:500],
            "error_handling": [],
            "key_review_points": [],
        }


def print_conclusion(result: dict, ticket_id: str, title: str) -> None:
    """Print conclusion as terminal-friendly output."""
    print(f"\n{BLUE}{'━' * 60}{NC}")
    print(f"📋 Review Guide: {YELLOW}{ticket_id}{NC} - {title}")
    print(f"{BLUE}{'━' * 60}{NC}")

    # Purpose
    print(f"\n{GREEN}Purpose{NC}")
    purpose = result.get("purpose", "N/A")
    for line in textwrap.wrap(purpose, width=70):
        print(f"  {line}")

    # Entry Point
    entry_point = result.get("entry_point", "")
    if entry_point:
        print(f"\n{GREEN}Entry Point{NC}")
        print(f"  {entry_point}")

    # Flow
    print(f"\n{GREEN}Flow{NC}")
    flow = result.get("flow", "N/A")
    # Preserve code blocks and numbered lists
    for line in flow.split("\n"):
        if line.strip():
            # Don't wrap code or numbered steps
            if line.strip().startswith(("```", "   ", "\t")) or line.strip()[0:1].isdigit():
                print(f"  {line}")
            else:
                for w in textwrap.wrap(line, width=68):
                    print(f"  {w}")
        else:
            print()

    # Error Handling
    error_handling = result.get("error_handling", [])
    if error_handling:
        print(f"\n{GREEN}Error Handling{NC}")
        for i, err in enumerate(error_handling, 1):
            print(f"  {i}. {err.get('location')}: {err.get('description')}")

    # Key Review Points
    key_points = result.get("key_review_points", [])
    if key_points:
        print(f"\n{GREEN}Key Review Points{NC}")
        for i, item in enumerate(key_points, 1):
            loc = item.get("location", "?")
            what = item.get("what_it_does", "?")
            risk = item.get("risk", "?")
            print(f"  {i}. {YELLOW}⚠{NC} {loc}")
            print(f"    {what}")
            print(f"    {RED}Risk:{NC} {risk}")

    # Tests
    tests = result.get("tests", {})
    if tests:
        print(f"\n{GREEN}Test Coverage{NC}")
        covered = tests.get("covered", [])
        for t in covered:
            print(f"  {GREEN}✓{NC} {t}")
        missing = tests.get("missing", [])
        for t in missing:
            print(f"  {YELLOW}✗{NC} {t}")

    # Subtask Mapping
    subtask_mapping = result.get("subtask_mapping", [])
    if subtask_mapping:
        print(f"\n{GREEN}Subtasks{NC}")
        for sub in subtask_mapping:
            ticket = sub.get("ticket", "?")
            impl = sub.get("implementation", "?")
            print(f"  {BLUE}{ticket}{NC}: {impl}")

    print(f"\n{BLUE}{'━' * 60}{NC}")


def format_conclusion_markdown(result: dict) -> str:
    """Format conclusion as markdown for Linear comment."""
    lines = ["## Review Guide"]

    # Purpose
    lines.append(f"**Purpose:** {result.get('purpose', 'N/A')}")
    lines.append("")

    # Entry Point
    entry_point = result.get("entry_point", "")
    if entry_point:
        lines.append(f"**Entry Point:** `{entry_point}`")
        lines.append("")

    # Flow
    lines.append("### Flow")
    lines.append(result.get("flow", "N/A"))
    lines.append("")

    # Error Handling
    error_handling = result.get("error_handling", [])
    if error_handling:
        lines.append("### Error Handling")
        for i, err in enumerate(error_handling, 1):
            lines.append(f"{i}. `{err.get('location')}`: {err.get('description')}")
        lines.append("")

    # Key Review Points
    key_points = result.get("key_review_points", [])
    if key_points:
        lines.append("### Key Review Points")
        for i, item in enumerate(key_points, 1):
            loc = item.get("location", "?")
            what = item.get("what_it_does", "?")
            risk = item.get("risk", "?")
            lines.append(f"{i}. **{loc}**")
            lines.append(f"   - {what}")
            lines.append(f"   - ⚠️ Risk: {risk}")
        lines.append("")

    # Tests
    tests = result.get("tests", {})
    if tests:
        lines.append("### Test Coverage")
        for t in tests.get("covered", []):
            lines.append(f"- [x] {t}")
        for t in tests.get("missing", []):
            lines.append(f"- [ ] {t}")
        lines.append("")

    # Subtasks
    subtask_mapping = result.get("subtask_mapping", [])
    if subtask_mapping:
        lines.append("### Subtasks")
        for sub in subtask_mapping:
            ticket = sub.get("ticket", "?")
            impl = sub.get("implementation", "?")
            lines.append(f"- **{ticket}**: {impl}")
        lines.append("")

    return "\n".join(lines)


def save_conclusion_to_linear(issue_uuid: str, branch_name: str, conclusion_md: str) -> bool:
    """Append conclusion to the state comment on Linear."""
    comment = find_state_comment(issue_uuid, branch_name)
    if not comment:
        warn("No state comment found to add conclusion")
        return False

    # Check if conclusion already exists
    body = comment["body"]
    if "## Review Guide" in body:
        # Replace existing review guide
        parts = body.split("## Review Guide")
        new_body = parts[0].rstrip() + "\n\n" + conclusion_md
    else:
        # Append review guide
        new_body = body.rstrip() + "\n\n" + conclusion_md

    return update_comment(comment["id"], new_body)
