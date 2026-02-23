"""Tests for lisa.phases.conclusion."""

import subprocess

from lisa.phases.conclusion import (
    format_conclusion_markdown,
    gather_conclusion_context,
    print_conclusion,
    save_conclusion_to_linear,
)


class TestFormatConclusionMarkdown:
    def test_minimal(self):
        result = format_conclusion_markdown({"purpose": "Add auth"})
        assert "## Review Guide" in result
        assert "Add auth" in result

    def test_with_entry_point(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Add auth",
                "entry_point": "src/auth/handler.py",
            }
        )
        assert "`src/auth/handler.py`" in result

    def test_with_flow(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Add auth",
                "flow": "1. Request comes in\n2. Auth check\n3. Response",
            }
        )
        assert "### Flow" in result
        assert "Request comes in" in result

    def test_with_error_handling(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Add auth",
                "error_handling": [
                    {"location": "handler.py:25", "description": "Catches auth errors"},
                ],
            }
        )
        assert "### Error Handling" in result
        assert "`handler.py:25`" in result

    def test_with_key_review_points(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Add auth",
                "key_review_points": [
                    {
                        "location": "handler.py:30",
                        "what_it_does": "Validates JWT",
                        "risk": "Token expiry not checked",
                    },
                ],
            }
        )
        assert "### Key Review Points" in result
        assert "**handler.py:30**" in result
        assert "Validates JWT" in result
        assert "Token expiry" in result

    def test_with_tests(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Add auth",
                "tests": {
                    "covered": ["JWT validation", "Login flow"],
                    "missing": ["Refresh token"],
                },
            }
        )
        assert "### Test Coverage" in result
        assert "[x] JWT validation" in result
        assert "[ ] Refresh token" in result

    def test_with_subtask_mapping(self):
        result = format_conclusion_markdown(
            {
                "purpose": "Multi-subtask",
                "subtask_mapping": [
                    {"ticket": "ENG-71", "implementation": "Added handler"},
                    {"ticket": "ENG-72", "implementation": "Added tests"},
                ],
            }
        )
        assert "### Subtasks" in result
        assert "**ENG-71**" in result


class TestPrintConclusion:
    def test_prints_purpose(self, capsys):
        result = {"purpose": "Add caching layer", "flow": "1. Check cache\n2. Return"}
        print_conclusion(result, "ENG-123", "Add caching")
        out = capsys.readouterr().out
        assert "ENG-123" in out
        assert "Add caching layer" in out

    def test_prints_key_review_points(self, capsys):
        result = {
            "purpose": "Fix",
            "flow": "flow",
            "key_review_points": [
                {"location": "handler.py:10", "what_it_does": "Validates input", "risk": "XSS"},
            ],
        }
        print_conclusion(result, "ENG-1", "Fix")
        out = capsys.readouterr().out
        assert "handler.py:10" in out
        assert "XSS" in out

    def test_prints_tests(self, capsys):
        result = {
            "purpose": "X",
            "flow": "Y",
            "tests": {"covered": ["auth test"], "missing": ["edge case"]},
        }
        print_conclusion(result, "ENG-1", "X")
        out = capsys.readouterr().out
        assert "auth test" in out
        assert "edge case" in out

    def test_prints_subtasks(self, capsys):
        result = {
            "purpose": "X",
            "flow": "Y",
            "subtask_mapping": [{"ticket": "ENG-5", "implementation": "done"}],
        }
        print_conclusion(result, "ENG-1", "X")
        out = capsys.readouterr().out
        assert "ENG-5" in out

    def test_prints_error_handling(self, capsys):
        result = {
            "purpose": "X",
            "flow": "Y",
            "error_handling": [{"location": "api.py:20", "description": "catches 404"}],
        }
        print_conclusion(result, "ENG-1", "X")
        out = capsys.readouterr().out
        assert "api.py:20" in out


class TestGatherConclusionContext:
    def test_gathers_diff_and_log(self, mocker):
        mocker.patch(
            "lisa.phases.conclusion.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout="src/a.py\nsrc/b.py", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="abc1234 feat: add thing", stderr=""),
            ],
        )
        ctx = gather_conclusion_context("eng-123-foo")
        assert ctx["changed_files"] == ["src/a.py", "src/b.py"]
        assert "abc1234" in ctx["commit_log"]

    def test_empty_on_failure(self, mocker):
        mocker.patch(
            "lisa.phases.conclusion.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="error"),
        )
        ctx = gather_conclusion_context("eng-123-foo")
        assert ctx["changed_files"] == []
        assert ctx["commit_log"] == ""


class TestSaveConclusionToLinear:
    def test_no_comment_found(self, mocker):
        mocker.patch("lisa.phases.conclusion.find_state_comment", return_value=None)
        assert save_conclusion_to_linear("uuid", "branch", "# Guide") is False

    def test_appends_to_existing(self, mocker):
        mocker.patch(
            "lisa.phases.conclusion.find_state_comment",
            return_value={"id": "c1", "body": "existing content"},
        )
        mock_update = mocker.patch("lisa.phases.conclusion.update_comment", return_value=True)
        assert save_conclusion_to_linear("uuid", "branch", "## Review Guide\nNew") is True
        call_body = mock_update.call_args[0][1]
        assert "existing content" in call_body
        assert "## Review Guide" in call_body

    def test_replaces_existing_guide(self, mocker):
        mocker.patch(
            "lisa.phases.conclusion.find_state_comment",
            return_value={"id": "c1", "body": "Header\n\n## Review Guide\nOld guide"},
        )
        mock_update = mocker.patch("lisa.phases.conclusion.update_comment", return_value=True)
        save_conclusion_to_linear("uuid", "branch", "## Review Guide\nNew guide")
        call_body = mock_update.call_args[0][1]
        assert "Old guide" not in call_body
        assert "New guide" in call_body
