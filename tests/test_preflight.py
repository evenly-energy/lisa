"""Tests for preflight functionality."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from lisa.phases.verify import run_preflight


@pytest.fixture
def mock_config():
    """Mock get_config for test isolation."""
    with patch("lisa.phases.verify.get_config") as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for test isolation."""
    with patch("lisa.phases.verify.subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="")
        yield mock


def test_preflight_runs_all_tests_by_default(mock_config, mock_subprocess):
    """Test that preflight runs all test commands when preflight property is not set."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1"},
            {"name": "Test 2", "run": "test2"},
        ]
    }

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 2
    # Order not guaranteed with parallel execution
    calls = {call[0][0] for call in mock_subprocess.call_args_list}
    assert calls == {"test1", "test2"}


def test_preflight_respects_explicit_true(mock_config, mock_subprocess):
    """Test that preflight runs commands with explicit preflight: true."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1", "preflight": True},
            {"name": "Test 2", "run": "test2", "preflight": True},
        ]
    }

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 2


def test_preflight_skips_false_commands(mock_config, mock_subprocess):
    """Test that preflight skips commands with preflight: false."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1", "preflight": True},
            {"name": "Test 2", "run": "test2", "preflight": False},
            {"name": "Test 3", "run": "test3"},  # default: true
        ]
    }

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 2
    # Order not guaranteed with parallel execution
    calls = {call[0][0] for call in mock_subprocess.call_args_list}
    assert calls == {"test1", "test3"}


def test_preflight_with_no_commands(mock_config, mock_subprocess):
    """Test that preflight succeeds when no commands are configured."""
    mock_config.return_value = {"tests": []}

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 0


def test_preflight_with_all_skipped(mock_config, mock_subprocess):
    """Test that preflight succeeds when all commands are skipped."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1", "preflight": False},
            {"name": "Test 2", "run": "test2", "preflight": False},
        ]
    }

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 0


def test_preflight_fails_on_command_failure(mock_config, mock_subprocess):
    """Test that preflight returns False when a command fails. Both commands still run."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1"},
            {"name": "Test 2", "run": "test2"},
        ]
    }
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="Error occurred")

    result = run_preflight()

    assert result is False
    assert mock_subprocess.call_count == 2  # Both run in parallel


def test_preflight_fails_on_timeout(mock_config, mock_subprocess):
    """Test that preflight returns False when a command times out."""
    mock_config.return_value = {"tests": [{"name": "Test 1", "run": "test1"}]}
    mock_subprocess.side_effect = subprocess.TimeoutExpired("test1", 120)

    result = run_preflight()

    assert result is False


def test_preflight_does_not_run_format_commands(mock_config, mock_subprocess):
    """Test that preflight no longer runs format commands."""
    mock_config.return_value = {
        "tests": [{"name": "Test 1", "run": "test1"}],
        "format": [{"name": "Format 1", "run": "format1"}],
    }

    result = run_preflight()

    assert result is True
    assert mock_subprocess.call_count == 1
    calls = [call[0][0] for call in mock_subprocess.call_args_list]
    assert calls[0] == "test1"


def test_preflight_reports_all_failures(mock_config, mock_subprocess):
    """Test that all failures are reported when multiple commands fail."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1"},
            {"name": "Test 2", "run": "test2"},
        ]
    }
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="fail")

    result = run_preflight()

    assert result is False
    assert mock_subprocess.call_count == 2


def test_preflight_mixed_pass_fail(mock_config, mock_subprocess):
    """Test that one pass + one fail = overall fail, both ran."""
    mock_config.return_value = {
        "tests": [
            {"name": "Test 1", "run": "test1"},
            {"name": "Test 2", "run": "test2"},
        ]
    }

    def side_effect(cmd, **kwargs):
        if cmd == "test1":
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=1, stdout="Error")

    mock_subprocess.side_effect = side_effect

    result = run_preflight()

    assert result is False
    assert mock_subprocess.call_count == 2
