"""Prompt loading and management."""

import importlib.resources
from pathlib import Path
from typing import Optional

import yaml

_prompts: Optional[dict] = None


def load_prompts(path: Optional[Path] = None) -> dict:
    """Load prompts from YAML file.

    Args:
        path: Optional override path. If None, loads bundled defaults.

    Returns:
        Dict of prompt configurations.
    """
    if path and path.exists():
        with open(path) as f:
            return yaml.safe_load(f)

    # Load bundled defaults
    try:
        files = importlib.resources.files("lisa")
        prompts_path = files / "prompts" / "default.yaml"
        content = prompts_path.read_text()
        return yaml.safe_load(content)
    except (FileNotFoundError, TypeError):
        # Fallback to relative path during development
        dev_path = Path(__file__).parent.parent.parent.parent / "prompts" / "default.yaml"
        if dev_path.exists():
            with open(dev_path) as f:
                return yaml.safe_load(f)
        raise FileNotFoundError("Could not find prompts file")


def get_prompts() -> dict:
    """Get cached prompts (loads on first access)."""
    global _prompts
    if _prompts is None:
        _prompts = load_prompts()
    return _prompts


def reload_prompts(path: Optional[Path] = None) -> dict:
    """Force reload prompts."""
    global _prompts
    _prompts = load_prompts(path)
    return _prompts
