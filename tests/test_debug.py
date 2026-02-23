"""Tests for lisa.utils.debug."""

import json

from lisa.models.state import RunConfig
from lisa.utils.debug import debug_log


class TestDebugLog:
    def test_disabled_does_nothing(self, tmp_path, monkeypatch):
        debug_log(False, "test", "data")
        # No file created

    def test_enabled_with_bool(self, tmp_path, monkeypatch, capsys):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        debug_log(True, "test label", "hello world")
        assert log_file.exists()
        content = log_file.read_text()
        assert "test label" in content
        assert "hello world" in content

    def test_enabled_with_config(self, tmp_path, monkeypatch, capsys):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        config = RunConfig(
            ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus", debug=True
        )
        debug_log(config, "label", {"key": "value"})
        content = log_file.read_text()
        assert "label" in content
        assert '"key"' in content

    def test_disabled_with_config(self, tmp_path, monkeypatch):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        config = RunConfig(
            ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus", debug=False
        )
        debug_log(config, "label", "data")
        assert not log_file.exists()

    def test_json_string_prettified(self, tmp_path, monkeypatch, capsys):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        debug_log(True, "json", json.dumps({"a": 1}))
        content = log_file.read_text()
        assert '"a": 1' in content

    def test_non_json_string(self, tmp_path, monkeypatch, capsys):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        debug_log(True, "plain", "not json {{")
        content = log_file.read_text()
        assert "not json {{" in content

    def test_prints_to_stdout(self, tmp_path, monkeypatch, capsys):
        import lisa.utils.debug as debug_mod

        log_file = tmp_path / ".lisa" / "debug.log"
        monkeypatch.setattr(debug_mod, "DEBUG_LOG", log_file)
        debug_log(True, "stdout test", "data")
        out = capsys.readouterr().out
        assert "debug" in out
        assert "stdout test" in out
