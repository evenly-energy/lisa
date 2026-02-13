"""Tests for lisa.phases.work helper functions."""

from lisa.models.core import Assumption, ExplorationFindings
from lisa.phases.work import format_exploration_context, format_step_files


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
