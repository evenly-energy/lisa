"""Tests for heavy work.py handlers: execute, verify, commit, save, final_review."""

import json
import time

from lisa.models.results import VerifyResult
from lisa.models.state import RunConfig, WorkContext, WorkState
from lisa.phases.work import (
    handle_commit_changes,
    handle_execute_work,
    handle_final_review,
    handle_max_iterations,
    handle_save_state,
    handle_verify_step,
)


def _make_ctx(**overrides):
    """Build WorkContext with defaults, overriding specified fields."""
    defaults = dict(
        ticket_id="ENG-1",
        title="Test",
        description="Desc",
        issue_uuid="uuid",
        issue_url="https://linear.app/ENG-1",
        branch_name="eng-1-test",
        subtasks=[],
        plan_steps=[
            {"id": 1, "description": "Step one", "done": False, "ticket": "ENG-1"},
        ],
        all_assumptions=[],
        assumptions=[],
        exploration=None,
        state_iteration=0,
        loop_iter=1,
        iter_start=time.time(),
        total_start=time.time(),
        current_step=1,
        step_desc="Step one",
        commit_ticket="ENG-1",
        work_result=None,
        last_test_error=None,
        last_review_issues=None,
        last_completion_issues=None,
        iter_state={"files_before": set()},
        tests_passed=True,
        step_done=False,
        review_status="skipped",
        comment_id=None,
        log_entries=[],
        config=RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus"),
    )
    defaults.update(overrides)
    return WorkContext(**defaults)


class TestHandleExecuteWork:
    def test_calls_work_claude_and_parses(self, mocker):
        mocker.patch(
            "lisa.phases.work.get_prompts",
            return_value={
                "work": {
                    "template": "{ticket_id}{title}{description}{exploration_context}"
                    "{files_context}{subtask_context}{prior_context}{iteration_context}"
                    "{plan_checklist}{current_step}{step_desc}"
                },
            },
        )
        mocker.patch("lisa.phases.work.get_schemas", return_value={"work": {}})
        mocker.patch("lisa.phases.work.get_changed_files", return_value=[])
        mocker.patch("lisa.phases.work.fetch_git_state", return_value={})
        work_output = json.dumps({"step_done": 1, "assumptions": []})
        mocker.patch("lisa.phases.work.work_claude", return_value=work_output)
        mocker.patch("lisa.phases.work.LiveTimer")

        ctx = _make_ctx()
        state = handle_execute_work(ctx)
        assert state == WorkState.HANDLE_ASSUMPTIONS
        assert ctx.work_result["step_done"] == 1

    def test_json_parse_error_exits(self, mocker):
        mocker.patch(
            "lisa.phases.work.get_prompts",
            return_value={
                "work": {
                    "template": "{ticket_id}{title}{description}{exploration_context}"
                    "{files_context}{subtask_context}{prior_context}{iteration_context}"
                    "{plan_checklist}{current_step}{step_desc}"
                },
            },
        )
        mocker.patch("lisa.phases.work.get_schemas", return_value={"work": {}})
        mocker.patch("lisa.phases.work.get_changed_files", return_value=[])
        mocker.patch("lisa.phases.work.fetch_git_state", return_value={})
        mocker.patch("lisa.phases.work.work_claude", return_value="not json{{{")
        mocker.patch("lisa.phases.work.LiveTimer")

        ctx = _make_ctx()
        import pytest

        with pytest.raises(SystemExit):
            handle_execute_work(ctx)

    def test_includes_test_error_context(self, mocker):
        mocker.patch(
            "lisa.phases.work.get_prompts",
            return_value={
                "work": {
                    "template": "{ticket_id}{title}{description}{exploration_context}"
                    "{files_context}{subtask_context}{prior_context}{iteration_context}"
                    "{plan_checklist}{current_step}{step_desc}"
                },
            },
        )
        mocker.patch("lisa.phases.work.get_schemas", return_value={"work": {}})
        mocker.patch("lisa.phases.work.get_changed_files", return_value=[])
        mocker.patch("lisa.phases.work.fetch_git_state", return_value={})
        mock_wc = mocker.patch(
            "lisa.phases.work.work_claude",
            return_value=json.dumps({"step_done": None, "assumptions": []}),
        )
        mocker.patch("lisa.phases.work.LiveTimer")

        ctx = _make_ctx(last_test_error="AssertionError in test_foo")
        handle_execute_work(ctx)
        prompt = mock_wc.call_args[0][0]
        assert "AssertionError" in prompt


class TestHandleVerifyStep:
    def test_skip_verify(self, mocker):
        config = RunConfig(
            ticket_ids=["ENG-1"],
            max_iterations=10,
            effort="high",
            model="opus",
            skip_verify=True,
        )
        ctx = _make_ctx(config=config, step_desc="Step one", current_step=1)
        state = handle_verify_step(ctx)
        assert state == WorkState.COMMIT_CHANGES
        assert ctx.tests_passed is True
        assert ctx.plan_steps[0]["done"] is True

    def test_verify_passes(self, mocker):
        mocker.patch(
            "lisa.phases.work.verify_step",
            return_value=VerifyResult(passed=True),
        )
        ctx = _make_ctx()
        state = handle_verify_step(ctx)
        assert state == WorkState.COMMIT_CHANGES
        assert ctx.tests_passed is True
        assert ctx.plan_steps[0]["done"] is True

    def test_verify_fails_retries(self, mocker):
        mocker.patch(
            "lisa.phases.work.verify_step",
            return_value=VerifyResult(passed=False, test_errors=["test failed"]),
        )
        ctx = _make_ctx(verify_attempts=0, max_verify_attempts=3)
        state = handle_verify_step(ctx)
        assert state == WorkState.EXECUTE_WORK  # retry
        assert ctx.verify_attempts == 1

    def test_verify_fails_exhausted(self, mocker):
        mocker.patch(
            "lisa.phases.work.verify_step",
            return_value=VerifyResult(passed=False, test_errors=["err"]),
        )
        ctx = _make_ctx(verify_attempts=2, max_verify_attempts=3)
        state = handle_verify_step(ctx)
        assert state == WorkState.COMMIT_CHANGES  # commit with FAIL
        assert "tests failed" in ctx.review_status

    def test_completion_issues_retry(self, mocker):
        mocker.patch(
            "lisa.phases.work.verify_step",
            return_value=VerifyResult(passed=False, completion_issues=["handler missing"]),
        )
        ctx = _make_ctx(verify_attempts=0, max_verify_attempts=3)
        state = handle_verify_step(ctx)
        assert state == WorkState.EXECUTE_WORK
        assert ctx.last_completion_issues == "handler missing"


class TestHandleCommitChanges:
    def test_no_changes(self, mocker):
        mocker.patch("lisa.phases.work.get_changed_files", return_value=[])
        ctx = _make_ctx(iter_state={"files_before": set()})
        state = handle_commit_changes(ctx)
        assert state == WorkState.SAVE_STATE

    def test_commits_changes(self, mocker):
        mocker.patch(
            "lisa.phases.work.get_changed_files",
            side_effect=[
                ["src/a.py"],  # files_after
                ["src/a.py"],  # files after format
            ],
        )
        mocker.patch("lisa.phases.work.run_format_phase")
        mocker.patch("lisa.phases.work.summarize_for_commit", return_value="add handler")
        mocker.patch("lisa.phases.work.git_commit", return_value=True)

        ctx = _make_ctx(
            iter_state={"files_before": set()},
            step_desc="Add handler",
            tests_passed=True,
        )
        state = handle_commit_changes(ctx)
        assert state == WorkState.SAVE_STATE

    def test_commit_failure(self, mocker):
        mocker.patch(
            "lisa.phases.work.get_changed_files",
            side_effect=[
                ["src/a.py"],
                ["src/a.py"],
            ],
        )
        mocker.patch("lisa.phases.work.run_format_phase")
        mocker.patch("lisa.phases.work.summarize_for_commit", return_value="fix")
        mocker.patch("lisa.phases.work.git_commit", return_value=False)

        ctx = _make_ctx(iter_state={"files_before": set()}, step_desc="Fix")
        handle_commit_changes(ctx)
        # Should warn but continue


class TestHandleSaveState:
    def test_saves_state(self, mocker):
        mocker.patch("lisa.phases.work.save_state", return_value="comment-id")
        mocker.patch("lisa.phases.work.LiveTimer")

        ctx = _make_ctx(step_done=True, tests_passed=True)
        state = handle_save_state(ctx)
        assert state == WorkState.SELECT_STEP
        assert ctx.comment_id == "comment-id"

    def test_no_branch_skips_save(self, mocker):
        ctx = _make_ctx(branch_name="", issue_uuid="")
        state = handle_save_state(ctx)
        assert state == WorkState.SELECT_STEP


class TestHandleFinalReview:
    def test_approved_first_try(self, mocker):
        mocker.patch(
            "lisa.phases.work.try_pr_review_skill",
            return_value={
                "skill_available": True,
                "approved": True,
                "summary": "LGTM",
            },
        )
        ctx = _make_ctx()
        state = handle_final_review(ctx)
        assert state == WorkState.ALL_DONE
        assert ctx.final_review_status == "APPROVED"

    def test_fallback_to_standard_review(self, mocker):
        mocker.patch("lisa.phases.work.try_pr_review_skill", return_value=None)
        mocker.patch(
            "lisa.phases.work.run_review_phase",
            return_value={
                "approved": True,
                "summary": "ok",
                "findings": [],
            },
        )
        ctx = _make_ctx()
        state = handle_final_review(ctx)
        assert state == WorkState.ALL_DONE
        assert ctx.final_review_status == "APPROVED"

    def test_only_minor_items(self, mocker):
        mocker.patch(
            "lisa.phases.work.try_pr_review_skill",
            return_value={
                "skill_available": True,
                "approved": False,
                "action_items": [{"priority": "minor", "action": "add docstring"}],
                "summary": "minor only",
            },
        )
        ctx = _make_ctx()
        state = handle_final_review(ctx)
        assert state == WorkState.ALL_DONE
        assert "minor items skipped" in ctx.final_review_status

    def test_repeated_issue_exits(self, mocker):
        # Returns same non-approved result 3 times (MAX_ISSUE_REPEATS)
        mocker.patch(
            "lisa.phases.work.try_pr_review_skill",
            return_value={
                "skill_available": True,
                "approved": False,
                "action_items": [{"priority": "critical", "action": "fix XSS"}],
                "summary": "XSS found",
            },
        )
        mocker.patch("lisa.phases.work.run_fix_phase")
        mocker.patch("lisa.phases.work.run_test_phase", return_value=None)
        mocker.patch("lisa.phases.work.run_format_phase")
        mocker.patch("lisa.phases.work.get_changed_files", return_value=["x.py"])
        mocker.patch("lisa.phases.work.git_commit", return_value=True)
        ctx = _make_ctx()
        state = handle_final_review(ctx)
        assert state == WorkState.ALL_DONE
        assert "repeated" in (ctx.final_review_status or "")


class TestHandleMaxIterations:
    def test_prints_warning(self, capsys):
        ctx = _make_ctx()
        handle_max_iterations(ctx)
        out = capsys.readouterr().out
        assert "Max iterations" in out

    def test_shows_manual_actions(self, capsys):
        from lisa.models.core import Assumption

        ctx = _make_ctx(
            all_assumptions=[
                Assumption(id="1", selected=False, statement="MANUAL: Deploy to staging"),
            ]
        )
        handle_max_iterations(ctx)
        out = capsys.readouterr().out
        assert "Deploy to staging" in out
