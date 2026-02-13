"""JSON schema loading and management."""

import importlib.resources
from pathlib import Path
from typing import Optional

import yaml

_schemas: Optional[dict] = None


def load_schemas(path: Optional[Path] = None) -> dict:
    """Load JSON schemas from YAML file.

    Args:
        path: Optional override path. If None, loads bundled defaults.

    Returns:
        Dict of JSON schemas for Claude structured output.
    """
    if path and path.exists():
        with open(path) as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    # Load bundled defaults
    try:
        files = importlib.resources.files("lisa")
        schemas_path = files / "schemas" / "default.yaml"
        content = schemas_path.read_text()
        return yaml.safe_load(content)  # type: ignore[no-any-return]
    except (FileNotFoundError, TypeError):
        # Fallback to relative path during development
        dev_path = Path(__file__).parent.parent.parent.parent / "schemas" / "default.yaml"
        if dev_path.exists():
            with open(dev_path) as f:
                return yaml.safe_load(f)  # type: ignore[no-any-return]
        raise FileNotFoundError("Could not find schemas file")


def get_schemas() -> dict:
    """Get cached schemas (loads on first access)."""
    global _schemas
    if _schemas is None:
        _schemas = load_schemas()
    return _schemas


def reload_schemas(path: Optional[Path] = None) -> dict:
    """Force reload schemas."""
    global _schemas
    _schemas = load_schemas(path)
    return _schemas
