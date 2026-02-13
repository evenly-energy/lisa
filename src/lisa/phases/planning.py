"""Planning phase: analyze ticket and create implementation steps."""

import json
from typing import Optional

from lisa.clients.claude import work_claude
from lisa.config.prompts import get_prompts
from lisa.config.schemas import get_schemas
from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import RunConfig
from lisa.constants import EFFORT_PLANNING, resolve_effort
from lisa.ui.output import log, warn
from lisa.ui.timer import LiveTimer
from lisa.utils.debug import debug_log


def sort_by_dependencies(subtasks: list) -> list:
    """Sort subtasks so unblocked ones come first (topological sort)."""
    if not subtasks:
        return subtasks

    # Build lookup and dependency graph
    by_id = {s["id"]: s for s in subtasks}
    subtask_ids = set(by_id.keys())

    # Filter blockedBy to only include sibling subtasks
    for s in subtasks:
        s["_blocked_by"] = [b for b in s.get("blockedBy", []) if b in subtask_ids]

    # Kahn's algorithm for topological sort
    result = []
    remaining = list(subtasks)

    while remaining:
        # Find tasks with no unresolved blockers
        done_ids = {s["id"] for s in result}
        unblocked = [s for s in remaining if all(b in done_ids for b in s["_blocked_by"])]

        if not unblocked:
            # Cycle detected or all blocked - just append rest
            result.extend(remaining)
            break

        # Add first unblocked task
        result.append(unblocked[0])
        remaining.remove(unblocked[0])

    # Cleanup temp field
    for s in result:
        s.pop("_blocked_by", None)

    return result


def run_planning_phase(
    ticket_id: str,
    title: str,
    description: str,
    subtasks: list[dict],
    total_start: float,
    model: str,
    yolo: bool,
    fallback_tools: bool,
    config: RunConfig,
    prior_assumptions: Optional[list[Assumption]] = None,
) -> tuple[list[dict], list[Assumption], Optional[ExplorationFindings]]:
    """Analyze ticket and generate granular implementation steps with ticket association.

    Returns (steps, assumptions, exploration).
    """
    prompts = get_prompts()
    schemas = get_schemas()

    subtask_list = (
        "\n".join(f"- {s['id']}: {s['title']}" for s in subtasks)
        if subtasks
        else "No subtasks defined"
    )
    example_subtask = subtasks[0]["id"] if subtasks else ticket_id

    prompt = prompts["planning"]["template"].format(
        ticket_id=ticket_id,
        title=title,
        description=description,
        subtask_list=subtask_list,
        example_subtask=example_subtask,
    )

    # Add prior assumptions context for replanning
    if prior_assumptions:
        prior_context = "\n## Prior Assumptions (User Reviewed)\nUser reviewed and edited these assumptions. Please replan with these constraints:\n"
        for a in prior_assumptions:
            marker = "[x]" if a.selected else "[ ]"
            prior_context += f"- {marker} {a.statement}"
            if a.rationale:
                prior_context += f" ({a.rationale})"
            prior_context += "\n"
        prompt += prior_context

    timer = LiveTimer("Re-planning..." if prior_assumptions else "Planning...", total_start)
    timer.start()
    output = work_claude(
        prompt,
        model,
        yolo,
        fallback_tools,
        resolve_effort(EFFORT_PLANNING, config.effort),
        json_schema=schemas["planning"],
    )
    timer.stop(print_final=False)
    debug_log(config, "Planning output", output)

    # Parse structured JSON output
    try:
        result = json.loads(output)
        debug_log(config, "Parsed planning result", result)
    except json.JSONDecodeError as e:
        debug_log(config, "Planning JSON parse error", str(e))
        warn(f"Failed to parse planning output as JSON: {e}")
        return [], [], None

    # Extract exploration findings
    exploration_data = result.get("exploration", {})
    exploration = (
        ExplorationFindings(
            patterns=exploration_data.get("patterns", []),
            relevant_modules=exploration_data.get("relevant_modules", []),
            similar_implementations=exploration_data.get("similar_implementations", []),
        )
        if exploration_data
        else None
    )

    if exploration:
        log(
            f"Exploration: {len(exploration.patterns)} patterns, "
            f"{len(exploration.relevant_modules)} modules, "
            f"{len(exploration.similar_implementations)} templates"
        )

    # Extract steps
    steps = [
        {
            "id": s["id"],
            "ticket": s["ticket"],
            "description": s["description"],
            "files": s.get("files", []),
            "done": False,
        }
        for s in result.get("steps", [])
    ]

    # Extract assumptions
    assumptions = [
        Assumption(
            id=str(a["id"]),
            selected=a["selected"],
            statement=a["statement"],
            rationale=a.get("rationale", ""),
        )
        for a in result.get("assumptions", [])
    ]

    if steps:
        log(f"Generated {len(steps)} steps")
    else:
        warn("No plan steps parsed, will use subtasks directly")

    return steps, assumptions, exploration
