"""Tests for lisa.phases.planning."""

import json

from lisa.models.state import RunConfig
from lisa.phases.planning import run_planning_phase, sort_by_dependencies


class TestSortByDependencies:
    def test_empty(self):
        assert sort_by_dependencies([]) == []

    def test_no_deps(self):
        tasks = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        result = sort_by_dependencies(tasks)
        assert [t["id"] for t in result] == ["A", "B", "C"]

    def test_single_dep(self):
        tasks = [
            {"id": "B", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids.index("A") < ids.index("B")

    def test_chain(self):
        tasks = [
            {"id": "C", "blockedBy": ["B"]},
            {"id": "B", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids == ["A", "B", "C"]

    def test_diamond(self):
        tasks = [
            {"id": "D", "blockedBy": ["B", "C"]},
            {"id": "B", "blockedBy": ["A"]},
            {"id": "C", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids.index("A") < ids.index("B")
        assert ids.index("A") < ids.index("C")
        assert ids.index("B") < ids.index("D")
        assert ids.index("C") < ids.index("D")

    def test_cycle_handled(self):
        tasks = [
            {"id": "A", "blockedBy": ["B"]},
            {"id": "B", "blockedBy": ["A"]},
        ]
        result = sort_by_dependencies(tasks)
        # Should not hang; all tasks returned
        assert len(result) == 2

    def test_external_dep_ignored(self):
        tasks = [
            {"id": "A", "blockedBy": ["EXTERNAL"]},
            {"id": "B"},
        ]
        result = sort_by_dependencies(tasks)
        # EXTERNAL not in subtask ids, so A is not blocked
        assert len(result) == 2

    def test_order_preserved_for_equal_priority(self):
        tasks = [{"id": "X"}, {"id": "Y"}, {"id": "Z"}]
        result = sort_by_dependencies(tasks)
        assert [t["id"] for t in result] == ["X", "Y", "Z"]

    def test_blocked_by_temp_field_cleaned(self):
        tasks = [{"id": "A"}, {"id": "B", "blockedBy": ["A"]}]
        result = sort_by_dependencies(tasks)
        for t in result:
            assert "_blocked_by" not in t


class TestRunPlanningPhase:
    def _mock_planning(self, mocker, output):
        mocker.patch(
            "lisa.phases.planning.get_prompts",
            return_value={
                "planning": {
                    "template": "{ticket_id} {title} {description} {subtask_list} {example_subtask}"
                },
            },
        )
        mocker.patch(
            "lisa.phases.planning.get_schemas",
            return_value={
                "planning": {"type": "object"},
            },
        )
        mocker.patch("lisa.phases.planning.work_claude", return_value=output)
        mocker.patch("lisa.phases.planning.LiveTimer")

    def test_parses_steps_and_assumptions(self, mocker):
        output = json.dumps(
            {
                "steps": [
                    {"id": 1, "ticket": "ENG-1", "description": "Setup config"},
                    {"id": 2, "ticket": "ENG-1", "description": "Add handler"},
                ],
                "assumptions": [
                    {"id": "1", "selected": True, "statement": "Use Redis", "rationale": "fast"},
                ],
                "exploration": {
                    "patterns": ["REST handler"],
                    "relevant_modules": ["src/api/"],
                    "similar_implementations": [{"file": "src/api/users.py", "relevance": "CRUD"}],
                },
            }
        )
        self._mock_planning(mocker, output)
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        steps, assumptions, exploration = run_planning_phase(
            "ENG-1",
            "Title",
            "Desc",
            [],
            0.0,
            "opus",
            False,
            False,
            config,
        )
        assert len(steps) == 2
        assert steps[0]["description"] == "Setup config"
        assert len(assumptions) == 1
        assert assumptions[0].statement == "Use Redis"
        assert exploration is not None
        assert "REST handler" in exploration.patterns

    def test_json_parse_error_returns_empty(self, mocker):
        self._mock_planning(mocker, "not valid json{{{")
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        steps, assumptions, exploration = run_planning_phase(
            "ENG-1",
            "Title",
            "Desc",
            [],
            0.0,
            "opus",
            False,
            False,
            config,
        )
        assert steps == []
        assert assumptions == []
        assert exploration is None

    def test_no_exploration(self, mocker):
        output = json.dumps(
            {"steps": [{"id": 1, "ticket": "ENG-1", "description": "Do"}], "assumptions": []}
        )
        self._mock_planning(mocker, output)
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        steps, assumptions, exploration = run_planning_phase(
            "ENG-1",
            "Title",
            "Desc",
            [],
            0.0,
            "opus",
            False,
            False,
            config,
        )
        assert len(steps) == 1
        assert exploration is None

    def test_with_subtasks(self, mocker):
        output = json.dumps(
            {"steps": [{"id": 1, "ticket": "ENG-2", "description": "Sub work"}], "assumptions": []}
        )
        self._mock_planning(mocker, output)
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        subtasks = [{"id": "ENG-2", "title": "Subtask"}]
        steps, _, _ = run_planning_phase(
            "ENG-1",
            "Title",
            "Desc",
            subtasks,
            0.0,
            "opus",
            False,
            False,
            config,
        )
        assert steps[0]["ticket"] == "ENG-2"

    def test_with_prior_assumptions(self, mocker):
        from lisa.models.core import Assumption

        output = json.dumps(
            {"steps": [{"id": 1, "ticket": "ENG-1", "description": "Redo"}], "assumptions": []}
        )
        self._mock_planning(mocker, output)
        mock_wc = mocker.patch("lisa.phases.planning.work_claude", return_value=output)
        config = RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="opus")
        prior = [Assumption(id="P.1", selected=True, statement="Use Redis")]
        run_planning_phase(
            "ENG-1",
            "Title",
            "Desc",
            [],
            0.0,
            "opus",
            False,
            False,
            config,
            prior_assumptions=prior,
        )
        # Verify prompt includes prior assumptions
        prompt_arg = mock_wc.call_args[0][0]
        assert "Use Redis" in prompt_arg
