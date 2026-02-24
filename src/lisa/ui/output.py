"""Terminal output helpers with colors and hyperlinks."""

from typing import Any, Callable, Optional

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
GRAY = "\033[90m"
MAGENTA = "\033[0;35m"
NC = "\033[0m"

# Module-level references set at runtime to avoid circular imports
_claude_fn: Optional[Callable[..., str]] = None
_prompts: Optional[dict[str, Any]] = None
_schemas: Optional[dict[str, Any]] = None


def _init_conclusion_deps() -> None:
    """Lazy-init dependencies for conclusion generation."""
    global _claude_fn, _prompts, _schemas
    if _claude_fn is None:
        from lisa.clients.claude import claude
        from lisa.config.prompts import get_prompts
        from lisa.config.schemas import get_schemas

        _claude_fn = claude
        _prompts = get_prompts()
        _schemas = get_schemas()


def hyperlink(url: str, text: str) -> str:
    """OSC 8 hyperlink - clickable in modern terminals."""
    return f"\033]8;;{url}\007{text}\033]8;;\007"


def log(msg: str) -> None:
    print(f"\r\033[K{BLUE}[lisa]{NC} {msg}")


def success(msg: str) -> None:
    print(f"\r\033[K{GREEN}[lisa]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"\r\033[K{YELLOW}[lisa]{NC} {msg}")


def error(msg: str) -> None:
    print(f"\r\033[K{RED}[lisa]{NC} {msg}")


MAX_CONTEXT_CHARS = 500


def generate_conclusion(context: str) -> str:
    """Use Haiku to generate a short conclusion (max ~10 words)."""
    import json

    _init_conclusion_deps()
    assert _claude_fn is not None and _prompts is not None and _schemas is not None

    prompt = _prompts["conclusion"]["template"].format(context=context[:MAX_CONTEXT_CHARS])
    result = _claude_fn(
        prompt, model="haiku", allowed_tools="", effort="low", json_schema=_schemas["conclusion"]
    )
    try:
        data = json.loads(result)
        return str(data.get("text", ""))[:80]
    except json.JSONDecodeError:
        return result.strip()[:80]


def success_with_conclusion(msg: str, context: str, raw: bool = False) -> None:
    """Print success message with gray conclusion (generated or raw)."""
    conclusion = context if raw else generate_conclusion(context)
    print(f"\r\033[K{GREEN}[lisa]{NC} {msg}  {GRAY}{conclusion}{NC}")


def warn_with_conclusion(msg: str, context: str, raw: bool = False) -> None:
    """Print warning message with gray conclusion (generated or raw)."""
    conclusion = context if raw else generate_conclusion(context)
    print(f"\r\033[K{YELLOW}[lisa]{NC} {msg}  {GRAY}{conclusion}{NC}")


def error_with_conclusion(msg: str, context: str, raw: bool = False) -> None:
    """Print error message with gray conclusion (generated or raw)."""
    conclusion = context if raw else generate_conclusion(context)
    print(f"\r\033[K{RED}[lisa]{NC} {msg}  {GRAY}{conclusion}{NC}")
