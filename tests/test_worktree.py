"""Tests for lisa.git.worktree."""

import subprocess

from lisa.git.worktree import create_session_worktree, remove_worktree


class TestCreateSessionWorktree:
    def test_creates_worktree(self, mocker):
        mocker.patch("lisa.git.worktree.os.path.exists", return_value=False)
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = create_session_worktree("test-session")
        assert result == "/tmp/lisa/test-session"

    def test_removes_stale_worktree(self, mocker):
        mocker.patch("lisa.git.worktree.os.path.exists", side_effect=[True, False])
        mock_remove = mocker.patch("lisa.git.worktree.remove_worktree", return_value=True)
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = create_session_worktree("test-session")
        assert result is not None
        mock_remove.assert_called_once()

    def test_stale_cleanup_fails(self, mocker):
        mocker.patch("lisa.git.worktree.os.path.exists", return_value=True)
        mocker.patch("lisa.git.worktree.remove_worktree", return_value=False)
        result = create_session_worktree("test-session")
        assert result is None

    def test_git_worktree_add_fails(self, mocker):
        mocker.patch("lisa.git.worktree.os.path.exists", return_value=False)
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="error"),
        )
        result = create_session_worktree("test-session")
        assert result is None


class TestRemoveWorktree:
    def test_safety_check_empty(self):
        assert remove_worktree("") is False

    def test_safety_check_wrong_prefix(self):
        assert remove_worktree("/home/user/repo") is False

    def test_git_remove_succeeds(self, mocker):
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert remove_worktree("/tmp/lisa/session-123") is True

    def test_fallback_rmtree(self, mocker):
        # git worktree remove fails, but rmtree + metadata cleanup succeeds
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 1, stdout="", stderr="lock"),  # remove fails
                subprocess.CompletedProcess([], 0, stdout="/repo", stderr=""),  # rev-parse
            ],
        )
        mocker.patch("lisa.git.worktree.os.path.exists", side_effect=[True, True])
        mocker.patch("lisa.git.worktree.shutil.rmtree")
        assert remove_worktree("/tmp/lisa/session-123") is True

    def test_fallback_rmtree_oserror(self, mocker):
        mocker.patch(
            "lisa.git.worktree.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 1, stdout="", stderr="err"),
                subprocess.CompletedProcess([], 0, stdout="/repo", stderr=""),
            ],
        )
        mocker.patch("lisa.git.worktree.os.path.exists", side_effect=[True, False])
        mocker.patch("lisa.git.worktree.shutil.rmtree", side_effect=OSError("perm denied"))
        assert remove_worktree("/tmp/lisa/session-123") is False
