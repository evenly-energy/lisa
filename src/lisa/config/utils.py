"""Shared utilities for config loading."""

from pathlib import Path
from typing import Optional

import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Dicts merge, lists/scalars replace."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def load_yaml(path: Path) -> Optional[dict]:
    """Load YAML file, return None if missing or empty."""
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None
