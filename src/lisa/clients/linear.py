"""Linear GraphQL API client."""

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from lisa.auth import get_token
from lisa.ui.output import error, log

LINEAR_API_URL = "https://api.linear.app/graphql"


def _get_auth_header() -> Optional[str]:
    """Get authorization header value from env var or stored OAuth token."""
    api_key = os.environ.get("LINEAR_API_KEY")
    if api_key:
        return api_key  # Linear API keys are sent as-is (no Bearer prefix)

    token = get_token()
    if token:
        return f"Bearer {token}"

    return None


def linear_api(query: str, variables: Optional[dict] = None) -> Optional[dict]:
    """Direct GraphQL call to Linear API. Returns None on error."""
    auth = _get_auth_header()
    if not auth:
        error("Not authenticated. Run `lisa login` or set LINEAR_API_KEY.")
        return None

    data = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        LINEAR_API_URL,
        data=data,
        headers={"Authorization": auth, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=30
        ) as resp:  # nosemgrep: dynamic-urllib-use-detected
            result = json.loads(resp.read())
            if "errors" in result:
                error(f"Linear GraphQL error: {result['errors']}")
                return None
            return result.get("data")  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        error(f"Linear API HTTP {e.code}: {e.reason}")
        return None
    except urllib.error.URLError as e:
        error(f"Linear API connection error: {e.reason}")
        return None
    except Exception as e:
        error(f"Linear API error: {e}")
        return None


def fetch_ticket(ticket_id: str, verbose: bool = False) -> Optional[dict]:
    """Fetch ticket and subtasks via Linear GraphQL API."""
    query = """
    query($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        url
        project { id }
        children {
          nodes {
            id
            identifier
            title
            state { name }
            inverseRelations {
              nodes {
                type
                issue { identifier }
              }
            }
          }
        }
      }
    }
    """
    data = linear_api(query, {"id": ticket_id})
    if not data or not data.get("issue"):
        return None

    issue = data["issue"]

    # Transform subtasks
    subtasks = []
    for child in issue.get("children", {}).get("nodes", []):
        blocked_by = []
        for rel in child.get("inverseRelations", {}).get("nodes", []):
            if rel.get("type") == "blocks":
                blocked_by.append(rel["issue"]["identifier"])

        subtasks.append(
            {
                "id": child["identifier"],
                "uuid": child["id"],
                "title": child["title"],
                "state": child.get("state", {}).get("name", "Unknown"),
                "blockedBy": blocked_by,
            }
        )

    result = {
        "id": issue["identifier"],
        "uuid": issue["id"],
        "title": issue["title"],
        "description": issue.get("description", ""),
        "url": issue.get("url", ""),
        "project_id": issue.get("project", {}).get("id", ""),
        "subtasks": subtasks,
    }
    if verbose:
        log(f"Fetched: {result['title']} with {len(subtasks)} subtasks")
    return result


def fetch_teams() -> Optional[list]:
    """Fetch all teams from Linear. Returns list of {key, name}, empty list if none, or None on error."""
    query = """
    query { teams { nodes { key name } } }
    """
    data = linear_api(query)
    if data is None:
        return None
    teams = data.get("teams")
    if not teams:
        return []
    return teams.get("nodes") or []


def fetch_subtask_details(subtask_id: str) -> Optional[dict]:
    """Fetch subtask title and description from Linear.

    Returns {id, title, description} or None.
    """
    query = """
    query($id: String!) {
      issue(id: $id) {
        identifier
        title
        description
      }
    }
    """
    data = linear_api(query, {"id": subtask_id})
    if not data or not data.get("issue"):
        return None
    issue = data["issue"]
    return {
        "id": issue["identifier"],
        "title": issue["title"],
        "description": issue.get("description", ""),
    }
