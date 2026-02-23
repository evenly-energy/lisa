"""Tests for lisa.config.prompts."""

from pathlib import Path

import yaml

import lisa.config.prompts as prompts_mod
from lisa.config.prompts import get_loaded_sources, get_prompts, load_prompts, reload_prompts


class TestLoadDefaults:
    def test_loads_bundled_prompts(self, reset_prompts_cache):
        result = load_prompts()
        assert isinstance(result, dict)
        assert "work" in result
        assert "planning" in result

    def test_defaults_source_recorded(self, reset_prompts_cache):
        load_prompts()
        sources = get_loaded_sources()
        assert "defaults" in sources


class TestLoadPrompts:
    def test_project_override(self, tmp_path, monkeypatch, reset_prompts_cache):
        override = {"custom_key": {"template": "hello {name}"}}
        override_file = tmp_path / "prompts.yaml"
        override_file.write_text(yaml.dump(override))
        monkeypatch.setattr(prompts_mod, "PROJECT_CONFIG", override_file)
        monkeypatch.setattr(prompts_mod, "GLOBAL_CONFIG", Path("/nonexistent/prompts.yaml"))
        result = load_prompts()
        assert "custom_key" in result
        assert result["custom_key"]["template"] == "hello {name}"

    def test_global_override(self, tmp_path, monkeypatch, reset_prompts_cache):
        override = {"global_key": "value"}
        override_file = tmp_path / "prompts.yaml"
        override_file.write_text(yaml.dump(override))
        monkeypatch.setattr(prompts_mod, "GLOBAL_CONFIG", override_file)
        monkeypatch.setattr(prompts_mod, "PROJECT_CONFIG", Path("/nonexistent/prompts.yaml"))
        result = load_prompts()
        assert "global_key" in result

    def test_sources_tracked(self, tmp_path, monkeypatch, reset_prompts_cache):
        override_file = tmp_path / "prompts.yaml"
        override_file.write_text(yaml.dump({"x": 1}))
        monkeypatch.setattr(prompts_mod, "PROJECT_CONFIG", override_file)
        monkeypatch.setattr(prompts_mod, "GLOBAL_CONFIG", Path("/nonexistent/prompts.yaml"))
        load_prompts()
        sources = get_loaded_sources()
        assert "defaults" in sources
        assert str(override_file) in sources


class TestGetPrompts:
    def test_caches_result(self, reset_prompts_cache):
        first = get_prompts()
        second = get_prompts()
        assert first is second

    def test_returns_dict(self, reset_prompts_cache):
        result = get_prompts()
        assert isinstance(result, dict)


class TestReloadPrompts:
    def test_refreshes_cache(self, reset_prompts_cache):
        first = get_prompts()
        second = reload_prompts()
        assert first is not second
        assert isinstance(second, dict)
