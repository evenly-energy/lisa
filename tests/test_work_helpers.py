"""Tests for lisa.phases.work helper functions."""

from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import WorkState
from lisa.phases.work import (
    display_assumptions,
    format_exploration_context,
    format_step_files,
    handle_assumptions,
    handle_check_completion,
    handle_select_step,
    log_step_files,
)


class TestFormatExplorationContext:
    def test_none_and_empty(self):
        assert format_exploration_context(None, []) == ""

    def test_patterns(self):
        exploration = ExplorationFindings(patterns=["REST handler", "middleware"])
        result = format_exploration_context(exploration, [])
        assert "Patterns to follow:" in result
        assert "REST handler" in result

    def test_similar_impls(self):
        exploration = ExplorationFindings(
            similar_implementations=[{"file": "src/api/users.py", "relevance": "CRUD handler"}]
        )
        result = format_exploration_context(exploration, [])
        assert "Reference files:" in result
        assert "src/api/users.py" in result

    def test_planning_assumptions_only(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis"),
            Assumption(id="P.2", selected=False, statement="Rejected"),
        ]
        result = format_exploration_context(None, assumptions)
        assert "Planning Decisions" in result
        assert "Use Redis" in result
        assert "Rejected" not in result  # Only selected shown

    def test_work_assumptions_excluded(self):
        assumptions = [
            Assumption(id="1.1", selected=True, statement="Work thing"),
        ]
        result = format_exploration_context(None, assumptions)
        # 1.x assumptions not in planning decisions section
        assert "1.1" not in result

    def test_full_context(self):
        exploration = ExplorationFindings(
            patterns=["pattern"],
            relevant_modules=["src/api/"],
            similar_implementations=[{"file": "f.py", "relevance": "similar"}],
        )
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Decision A"),
        ]
        result = format_exploration_context(exploration, assumptions)
        assert "Exploration Context" in result
        assert "Planning Decisions" in result
        assert "pattern" in result
        assert "Decision A" in result


class TestFormatStepFiles:
    def test_empty(self):
        assert format_step_files([]) == ""

    def test_single_create(self):
        files = [{"op": "create", "path": "src/new.py"}]
        result = format_step_files(files)
        assert "CREATE: src/new.py" in result

    def test_with_template_and_detail(self):
        files = [
            {"op": "create", "path": "src/new.py", "template": "handler", "detail": "REST API"}
        ]
        result = format_step_files(files)
        assert "template: handler" in result
        assert "detail: REST API" in result

    def test_multiple_files(self):
        files = [
            {"op": "create", "path": "src/a.py"},
            {"op": "modify", "path": "src/b.py"},
        ]
        result = format_step_files(files)
        assert "CREATE: src/a.py" in result
        assert "MODIFY: src/b.py" in result


class TestHandleSelectStep:
    def test_all_done(self, sample_work_context):
        for s in sample_work_context.plan_steps:
            s["done"] = True
        assert handle_select_step(sample_work_context) == WorkState.ALL_DONE

    def test_selects_first_incomplete(self, sample_work_context):
        # step 1 done, step 2 not done
        state = handle_select_step(sample_work_context)
        assert state == WorkState.EXECUTE_WORK
        assert sample_work_context.current_step == 2

    def test_sets_step_desc(self, sample_work_context):
        handle_select_step(sample_work_context)
        assert sample_work_context.step_desc == "Implement endpoint"

    def test_sets_commit_ticket(self, sample_work_context):
        handle_select_step(sample_work_context)
        assert sample_work_context.commit_ticket == "ENG-72"

    def test_logs_test_error(self, sample_work_context, capsys):
        sample_work_context.last_test_error = "AssertionError in test_foo"
        handle_select_step(sample_work_context)
        out = capsys.readouterr().out
        assert "Fixing:" in out

    def test_logs_completion_issues(self, sample_work_context, capsys):
        sample_work_context.last_completion_issues = "Missing endpoint"
        handle_select_step(sample_work_context)
        out = capsys.readouterr().out
        assert "Incomplete:" in out

    def test_logs_review_issues(self, sample_work_context, capsys):
        sample_work_context.last_review_issues = "No error handling"
        handle_select_step(sample_work_context)
        out = capsys.readouterr().out
        assert "Fixing:" in out


class TestHandleAssumptions:
    def test_no_assumptions(self, sample_work_context):
        sample_work_context.work_result = {"assumptions": []}
        state = handle_assumptions(sample_work_context)
        assert state == WorkState.CHECK_COMPLETION
        assert sample_work_context.assumptions == []

    def test_extracts_assumptions(self, sample_work_context):
        sample_work_context.work_result = {
            "assumptions": [
                {"id": "1", "selected": True, "statement": "Use cache", "rationale": "Fast"},
            ]
        }
        sample_work_context.loop_iter = 2
        state = handle_assumptions(sample_work_context)
        assert state == WorkState.CHECK_COMPLETION
        assert len(sample_work_context.assumptions) == 1
        assert sample_work_context.assumptions[0].id == "2.1"  # iteration.index

    def test_accumulates_all_assumptions(self, sample_work_context):
        sample_work_context.work_result = {
            "assumptions": [
                {"id": "1", "selected": True, "statement": "A"},
                {"id": "2", "selected": False, "statement": "B"},
            ]
        }
        handle_assumptions(sample_work_context)
        assert len(sample_work_context.all_assumptions) == 2


class TestHandleCheckCompletion:
    def test_blocked_records_manual_action(self, sample_work_context):
        sample_work_context.work_result = {"blocked": "Need API key"}
        state = handle_check_completion(sample_work_context)
        assert state == WorkState.COMMIT_CHANGES
        manuals = [a for a in sample_work_context.assumptions if "MANUAL:" in a.statement]
        assert len(manuals) == 1

    def test_step_in_progress(self, sample_work_context):
        sample_work_context.work_result = {"step_done": None}
        state = handle_check_completion(sample_work_context)
        assert state == WorkState.COMMIT_CHANGES
        assert not sample_work_context.step_done

    def test_wrong_step_completed(self, sample_work_context):
        sample_work_context.current_step = 2
        sample_work_context.work_result = {"step_done": 99}
        state = handle_check_completion(sample_work_context)
        assert state == WorkState.COMMIT_CHANGES

    def test_step_completed(self, sample_work_context, mocker):
        mocker.patch("lisa.phases.work.get_diff_summary", return_value="2 files changed")
        sample_work_context.current_step = 2
        sample_work_context.iter_state = {"step_elapsed": "0:30"}
        sample_work_context.work_result = {"step_done": 2}
        state = handle_check_completion(sample_work_context)
        assert state == WorkState.VERIFY_STEP
        assert sample_work_context.step_done


class TestLogStepFiles:
    def test_empty(self, capsys):
        log_step_files([])
        assert capsys.readouterr().out == ""

    def test_logs_operations(self, capsys):
        files = [
            {"op": "create", "path": "src/new.py"},
            {"op": "modify", "path": "src/old.py", "detail": "add route"},
        ]
        log_step_files(files)
        out = capsys.readouterr().out
        assert "CREATE" in out
        assert "MODIFY" in out
        assert "add route" in out


class TestDisplayAssumptions:
    def test_empty(self, capsys):
        display_assumptions([])
        assert capsys.readouterr().out == ""

    def test_shows_selected_marker(self, capsys):
        assumptions = [
            Assumption(id="1.1", selected=True, statement="Use cache"),
            Assumption(id="1.2", selected=False, statement="Skip tests", rationale="Too slow"),
        ]
        display_assumptions(assumptions)
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "[ ]" in out
        assert "Use cache" in out
        assert "Too slow" in out
