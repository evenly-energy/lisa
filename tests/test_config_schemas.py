"""Tests for lisa.config.schemas."""

from pathlib import Path

import yaml

from lisa.config.schemas import get_schemas, load_schemas, reload_schemas


class TestLoadSchemas:
    def test_loads_defaults(self, reset_schemas_cache):
        result = load_schemas()
        assert isinstance(result, dict)
        assert "work" in result
        assert "planning" in result

    def test_custom_path(self, tmp_path, reset_schemas_cache):
        custom = {"my_schema": {"type": "object"}}
        path = tmp_path / "schemas.yaml"
        path.write_text(yaml.dump(custom))
        result = load_schemas(path)
        assert "my_schema" in result

    def test_custom_path_missing_falls_back(self, reset_schemas_cache):
        result = load_schemas(Path("/nonexistent/schemas.yaml"))
        # Falls back to bundled defaults
        assert "work" in result


class TestGetSchemas:
    def test_caches(self, reset_schemas_cache):
        first = get_schemas()
        second = get_schemas()
        assert first is second

    def test_returns_dict(self, reset_schemas_cache):
        result = get_schemas()
        assert isinstance(result, dict)


class TestReloadSchemas:
    def test_refreshes_cache(self, reset_schemas_cache):
        first = get_schemas()
        second = reload_schemas()
        assert first is not second
        assert isinstance(second, dict)

    def test_reload_with_custom_path(self, tmp_path, reset_schemas_cache):
        custom = {"reloaded": True}
        path = tmp_path / "schemas.yaml"
        path.write_text(yaml.dump(custom))
        result = reload_schemas(path)
        assert result.get("reloaded") is True
