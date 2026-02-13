"""Integration tests for lisa.clients.claude."""

import json
import subprocess

from lisa.clients.claude import claude, token_tracker, work_claude


class TestClaude:
    def _mock_run(self, mocker, stdout, returncode=0, stderr=""):
        return mocker.patch(
            "lisa.clients.claude.subprocess.run",
            return_value=subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr),
        )

    def test_command_construction(self, mocker, reset_token_tracker):
        mock = self._mock_run(mocker, json.dumps({"result": "ok"}))
        claude("hello", model="sonnet")
        cmd = mock.call_args[0][0]
        assert "claude" in cmd
        assert "-p" in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_allowed_tools_flag(self, mocker, reset_token_tracker):
        mock = self._mock_run(mocker, json.dumps({"result": "ok"}))
        claude("hello", model="sonnet", allowed_tools="Read Write")
        cmd = mock.call_args[0][0]
        assert "--allowedTools" in cmd
        assert "Read Write" in cmd

    def test_yolo_flag(self, mocker, reset_token_tracker):
        mock = self._mock_run(mocker, json.dumps({"result": "ok"}))
        claude("hello", model="sonnet", yolo=True)
        cmd = mock.call_args[0][0]
        assert "--dangerously-skip-permissions" in cmd

    def test_effort_flag(self, mocker, reset_token_tracker):
        mock = self._mock_run(mocker, json.dumps({"result": "ok"}))
        claude("hello", model="sonnet", effort="low")
        cmd = mock.call_args[0][0]
        assert "--effort" in cmd
        assert "low" in cmd

    def test_json_schema_flag(self, mocker, reset_token_tracker):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        mock = self._mock_run(mocker, json.dumps({"result": "ok"}))
        claude("hello", model="sonnet", json_schema=schema)
        cmd = mock.call_args[0][0]
        assert "--json-schema" in cmd

    def test_result_extraction(self, mocker, reset_token_tracker):
        self._mock_run(mocker, json.dumps({"result": "extracted text"}))
        result = claude("hello", model="sonnet")
        assert result == "extracted text"

    def test_structured_output_extraction(self, mocker, reset_token_tracker):
        schema = {"type": "object"}
        self._mock_run(mocker, json.dumps({"structured_output": {"key": "value"}}))
        result = claude("hello", model="sonnet", json_schema=schema)
        assert json.loads(result) == {"key": "value"}

    def test_token_tracking(self, mocker, reset_token_tracker):
        wrapper = {
            "result": "ok",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
                "total_cost_usd": 0.01,
            },
        }
        self._mock_run(mocker, json.dumps(wrapper))
        claude("hello", model="sonnet")
        assert token_tracker.total.input_tokens == 100
        assert token_tracker.total.output_tokens == 50
        assert token_tracker.total.cost_usd == 0.01

    def test_non_json_fallback(self, mocker, reset_token_tracker):
        self._mock_run(mocker, "raw text output")
        result = claude("hello", model="sonnet")
        assert result == "raw text output"

    def test_nonzero_exit_still_processes(self, mocker, reset_token_tracker):
        self._mock_run(mocker, json.dumps({"result": "partial"}), returncode=1, stderr="error")
        result = claude("hello", model="sonnet")
        assert result == "partial"


class TestWorkClaude:
    def test_yolo_mode(self, mocker, reset_token_tracker):
        mock = mocker.patch("lisa.clients.claude.claude", return_value="result")
        work_claude("prompt", "sonnet", yolo=True)
        mock.assert_called_once_with(
            "prompt", model="sonnet", yolo=True, effort=None, json_schema=None
        )

    def test_fallback_tools_mode(self, mocker, reset_token_tracker):
        mocker.patch("lisa.clients.claude.get_fallback_tools", return_value="Read Write")
        mock = mocker.patch("lisa.clients.claude.claude", return_value="result")
        work_claude("prompt", "sonnet", fallback_tools=True)
        mock.assert_called_once_with(
            "prompt", model="sonnet", allowed_tools="Read Write", effort=None, json_schema=None
        )

    def test_default_mode(self, mocker, reset_token_tracker):
        mock = mocker.patch("lisa.clients.claude.claude", return_value="result")
        work_claude("prompt", "sonnet")
        mock.assert_called_once_with(
            "prompt", model="sonnet", effort=None, json_schema=None
        )
