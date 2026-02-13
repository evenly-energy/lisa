"""Stack config loading with layered overrides.

Priority chain: bundled defaults < ~/.config/lisa/config.yaml < .lisa/config.yaml
Deep merge: dicts merge recursively, lists/scalars replace.
"""

import importlib.resources
from pathlib import Path
from typing import Optional

import yaml

from lisa.config.utils import deep_merge, load_yaml

_config: Optional[dict] = None
_loaded_sources: list[str] = []

GLOBAL_CONFIG = Path.home() / ".config" / "lisa" / "config.yaml"
PROJECT_CONFIG = Path(".lisa") / "config.yaml"


def _load_defaults() -> dict:
    """Load bundled default config."""
    try:
        files = importlib.resources.files("lisa")
        config_path = files / "defaults" / "config.yaml"
        content = config_path.read_text()
        return yaml.safe_load(content)
    except (FileNotFoundError, TypeError):
        dev_path = Path(__file__).parent.parent / "defaults" / "config.yaml"
        if dev_path.exists():
            with open(dev_path) as f:
                return yaml.safe_load(f)
        raise FileNotFoundError("Could not find defaults/config.yaml")


def load_config() -> dict:
    """Load config with layered overrides: defaults < global < project."""
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


def get_config() -> dict:
    """Get cached config (loads on first access)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> dict:
    """Force reload config."""
    global _config
    _config = load_config()
    return _config


def get_config_loaded_sources() -> list[str]:
    """Return list of config sources that were loaded (for logging)."""
    return _loaded_sources
