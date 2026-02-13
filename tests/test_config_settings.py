"""Integration tests for lisa.config.settings."""

import lisa.config.settings as settings


class TestLoadConfig:
    def test_defaults_only(self, mocker, reset_config_cache):
        defaults = {"test": {"run": "pytest"}, "format": {"run": "ruff"}}
        mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", return_value=None)
        result = settings.load_config()
        assert result == defaults

    def test_global_override_merges(self, mocker, reset_config_cache):
        defaults = {"test": {"run": "pytest", "timeout": 60}}
        global_override = {"test": {"timeout": 120}}
        mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", side_effect=[global_override, None])
        result = settings.load_config()
        assert result["test"]["run"] == "pytest"
        assert result["test"]["timeout"] == 120

    def test_project_override_merges(self, mocker, reset_config_cache):
        defaults = {"test": {"run": "pytest"}}
        project_override = {"test": {"run": "npm test"}}
        mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", side_effect=[None, project_override])
        result = settings.load_config()
        assert result["test"]["run"] == "npm test"

    def test_full_priority_chain(self, mocker, reset_config_cache):
        defaults = {"test": {"run": "pytest", "timeout": 60}, "format": {"run": "ruff"}}
        global_override = {"test": {"timeout": 120}}
        project_override = {"test": {"timeout": 300}}
        mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch(
            "lisa.config.settings.load_yaml", side_effect=[global_override, project_override]
        )
        result = settings.load_config()
        assert result["test"]["timeout"] == 300  # project wins
        assert result["test"]["run"] == "pytest"  # defaults preserved
        assert result["format"]["run"] == "ruff"  # untouched

    def test_list_replaces_not_appends(self, mocker, reset_config_cache):
        defaults = {"test": {"paths": ["src/"]}}
        override = {"test": {"paths": ["tests/"]}}
        mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", side_effect=[override, None])
        result = settings.load_config()
        assert result["test"]["paths"] == ["tests/"]

    def test_loaded_sources_tracked(self, mocker, reset_config_cache):
        mocker.patch.object(settings, "_load_defaults", return_value={"a": 1})
        mocker.patch("lisa.config.settings.load_yaml", side_effect=[{"b": 2}, None])
        settings.load_config()
        sources = settings.get_config_loaded_sources()
        assert "defaults" in sources
        assert len(sources) == 2  # defaults + global


class TestGetConfig:
    def test_caches_on_first_call(self, mocker, reset_config_cache):
        defaults = {"a": 1}
        load_mock = mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", return_value=None)
        settings.get_config()
        settings.get_config()
        assert load_mock.call_count == 1

    def test_reload_forces_reload(self, mocker, reset_config_cache):
        defaults = {"a": 1}
        load_mock = mocker.patch.object(settings, "_load_defaults", return_value=defaults)
        mocker.patch("lisa.config.settings.load_yaml", return_value=None)
        settings.get_config()
        settings.reload_config()
        assert load_mock.call_count == 2
