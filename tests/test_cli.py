"""Tests for lisa.cli."""

import sys

import pytest

from lisa.cli import (
    log_config,
    parse_args,
    print_review_report,
    show_dry_run_status,
    validate_env,
)
from lisa.models.state import RunConfig


class TestParseArgs:
    def test_single_ticket(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-123"])
        config = parse_args()
        assert config.ticket_ids == ["ENG-123"]
        assert config.max_iterations == 30
        assert config.effort == "high"
        assert config.model == "opus"

    def test_multiple_tickets(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "ENG-2", "ENG-3"])
        config = parse_args()
        assert config.ticket_ids == ["ENG-1", "ENG-2", "ENG-3"]

    def test_max_iterations(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-n", "50"])
        config = parse_args()
        assert config.max_iterations == 50

    def test_dry_run(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--dry-run"])
        config = parse_args()
        assert config.dry_run is True

    def test_push(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-p"])
        config = parse_args()
        assert config.push is True

    def test_model(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-m", "sonnet"])
        config = parse_args()
        assert config.model == "sonnet"

    def test_yolo(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--yolo"])
        config = parse_args()
        assert config.yolo is True

    def test_fallback_tools(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--fallback-tools"])
        config = parse_args()
        assert config.fallback_tools is True

    def test_skip_verify(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--skip-verify"])
        config = parse_args()
        assert config.skip_verify is True

    def test_effort_medium(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--effort", "medium"])
        config = parse_args()
        assert config.effort == "medium"

    def test_skip_plan(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--skip-plan"])
        config = parse_args()
        assert config.skip_plan is True

    def test_interactive(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-i"])
        config = parse_args()
        assert config.interactive is True

    def test_always_interactive(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-I"])
        config = parse_args()
        assert config.always_interactive is True

    def test_debug(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--debug"])
        config = parse_args()
        assert config.debug is True

    def test_review_only(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--review-only"])
        config = parse_args()
        assert config.review_only is True

    def test_conclusion(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "--conclusion"])
        config = parse_args()
        assert config.conclusion is True

    def test_worktree(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-w"])
        config = parse_args()
        assert config.worktree is True

    def test_preflight(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-c"])
        config = parse_args()
        assert config.preflight is True

    def test_spice(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa", "ENG-1", "-s"])
        config = parse_args()
        assert config.spice is True

    def test_combined_flags(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            ["lisa", "ENG-1", "-n", "5", "--yolo", "-p", "--debug", "--effort", "low"],
        )
        config = parse_args()
        assert config.max_iterations == 5
        assert config.yolo is True
        assert config.push is True
        assert config.debug is True
        assert config.effort == "low"

    def test_no_ticket_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["lisa"])
        with pytest.raises(SystemExit):
            parse_args()


class TestValidateEnv:
    def test_env_var_present(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "key")
        validate_env()  # Should not raise

    def test_oauth_token_present(self, monkeypatch, mocker):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        mocker.patch("lisa.auth.get_token", return_value="token")
        validate_env()

    def test_no_auth_exits(self, monkeypatch, mocker):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        mocker.patch("lisa.auth.get_token", return_value=None)
        mocker.patch("builtins.input", return_value="n")
        with pytest.raises(SystemExit):
            validate_env()


class TestLogConfig:
    def _mock_config_deps(self, mocker):
        mocker.patch("lisa.config.prompts.get_prompts", return_value={})
        mocker.patch("lisa.config.settings.get_config", return_value={})
        mocker.patch("lisa.config.prompts.get_loaded_sources", return_value=["defaults"])
        mocker.patch("lisa.config.settings.get_config_loaded_sources", return_value=["defaults"])

    def test_single_ticket(self, capsys, mocker, sample_run_config):
        self._mock_config_deps(mocker)
        log_config(sample_run_config)
        out = capsys.readouterr().out
        assert "ENG-123" in out
        assert "Max iterations" in out

    def test_multi_ticket(self, capsys, mocker):
        config = RunConfig(
            ticket_ids=["ENG-1", "ENG-2"],
            max_iterations=10,
            effort="high",
            model="opus",
        )
        self._mock_config_deps(mocker)
        log_config(config)
        out = capsys.readouterr().out
        assert "2 tickets" in out

    def test_flags_logged(self, capsys, mocker):
        config = RunConfig(
            ticket_ids=["ENG-1"],
            max_iterations=10,
            effort="high",
            model="opus",
            yolo=True,
            skip_verify=True,
            debug=True,
            preflight=True,
            spice=True,
            dry_run=True,
        )
        self._mock_config_deps(mocker)
        log_config(config)
        out = capsys.readouterr().out
        assert "YOLO" in out
        assert "SKIP-VERIFY" in out
        assert "Debug" in out
        assert "DRY RUN" in out


class TestShowDryRunStatus:
    def test_shows_ticket_info(self, capsys, mocker):
        mocker.patch("lisa.cli.list_branches_matching", return_value=["eng-1-foo"])
        mocker.patch("lisa.cli.get_current_branch", return_value="eng-1-foo")
        ticket = {"title": "Fix bug", "description": "Details"}
        plan_steps = [
            {"id": 1, "description": "Step one", "done": True},
            {"id": 2, "description": "Step two", "done": False},
        ]
        with pytest.raises(SystemExit):
            show_dry_run_status("ENG-1", ticket, plan_steps, 2, 3)
        out = capsys.readouterr().out
        assert "Fix bug" in out
        assert "Step one" in out
        assert "1/2 steps done" in out


class TestPrintReviewReport:
    def test_approved(self, capsys):
        result = {
            "approved": True,
            "findings": [{"category": "security", "status": "pass", "detail": "No issues"}],
            "summary": "All good",
        }
        print_review_report(result)
        out = capsys.readouterr().out
        assert "APPROVED" in out
        assert "All good" in out

    def test_rejected(self, capsys):
        result = {
            "approved": False,
            "findings": [{"category": "code", "status": "issue", "detail": "Missing tests"}],
            "summary": "Needs work",
        }
        print_review_report(result)
        out = capsys.readouterr().out
        assert "NEEDS_FIXES" in out
        assert "Missing tests" in out

    def test_no_findings(self, capsys):
        result = {"approved": True, "summary": "Clean"}
        print_review_report(result)
        out = capsys.readouterr().out
        assert "Clean" in out
