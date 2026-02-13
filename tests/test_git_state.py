"""Integration tests for lisa.state.git.fetch_git_state."""

import subprocess

from lisa.state.git import fetch_git_state


def _mock_git_log(mocker, stdout, returncode=0):
    return mocker.patch(
        "lisa.state.git.subprocess.run",
        return_value=subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=""),
    )


class TestFetchGitState:
    def test_no_commits_empty(self, mocker):
        _mock_git_log(mocker, "", returncode=0)
        result = fetch_git_state("eng-1-test")
        assert result["iterations"] == []
        assert result["last_test_error"] is None
        assert result["last_review_issues"] is None

    def test_no_commits_error(self, mocker):
        _mock_git_log(mocker, "", returncode=1)
        result = fetch_git_state("eng-1-test")
        assert result["iterations"] == []

    def test_single_commit_with_lisa_trailers(self, mocker):
        body = "feat(lisa): [ENG-1] step 1\n\nLisa-Iteration: 3\nLisa-Test-Error: some error\nLisa-Review-Issues: none\n\x00"
        _mock_git_log(mocker, body)
        result = fetch_git_state("eng-1-test")
        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["iteration"] == 3
        assert result["last_test_error"] == "some error"
        assert result["last_review_issues"] is None

    def test_legacy_tralph_trailers(self, mocker):
        body = "feat(tralph): [ENG-1] step 1\n\nTralph-Iteration: 2\nTralph-Test-Error: none\n\x00"
        _mock_git_log(mocker, body)
        result = fetch_git_state("eng-1-test")
        assert len(result["iterations"]) == 1
        assert result["iterations"][0]["iteration"] == 2
        assert result["last_test_error"] is None  # "none" → None

    def test_multiple_commits_limited_to_3(self, mocker):
        commits = []
        for i in range(5):
            commits.append(f"feat(lisa): [ENG-1] step {i}\n\nLisa-Iteration: {i}\n")
        body = "\x00".join(commits) + "\x00"
        _mock_git_log(mocker, body)
        result = fetch_git_state("eng-1-test")
        assert len(result["iterations"]) == 3

    def test_last_test_error_only_from_first(self, mocker):
        body = (
            "feat(lisa): [ENG-1] step 2\n\nLisa-Iteration: 2\nLisa-Test-Error: none\n\x00"
            "feat(lisa): [ENG-1] step 1\n\nLisa-Iteration: 1\nLisa-Test-Error: old error\n\x00"
        )
        _mock_git_log(mocker, body)
        result = fetch_git_state("eng-1-test")
        # "none" in first commit → None
        assert result["last_test_error"] is None

    def test_none_values_mapped(self, mocker):
        body = "feat(lisa): [ENG-1] step 1\n\nLisa-Iteration: 1\nLisa-Test-Error: none\nLisa-Review-Issues: none\n\x00"
        _mock_git_log(mocker, body)
        result = fetch_git_state("eng-1-test")
        assert result["last_test_error"] is None
        assert result["last_review_issues"] is None

    def test_git_failure_defaults(self, mocker):
        _mock_git_log(mocker, "", returncode=128)
        result = fetch_git_state("eng-1-test")
        assert result == {"iterations": [], "last_test_error": None, "last_review_issues": None}
