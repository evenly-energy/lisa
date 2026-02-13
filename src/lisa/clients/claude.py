"""Claude CLI client wrapper."""

import json
import subprocess
from typing import Optional

from lisa.models.results import TokenUsage
from lisa.ui.output import error, warn

# Default fallback tools when project settings not available
# This is overridden by config.fallback_tools in prompts.yaml
DEFAULT_FALLBACK_TOOLS = (
    "Read Edit Write Grep Glob Skill Bash(git:*) Bash(cd:*) Bash(ls:*) Bash(mkdir:*) Bash(rm:*)"
)


def get_fallback_tools() -> str:
    """Get fallback tools from config or use default."""
    try:
        from lisa.config.prompts import get_prompts

        prompts = get_prompts()
        config = prompts.get("config", {})
        return config.get("fallback_tools", DEFAULT_FALLBACK_TOOLS).strip()
    except Exception:
        return DEFAULT_FALLBACK_TOOLS


class TokenTracker:
    """Track token usage across iterations."""

    def __init__(self):
        self.iteration = TokenUsage()
        self.total = TokenUsage()

    def add(self, usage: TokenUsage) -> None:
        self.iteration = self.iteration + usage
        self.total = self.total + usage

    def reset_iteration(self) -> None:
        self.iteration = TokenUsage()


# Global token tracker instance
token_tracker = TokenTracker()


def claude(
    prompt: str,
    model: str,
    allowed_tools: Optional[str] = None,
    yolo: bool = False,
    verbose: bool = False,
    effort: Optional[str] = None,
    json_schema: Optional[dict] = None,
) -> str:
    """Run claude CLI and return output.

    Always uses --output-format json to get token usage data.
    When json_schema is provided, also uses --json-schema for structured output.
    """
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if allowed_tools:
        cmd.extend(["--allowedTools", allowed_tools])
    if yolo:
        cmd.append("--dangerously-skip-permissions")
    if effort:
        cmd.extend(["--effort", effort])
    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True)

    if result.returncode != 0:
        error(f"Claude CLI exited with code {result.returncode}")
        if result.stderr:
            error(f"stderr: {result.stderr[:500]}")

    if verbose and result.stderr:
        warn(f"Claude stderr: {result.stderr[:200]}")

    output = result.stdout

    # Always parse JSON wrapper to extract usage and result
    if output.strip():
        try:
            wrapper = json.loads(output)
            if isinstance(wrapper, dict):
                # Extract and track token usage
                usage = wrapper.get("usage", {})
                if usage:
                    token_tracker.add(
                        TokenUsage(
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                            cost_usd=usage.get("total_cost_usd", 0.0),
                        )
                    )

                # Return structured_output if json_schema was used
                if json_schema and "structured_output" in wrapper:
                    structured = wrapper["structured_output"]
                    return json.dumps(structured) if isinstance(structured, dict) else structured

                # Return result field (text output)
                if "result" in wrapper:
                    return wrapper["result"]
        except json.JSONDecodeError:
            warn("JSON output extraction failed, using raw output")

    return output


def work_claude(
    prompt: str,
    model: str,
    yolo: bool = False,
    fallback_tools: bool = False,
    effort: Optional[str] = None,
    json_schema: Optional[dict] = None,
) -> str:
    """Run claude for coding work."""
    if yolo:
        return claude(prompt, model=model, yolo=True, effort=effort, json_schema=json_schema)
    if fallback_tools:
        return claude(
            prompt,
            model=model,
            allowed_tools=get_fallback_tools(),
            effort=effort,
            json_schema=json_schema,
        )
    # Default: rely on project .claude/settings.json permissions
    return claude(prompt, model=model, effort=effort, json_schema=json_schema)
