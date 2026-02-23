"""Tests for lisa.git.commit helper functions."""

import subprocess

from lisa.git.commit import (
    format_assumptions_trailer,
    get_changed_files,
    get_diff_summary,
    git_commit,
    summarize_for_commit,
)
from lisa.models.core import Assumption


class TestFormatAssumptionsTrailer:
    def test_empty(self):
        assert format_assumptions_trailer([]) == ""

    def test_no_selected(self):
        assumptions = [Assumption(id="P.1", selected=False, statement="Skip it")]
        assert format_assumptions_trailer(assumptions) == ""

    def test_single_selected(self):
        assumptions = [Assumption(id="P.1", selected=True, statement="Use Redis")]
        assert format_assumptions_trailer(assumptions) == "Use Redis"

    def test_multiple_joined(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis"),
            Assumption(id="P.2", selected=True, statement="Add cache"),
        ]
        result = format_assumptions_trailer(assumptions)
        assert result == "Use Redis; Add cache"

    def test_truncation_at_50_chars(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="A" * 60),
        ]
        result = format_assumptions_trailer(assumptions)
        assert len(result) == 50

    def test_mixed_selected_rejected(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis"),
            Assumption(id="P.2", selected=False, statement="Skip migration"),
            Assumption(id="P.3", selected=True, statement="Add tests"),
        ]
        result = format_assumptions_trailer(assumptions)
        assert "Use Redis" in result
        assert "Add tests" in result
        assert "Skip migration" not in result


class TestGetChangedFiles:
    def test_empty_status(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert get_changed_files() == []

    def test_modified_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout=" M src/foo.py\n M src/bar.py\n", stderr=""
            ),
        )
        result = get_changed_files()
        assert "src/foo.py" in result
        assert "src/bar.py" in result

    def test_untracked_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="?? new_file.py\n", stderr=""),
        )
        result = get_changed_files()
        assert "new_file.py" in result

    def test_renamed_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout="R  old.py -> new.py\n", stderr=""
            ),
        )
        result = get_changed_files()
        assert "new.py" in result

    def test_mixed_status(self, mocker):
        stdout = " M src/mod.py\n?? new.py\nA  added.py\n"
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
        )
        result = get_changed_files()
        assert len(result) == 3


class TestGetDiffSummary:
    def test_with_changes(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout="2 files changed", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="+new line\n-old line", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ],
        )
        result = get_diff_summary()
        assert "files changed" in result

    def test_no_changes_fallback_to_status(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="?? new_file.py", stderr=""),
            ],
        )
        result = get_diff_summary()
        assert "New files" in result

    def test_completely_empty(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert get_diff_summary() == "no changes"


class TestSummarizeForCommit:
    def test_calls_claude(self, mocker):
        mocker.patch("lisa.git.commit.claude", return_value="  add auth handler  ")
        result = summarize_for_commit("Add authentication handler to the API endpoint")
        assert result == "add auth handler"


class TestGitCommit:
    def _mock_subprocess(self, mocker, commit_rc=0):
        """Setup subprocess mock for git commit flow."""
        calls = [
            subprocess.CompletedProcess([], 0, stdout=" M src/a.py\n", stderr=""),  # status
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            subprocess.CompletedProcess(
                [], commit_rc, stdout="", stderr="hook failed" if commit_rc else ""
            ),  # commit
        ]
        if commit_rc == 0:
            calls.append(
                subprocess.CompletedProcess([], 0, stdout="abc1234\n", stderr="")
            )  # rev-parse
        return mocker.patch("lisa.git.commit.subprocess.run", side_effect=calls)

    def test_no_changes(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert git_commit("ENG-1", 1, "task") is True

    def test_basic_commit(self, mocker):
        self._mock_subprocess(mocker)
        result = git_commit("ENG-1", 1, "step 1: add handler")
        assert result is True

    def test_with_files_to_add(self, mocker):
        mock_run = self._mock_subprocess(mocker)
        git_commit("ENG-1", 1, "step 1", files_to_add=["src/a.py"])
        # Second call is git add -- src/a.py
        add_call = mock_run.call_args_list[1]
        assert "src/a.py" in add_call[0][0]

    def test_with_iter_state(self, mocker):
        self._mock_subprocess(mocker)
        iter_state = {
            "test_errors": [],
            "review_issues": ["minor style"],
        }
        git_commit("ENG-1", 1, "step 1", iter_state=iter_state)

    def test_with_assumptions(self, mocker):
        self._mock_subprocess(mocker)
        assumptions = [Assumption(id="P.1", selected=True, statement="Use cache")]
        git_commit("ENG-1", 1, "step 1", assumptions=assumptions)

    def test_hook_failure_with_fix(self, mocker):
        calls = [
            subprocess.CompletedProcess([], 0, stdout=" M src/a.py\n", stderr=""),  # status
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            subprocess.CompletedProcess(
                [], 1, stdout="", stderr="hook: lint error"
            ),  # commit fails
            # Fix loop: get staged files
            subprocess.CompletedProcess([], 0, stdout="src/a.py\n", stderr=""),  # diff --cached
            # Re-stage after fix
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            # Retry commit succeeds
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # commit
            subprocess.CompletedProcess([], 0, stdout="def5678\n", stderr=""),  # rev-parse
        ]
        mocker.patch("lisa.git.commit.subprocess.run", side_effect=calls)
        mocker.patch("lisa.git.commit.work_claude", return_value="fixed")
        result = git_commit("ENG-1", 1, "step 1", model="opus")
        assert result is True

    def test_hook_failure_falls_back_to_no_verify(self, mocker):
        calls = [
            subprocess.CompletedProcess([], 0, stdout=" M src/a.py\n", stderr=""),  # status
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            subprocess.CompletedProcess([], 1, stdout="", stderr="hook err"),  # commit fails
            # --no-verify
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # commit --no-verify
            subprocess.CompletedProcess([], 0, stdout="abc1234\n", stderr=""),  # rev-parse
        ]
        mocker.patch("lisa.git.commit.subprocess.run", side_effect=calls)
        result = git_commit("ENG-1", 1, "step 1", model=None, allow_no_verify=True)
        assert result is True

    def test_commit_failure_no_verify_disabled(self, mocker):
        calls = [
            subprocess.CompletedProcess([], 0, stdout=" M src/a.py\n", stderr=""),  # status
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            subprocess.CompletedProcess([], 1, stdout="", stderr="hook err"),  # commit fails
        ]
        mocker.patch("lisa.git.commit.subprocess.run", side_effect=calls)
        result = git_commit("ENG-1", 1, "step 1", model=None, allow_no_verify=False)
        assert result is False

    def test_push_on_success(self, mocker):
        calls = [
            subprocess.CompletedProcess([], 0, stdout=" M src/a.py\n", stderr=""),  # status
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # add
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # commit
            subprocess.CompletedProcess([], 0, stdout="abc\n", stderr=""),  # rev-parse
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),  # push
        ]
        mocker.patch("lisa.git.commit.subprocess.run", side_effect=calls)
        result = git_commit("ENG-1", 1, "step 1", push=True)
        assert result is True

    def test_git_status_error(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 128, stdout="", stderr="fatal"),
        )
        assert git_commit("ENG-1", 1, "step 1") is False
