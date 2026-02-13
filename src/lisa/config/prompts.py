"""Prompt loading and management with layered config overrides.

Priority chain: bundled defaults < ~/.config/lisa/prompts.yaml < .lisa/prompts.yaml
Deep merge: dicts merge recursively, lists/scalars replace.
"""

import importlib.resources
from pathlib import Path
from typing import Optional

import yaml

from lisa.config.utils import deep_merge, load_yaml

_prompts: Optional[dict] = None
_loaded_sources: list[str] = []

GLOBAL_CONFIG = Path.home() / ".config" / "lisa" / "prompts.yaml"
PROJECT_CONFIG = Path(".lisa") / "prompts.yaml"


def _load_defaults() -> dict:
    """Load bundled default prompts."""
    try:
        files = importlib.resources.files("lisa")
        prompts_path = files / "prompts" / "default.yaml"
        content = prompts_path.read_text()
        return yaml.safe_load(content)  # type: ignore[no-any-return]
    except (FileNotFoundError, TypeError):
        dev_path = Path(__file__).parent.parent.parent.parent / "prompts" / "default.yaml"
        if dev_path.exists():
            with open(dev_path) as f:
                return yaml.safe_load(f)  # type: ignore[no-any-return]
        raise FileNotFoundError("Could not find prompts file")


def load_prompts() -> dict:
    """Load prompts with layered overrides: defaults < global < project."""
    global _loaded_sources
    _loaded_sources = []

    result = _load_defaults()
    _loaded_sources.append("defaults")

    global_overrides = load_yaml(GLOBAL_CONFIG)
    if global_overrides:
        result = deep_merge(result, global_overrides)
        _loaded_sources.append(str(GLOBAL_CONFIG))

    project_overrides = load_yaml(PROJECT_CONFIG)
    if project_overrides:
        result = deep_merge(result, project_overrides)
        _loaded_sources.append(str(PROJECT_CONFIG))

    return result


def get_prompts() -> dict:
    """Get cached prompts (loads on first access)."""
    global _prompts
    if _prompts is None:
        _prompts = load_prompts()
    return _prompts


def reload_prompts() -> dict:
    """Force reload prompts."""
    global _prompts
    _prompts = load_prompts()
    return _prompts


def get_loaded_sources() -> list[str]:
    """Return list of config sources that were loaded (for logging)."""
    return _loaded_sources
