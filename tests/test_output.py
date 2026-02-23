"""Tests for lisa.ui.output."""

import json

from lisa.ui.output import (
    error,
    error_with_conclusion,
    generate_conclusion,
    hyperlink,
    log,
    success,
    success_with_conclusion,
    warn,
    warn_with_conclusion,
)


class TestHyperlink:
    def test_format(self):
        result = hyperlink("https://example.com", "Click here")
        assert "\033]8;;https://example.com\007Click here\033]8;;\007" == result

    def test_empty_text(self):
        result = hyperlink("https://x.com", "")
        assert "https://x.com" in result


class TestLogFunctions:
    def test_log(self, capsys):
        log("hello")
        assert "hello" in capsys.readouterr().out

    def test_success(self, capsys):
        success("done")
        assert "done" in capsys.readouterr().out

    def test_warn(self, capsys):
        warn("careful")
        assert "careful" in capsys.readouterr().out

    def test_error(self, capsys):
        error("broke")
        assert "broke" in capsys.readouterr().out


class TestSuccessWithConclusion:
    def test_raw_mode(self, capsys):
        success_with_conclusion("Tests PASS", "pytest, ruff", raw=True)
        out = capsys.readouterr().out
        assert "Tests PASS" in out
        assert "pytest, ruff" in out

    def test_generated_mode(self, capsys, mocker):
        mocker.patch("lisa.ui.output.generate_conclusion", return_value="short summary")
        success_with_conclusion("Done", "long context here")
        out = capsys.readouterr().out
        assert "Done" in out
        assert "short summary" in out


class TestWarnWithConclusion:
    def test_raw(self, capsys):
        warn_with_conclusion("FAIL", "test failed", raw=True)
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "test failed" in out


class TestErrorWithConclusion:
    def test_raw(self, capsys):
        error_with_conclusion("ERR", "details", raw=True)
        out = capsys.readouterr().out
        assert "ERR" in out


class TestGenerateConclusion:
    def test_calls_claude(self, mocker):
        mocker.patch("lisa.ui.output._claude_fn", return_value=json.dumps({"text": "added auth"}))
        mocker.patch("lisa.ui.output._prompts", {"conclusion": {"template": "summarize {context}"}})
        mocker.patch("lisa.ui.output._schemas", {"conclusion": {"type": "object"}})
        result = generate_conclusion("big context")
        assert result == "added auth"

    def test_json_parse_fallback(self, mocker):
        mocker.patch("lisa.ui.output._claude_fn", return_value="plain text response")
        mocker.patch("lisa.ui.output._prompts", {"conclusion": {"template": "summarize {context}"}})
        mocker.patch("lisa.ui.output._schemas", {"conclusion": {"type": "object"}})
        result = generate_conclusion("context")
        assert result == "plain text response"

    def test_truncates_long_result(self, mocker):
        mocker.patch(
            "lisa.ui.output._claude_fn",
            return_value=json.dumps({"text": "x" * 200}),
        )
        mocker.patch("lisa.ui.output._prompts", {"conclusion": {"template": "s {context}"}})
        mocker.patch("lisa.ui.output._schemas", {"conclusion": {"type": "object"}})
        result = generate_conclusion("context")
        assert len(result) <= 80
