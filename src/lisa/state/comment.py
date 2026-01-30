"""Linear comment state management with backwards compatibility."""

import re
import time
from typing import Optional

from lisa.clients.linear import linear_api
from lisa.models.core import Assumption, ExplorationFindings
from lisa.ui.output import warn


def get_state_headers(branch_name: str) -> list[str]:
    """Get state comment headers for both lisa and legacy tralph.

    Returns list for searching (lisa first, tralph fallback).
    """
    return [
        f"🤖 **lisa** · `{branch_name}`",
        f"🤖 **tralph** · `{branch_name}`",  # legacy
    ]


def get_state_header(branch_name: str) -> str:
    """Get state header for NEW comments (uses lisa)."""
    return f"🤖 **lisa** · `{branch_name}`"


def list_comments(issue_id: str) -> list[dict]:
    """List comments on an issue via Linear API."""
    query = """
    query($id: String!) {
      issue(id: $id) {
        comments {
          nodes {
            id
            body
          }
        }
      }
    }
    """
    data = linear_api(query, {"id": issue_id})
    if not data or not data.get("issue"):
        return []
    return data["issue"].get("comments", {}).get("nodes", [])


def find_state_comment(issue_id: str, branch_name: str) -> Optional[dict]:
    """Find state comment for this branch (supports both lisa and tralph headers).

    Returns {id, body} or None.
    """
    headers = get_state_headers(branch_name)
    comments = list_comments(issue_id)
    for comment in comments:
        body = comment.get("body", "")
        for header in headers:
            if body.startswith(header):
                return {"id": comment["id"], "body": body}
    return None


def create_comment(issue_id: str, body: str) -> Optional[str]:
    """Create comment on issue. Returns comment ID."""
    mutation = """
    mutation($issueId: String!, $body: String!) {
      commentCreate(input: { issueId: $issueId, body: $body }) {
        success
        comment { id }
      }
    }
    """
    data = linear_api(mutation, {"issueId": issue_id, "body": body})
    if not data or not data.get("commentCreate", {}).get("success"):
        return None
    return data["commentCreate"]["comment"]["id"]


def update_comment(comment_id: str, body: str) -> bool:
    """Update existing comment."""
    mutation = """
    mutation($id: String!, $body: String!) {
      commentUpdate(id: $id, input: { body: $body }) {
        success
      }
    }
    """
    data = linear_api(mutation, {"id": comment_id, "body": body})
    return data and data.get("commentUpdate", {}).get("success", False)


def parse_state_comment(body: str) -> dict:
    """Parse state from comment body.

    Returns dict with iterations, current_step, plan_steps.
    """
    result = {"iterations": 0, "current_step": None, "plan_steps": []}

    # Parse plan checklist
    for line in body.split("\n"):
        line = line.strip()
        # Match: - [x] **1** (ENG-456): Description or - [ ] **2**: Description ← current
        step_match = re.match(
            r"- \[([ x])\] \*\*(\d+)\*\*(?: \(([^)]+)\))?: (.+?)(?:\s*←\s*current)?$", line
        )
        if step_match:
            done = step_match.group(1) == "x"
            step_id = int(step_match.group(2))
            ticket = step_match.group(3) or ""
            desc = step_match.group(4).strip()
            result["plan_steps"].append(
                {
                    "id": step_id,
                    "ticket": ticket,
                    "description": desc,
                    "done": done,
                }
            )

    # Parse table rows
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("| Iterations |"):
            match = re.search(
                r"\|\s*(\d+)\s*\|", line.split("|")[2] if len(line.split("|")) > 2 else ""
            )
            if match:
                result["iterations"] = int(match.group(1))
        elif line.startswith("| Current step |"):
            parts = line.split("|")
            if len(parts) > 2:
                val = parts[2].strip()
                if val and val != "-":
                    try:
                        result["current_step"] = int(val)
                    except ValueError:
                        pass

    return result


def fetch_state(issue_uuid: str, branch_name: str) -> Optional[dict]:
    """Fetch state from comment on issue."""
    comment = find_state_comment(issue_uuid, branch_name)
    if not comment:
        return None

    body = comment["body"]
    state = parse_state_comment(body)
    assumptions = parse_assumptions_markdown(body)
    return {
        "comment_id": comment["id"],
        "iterations": state["iterations"],
        "current_step": state["current_step"],
        "plan_steps": state["plan_steps"],
        "assumptions": assumptions,
    }


def format_exploration_markdown(exploration: Optional[ExplorationFindings]) -> str:
    """Format exploration findings as markdown for Linear comment."""
    if not exploration:
        return ""
    lines = ["## Exploration"]

    if exploration.patterns:
        patterns_str = " | ".join(exploration.patterns[:5])  # Limit to 5 patterns
        lines.append(f"**Patterns:** {patterns_str}")

    if exploration.relevant_modules:
        modules_str = ", ".join(exploration.relevant_modules[:5])  # Limit to 5 modules
        lines.append(f"**Modules:** {modules_str}")

    if exploration.similar_implementations:
        templates = []
        for impl in exploration.similar_implementations[:3]:  # Limit to 3 templates
            file_name = impl.get("file", "").split("/")[-1]  # Just filename
            relevance = impl.get("relevance", "")
            if file_name:
                templates.append(f"{file_name} ({relevance[:30]})" if relevance else file_name)
        if templates:
            lines.append(f"**Templates:** {', '.join(templates)}")

    return "\n".join(lines) + "\n\n" if len(lines) > 1 else ""


def format_assumptions_markdown(assumptions: list[Assumption]) -> str:
    """Format assumptions as markdown for Linear comment.

    Groups assumptions by type:
    - P.x = planning phase assumptions
    - N.x = work-phase assumptions (N = iteration number)
    """
    if not assumptions:
        return ""

    # Group by prefix type
    planning = [a for a in assumptions if a.id.startswith("P.")]
    work = [a for a in assumptions if not a.id.startswith("P.")]

    lines = ["## Assumptions"]

    def format_group(group: list[Assumption]) -> None:
        for a in group:
            emoji = "✅" if a.selected else "❌"
            lines.append(f"{emoji} {a.id}. {a.statement}")
            if a.rationale:
                lines.append(f"   *{a.rationale}*")

    if planning:
        format_group(planning)
    if work:
        format_group(work)

    return "\n".join(lines) + "\n\n"


def parse_assumptions_markdown(body: str) -> list[Assumption]:
    """Parse assumptions from markdown in Linear comment."""
    assumptions = []
    lines = body.split("\n")
    current_assumption = None

    for line in lines:
        # Match: ✅ P.1. Statement or ❌ 1.2. Statement
        assumption_match = re.match(r"([✅❌]) ([A-Z]\.\d+|\d+(?:\.\d+)?)\. (.+)", line.strip())
        if assumption_match:
            if current_assumption:
                assumptions.append(current_assumption)
            selected = assumption_match.group(1) == "✅"
            aid = assumption_match.group(2)
            statement = assumption_match.group(3).strip()
            current_assumption = Assumption(
                id=aid, selected=selected, statement=statement, rationale=""
            )
        # Match rationale: *rationale text*
        elif current_assumption and line.strip().startswith("*") and line.strip().endswith("*"):
            current_assumption.rationale = line.strip()[1:-1]

    if current_assumption:
        assumptions.append(current_assumption)

    return assumptions


def build_state_comment(
    branch_name: str,
    iteration: int,
    current_step: Optional[int],
    plan_steps: list[dict],
    log_entries: list[str],
    assumptions: Optional[list[Assumption]] = None,
    exploration: Optional[ExplorationFindings] = None,
) -> str:
    """Build state comment body with exploration, plan checklist, and assumptions."""
    header = get_state_header(branch_name)
    timestamp = time.strftime("%Y-%m-%d %H:%M %Z", time.localtime())

    body = f"""{header}

"""
    # Add exploration section if present
    if exploration:
        body += format_exploration_markdown(exploration)

    # Add plan checklist if we have steps
    if plan_steps:
        body += "## Plan\n"
        for step in plan_steps:
            checkbox = "x" if step.get("done") else " "
            marker = " ← current" if step["id"] == current_step else ""
            ticket = step.get("ticket", "")
            ticket_str = f" ({ticket})" if ticket else ""
            body += f"- [{checkbox}] **{step['id']}**{ticket_str}: {step['description']}{marker}\n"
            for f in step.get("files", []):
                op = f["op"]
                body += f"  - `{op}`: {f['path']}\n"
                if f.get("template"):
                    body += f"    template: {f['template']}\n"
                if f.get("detail"):
                    body += f"    detail: {f['detail']}\n"
        body += "\n"

    # Add assumptions section if present
    if assumptions:
        body += format_assumptions_markdown(assumptions)

    body += f"""| Field | Value |
|-------|-------|
| Iterations | {iteration} |
| Current step | {current_step or '-'} |
| Last run | {timestamp} |

**Log:**
"""
    # Add log entries (most recent first, limit to 10)
    for entry in log_entries[:10]:
        body += f"- {entry}\n"

    return body


def save_state(
    issue_uuid: str,
    branch_name: str,
    iteration: int,
    current_step: Optional[int] = None,
    plan_steps: Optional[list] = None,
    comment_id: Optional[str] = None,
    log_entry: str = "",
    existing_log: list[str] = None,
    assumptions: Optional[list[Assumption]] = None,
    exploration: Optional[ExplorationFindings] = None,
) -> Optional[str]:
    """Save state to comment. Returns comment ID."""
    steps = plan_steps or []
    log_entries = existing_log or []
    if log_entry:
        timestamp = time.strftime("%H:%M", time.localtime())
        log_entries.insert(0, f"{timestamp} {log_entry}")

    body = build_state_comment(
        branch_name, iteration, current_step, steps, log_entries, assumptions, exploration
    )

    if comment_id:
        if update_comment(comment_id, body):
            return comment_id
        warn("Failed to update state comment")
        return None
    else:
        new_id = create_comment(issue_uuid, body)
        if new_id:
            return new_id
        warn("Failed to create state comment")
        return None
