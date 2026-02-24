"""Tests for lisa.phases.verify."""

import json
import subprocess

from lisa.models.core import Assumption
from lisa.models.results import TestFailure
from lisa.models.state import RunConfig
from lisa.phases.verify import (
    run_completion_check,
    run_coverage_fix_phase,
    run_coverage_gate,
    run_fix_phase,
    run_format_phase,
    run_review_phase,
    run_setup,
    run_test_fix_phase,
    run_test_phase,
    should_run_command,
    try_pr_review_skill,
    verify_step,
)


class TestShouldRunCommand:
    def test_no_paths_always_runs(self):
        assert should_run_command({"run": "test"}, ["src/foo.py"]) is True

    def test_matching_path(self):
        cmd = {"run": "test", "paths": ["**/*.py"]}
        assert should_run_command(cmd, ["src/foo.py"]) is True

    def test_non_matching_path(self):
        cmd = {"run": "test", "paths": ["**/*.kt"]}
        assert should_run_command(cmd, ["src/foo.py"]) is False

    def test_empty_changed_files(self):
        cmd = {"run": "test", "paths": ["**/*.py"]}
        assert should_run_command(cmd, []) is False

    def test_brace_expansion(self):
        cmd = {"run": "test", "paths": ["**/*.{py,kt}"]}
        assert should_run_command(cmd, ["src/foo.py"]) is True
        assert should_run_command(cmd, ["src/foo.kt"]) is True
        assert should_run_command(cmd, ["src/foo.js"]) is False


class TestRunSetup:
    def test_no_commands(self, mocker):
        mocker.patch("lisa.phases.verify.get_config", return_value={})
        assert run_setup() is True

    def test_success(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"setup": [{"name": "install", "run": "echo ok"}]},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="ok", stderr=""),
        )
        assert run_setup() is True

    def test_failure(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"setup": [{"name": "install", "run": "false"}]},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="error", stderr=""),
        )
        assert run_setup() is False

    def test_timeout(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"setup": [{"name": "slow", "run": "sleep 999"}]},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            side_effect=subprocess.TimeoutExpired("sleep", 300),
        )
        assert run_setup() is False


class TestRunFormatPhase:
    def test_no_commands(self, mocker):
        mocker.patch("lisa.phases.verify.get_config", return_value={})
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        assert run_format_phase() is True

    def test_no_changed_files(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"format": [{"name": "ruff", "run": "ruff format"}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=[])
        assert run_format_phase() is True

    def test_runs_matching_formatter(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"format": [{"name": "ruff", "run": "ruff format", "paths": ["**/*.py"]}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        mock_run = mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert run_format_phase() is True
        mock_run.assert_called_once()

    def test_skips_non_matching(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"format": [{"name": "ktlint", "run": "ktlint", "paths": ["**/*.kt"]}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        assert run_format_phase() is True

    def test_format_failure(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"format": [{"name": "ruff", "run": "ruff format"}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="err", stderr=""),
        )
        assert run_format_phase() is False

    def test_format_timeout(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"format": [{"name": "ruff", "run": "ruff format"}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ruff", 120),
        )
        assert run_format_phase() is False


class TestRunTestPhase:
    def _setup_mocks(self, mocker, test_return_code=0, test_stdout=""):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "test": {"extract_prompt": "extract {output}", "fix_prompt": "fix {output}"}
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas", return_value={"test_extraction": {"type": "object"}}
        )
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"tests": [{"name": "pytest", "run": "pytest"}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], test_return_code, stdout=test_stdout, stderr=""
            ),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")

    def test_all_pass(self, mocker):
        self._setup_mocks(mocker, test_return_code=0)
        result = run_test_phase("task", 0.0, "opus", False, False)
        assert result is None

    def test_failure_extracts(self, mocker):
        self._setup_mocks(mocker, test_return_code=1, test_stdout="FAILED test_foo")
        extraction = json.dumps(
            {
                "passed_count": 0,
                "failed_count": 1,
                "failed_tests": ["test_foo"],
                "extracted_output": "FAILED test_foo",
                "summary": "1 test failed",
            }
        )
        mocker.patch("lisa.phases.verify.claude", return_value=extraction)
        result = run_test_phase("task", 0.0, "opus", False, False)
        assert result is not None
        assert result.command_name == "pytest"
        assert "test_foo" in result.failed_tests

    def test_timeout(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={"test": {"extract_prompt": "extract {output}"}},
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas", return_value={"test_extraction": {"type": "object"}}
        )
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"tests": [{"name": "pytest", "run": "pytest"}]},
        )
        mocker.patch("lisa.phases.verify.get_changed_files", return_value=["src/a.py"])
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pytest", 600),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_test_phase("task", 0.0, "opus", False, False)
        assert result is not None
        assert "Timed out" in result.summary


class TestRunReviewPhase:
    def test_approved_lightweight(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "review_light": {"template": "review {task_title}"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={
                "review_light": {"type": "object"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"approved": True}),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_review_phase(
            "task", "desc", 0.0, "opus", False, False, "low", lightweight=True
        )
        assert result["approved"] is True

    def test_rejected_full(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "review": {
                    "template": "review {task_title} {task_description} {assumptions_section}"
                },
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={
                "review": {"type": "object"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps(
                {
                    "approved": False,
                    "findings": [{"category": "security", "status": "issue", "detail": "XSS"}],
                    "summary": "XSS found",
                }
            ),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_review_phase("task", "desc", 0.0, "opus", False, False, "medium")
        assert result["approved"] is False
        assert "XSS" in result["summary"]

    def test_json_parse_failure(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "review_light": {"template": "review {task_title}"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={
                "review_light": {"type": "object"},
            },
        )
        mocker.patch("lisa.phases.verify.work_claude", return_value="not json")
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_review_phase(
            "task", "desc", 0.0, "opus", False, False, "low", lightweight=True
        )
        assert result["approved"] is False


class TestRunFixPhase:
    def test_calls_work_claude(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "fix": {"template": "fix {issues}"},
            },
        )
        mock_wc = mocker.patch("lisa.phases.verify.work_claude", return_value="fixed")
        mocker.patch("lisa.phases.verify.LiveTimer")
        run_fix_phase("broken", 0.0, "opus", False, False, "low")
        mock_wc.assert_called_once()


class TestRunCompletionCheck:
    def test_complete(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "completion_check": {"template": "check {step_id} {step_desc} {files_context}"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={
                "completion_check": {"type": "object"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"complete": True, "missing": None}),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_completion_check(1, "add handler", [], 0.0, "opus", False, False, "low")
        assert result["complete"] is True

    def test_incomplete(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "completion_check": {"template": "check {step_id} {step_desc} {files_context}"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={
                "completion_check": {"type": "object"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"complete": False, "missing": "tests not added"}),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        result = run_completion_check(1, "add handler", [], 0.0, "opus", False, False, "low")
        assert result["complete"] is False
        assert "tests" in result["missing"]


class TestRunCoverageGate:
    def test_no_coverage_cmd(self, mocker):
        mocker.patch("lisa.phases.verify.get_config", return_value={})
        passed, err = run_coverage_gate(0.0)
        assert passed is True

    def test_pass(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"coverage": {"run": "pytest --cov"}},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="80%", stderr=""),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        passed, err = run_coverage_gate(0.0)
        assert passed is True

    def test_fail(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"coverage": {"run": "pytest --cov"}},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="coverage: 50%", stderr=""),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        passed, err = run_coverage_gate(0.0)
        assert passed is False

    def test_timeout(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_config",
            return_value={"coverage": {"run": "pytest --cov"}},
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pytest", 300),
        )
        mocker.patch("lisa.phases.verify.LiveTimer")
        passed, err = run_coverage_gate(0.0)
        assert passed is False


class TestVerifyStep:
    def test_completion_fail_returns_early(self, mocker):
        mocker.patch(
            "lisa.phases.verify.run_completion_check",
            return_value={"complete": False, "missing": "handler not created"},
        )
        result = verify_step("add handler", "desc", 0.0, "opus", False, False, "high", step_id=1)
        assert result.passed is False
        assert "handler not created" in result.completion_issues[0]

    def test_tests_pass_review_pass(self, mocker):
        mocker.patch("lisa.phases.verify.run_completion_check", return_value={"complete": True})
        mocker.patch("lisa.phases.verify.run_test_phase", return_value=None)
        mocker.patch(
            "lisa.phases.verify.run_review_phase",
            return_value={"approved": True, "summary": "ok", "findings": []},
        )
        result = verify_step("add handler", "desc", 0.0, "opus", False, False, "high", step_id=1)
        assert result.passed is True

    def test_tests_fail_returns_error(self, mocker):
        mocker.patch("lisa.phases.verify.run_completion_check", return_value={"complete": True})
        failure = TestFailure(
            command_name="pytest", output="error", summary="1 failed", failed_tests=[]
        )
        mocker.patch("lisa.phases.verify.run_test_phase", return_value=failure)
        mocker.patch("lisa.phases.verify.run_test_fix_phase")
        result = verify_step("add handler", "desc", 0.0, "opus", False, False, "high", step_id=1)
        assert result.passed is False
        assert result.test_errors


class TestRunTestFixPhase:
    def test_calls_work_claude(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "test": {
                    "fix_prompt": "fix {command_name} {step_desc}"
                    " {task_description} {git_diff} {output}"
                },
            },
        )
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="diff", stderr=""),
        )
        mock_wc = mocker.patch("lisa.phases.verify.work_claude")
        mocker.patch("lisa.phases.verify.LiveTimer")
        failure = TestFailure(command_name="pytest", output="FAILED", summary="error")
        run_test_fix_phase(failure, "step", "desc", 0.0, "opus", False, False, "low")
        mock_wc.assert_called_once()


class TestTryPrReviewSkill:
    def _setup_base(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "final_review": {
                    "template": (
                        "{ticket_id} {title} {description} "
                        "{plan_steps} {assumptions} {subtasks_context} "
                        "{commit_messages}"
                    )
                }
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={"final_review_result": {"type": "object"}},
        )

    def test_skill_available_approved(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout="abc123 ENG-1 feat: thing", stderr=""
            ),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"skill_available": True, "approved": True, "summary": "ok"}),
        )
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], []
        )
        assert result is not None
        assert result["approved"] is True

    def test_skill_unavailable(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"skill_available": False}),
        )
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], []
        )
        assert result is None

    def test_json_error(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        mocker.patch("lisa.phases.verify.work_claude", return_value="not json")
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], []
        )
        assert result is None

    def test_with_assumptions_and_plan_steps(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="abc ENG-1 feat", stderr=""),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps(
                {"skill_available": True, "approved": False, "summary": "issues"}
            ),
        )
        assumptions = [Assumption(id="P.1", selected=True, statement="Use Redis")]
        plan_steps = [{"id": 1, "description": "Setup"}]
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", assumptions, plan_steps, []
        )
        assert result is not None
        assert result["approved"] is False

    def test_with_subtasks(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="abc ENG-1 feat", stderr=""),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"skill_available": True, "approved": True, "summary": "ok"}),
        )
        subtasks = [{"identifier": "ENG-2", "title": "Sub", "description": "Sub desc"}]
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], subtasks
        )
        assert result is not None

    def test_git_log_failure(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="error"),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"skill_available": True, "approved": True, "summary": "ok"}),
        )
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], []
        )
        assert result is not None

    def test_subprocess_exception(self, mocker):
        self._setup_base(mocker)
        mocker.patch(
            "lisa.phases.verify.subprocess.run",
            side_effect=Exception("boom"),
        )
        mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"skill_available": True, "approved": True, "summary": "ok"}),
        )
        result = try_pr_review_skill(
            "ENG-1", "Title", "Desc", "opus", False, False, "high", [], [], []
        )
        assert result is not None


class TestRunCoverageFixPhase:
    def test_calls_work_claude(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "coverage_fix": {"template": "fix coverage {changed_files} {error_output}"},
            },
        )
        mock_wc = mocker.patch("lisa.phases.verify.work_claude", return_value="done")
        mocker.patch("lisa.phases.verify.LiveTimer")
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        run_coverage_fix_phase(["src/a.py"], "coverage 60%", 0.0, config)
        mock_wc.assert_called_once()

    def test_empty_inputs(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "coverage_fix": {"template": "fix coverage {changed_files} {error_output}"},
            },
        )
        mock_wc = mocker.patch("lisa.phases.verify.work_claude", return_value="done")
        mocker.patch("lisa.phases.verify.LiveTimer")
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        run_coverage_fix_phase([], "", 0.0, config)
        mock_wc.assert_called_once()


class TestRunCompletionCheckWithStepFiles:
    def _setup(self, mocker):
        mocker.patch(
            "lisa.phases.verify.get_prompts",
            return_value={
                "completion_check": {"template": "check {step_id} {step_desc} {files_context}"},
            },
        )
        mocker.patch(
            "lisa.phases.verify.get_schemas",
            return_value={"completion_check": {"type": "object"}},
        )
        mocker.patch("lisa.phases.verify.LiveTimer")

    def test_with_files(self, mocker):
        self._setup(mocker)
        mock_wc = mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"complete": True, "missing": None}),
        )
        step_files = [
            {
                "op": "create",
                "path": "src/handler.py",
                "template": "rest_handler",
                "detail": "new route",
            },
        ]
        result = run_completion_check(
            1, "add handler", step_files, 0.0, "opus", False, False, "low"
        )
        assert result["complete"] is True
        # Verify files context was formatted into the prompt
        prompt_arg = mock_wc.call_args[0][0]
        assert "CREATE" in prompt_arg
        assert "src/handler.py" in prompt_arg
        assert "template: rest_handler" in prompt_arg
        assert "detail: new route" in prompt_arg

    def test_files_without_extras(self, mocker):
        self._setup(mocker)
        mock_wc = mocker.patch(
            "lisa.phases.verify.work_claude",
            return_value=json.dumps({"complete": True, "missing": None}),
        )
        step_files = [{"op": "modify", "path": "src/routes.py"}]
        run_completion_check(1, "update routes", step_files, 0.0, "opus", False, False, "low")
        prompt_arg = mock_wc.call_args[0][0]
        assert "MODIFY" in prompt_arg
        assert "src/routes.py" in prompt_arg
