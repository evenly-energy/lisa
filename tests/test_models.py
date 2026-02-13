"""Tests for lisa.models.core and lisa.models.results."""

import pytest

from lisa.models.core import Assumption, ExplorationFindings, PlanStep
from lisa.models.results import TokenUsage
from lisa.models.state import RunConfig, WorkContext


class TestPlanStep:
    def test_to_dict(self):
        step = PlanStep(id=1, description="Do thing", ticket="ENG-1", done=True)
        d = step.to_dict()
        assert d == {"id": 1, "description": "Do thing", "ticket": "ENG-1", "done": True}

    def test_from_dict(self):
        step = PlanStep.from_dict({"id": 2, "description": "Another"})
        assert step.id == 2
        assert step.ticket == ""
        assert step.done is False

    def test_defaults(self):
        step = PlanStep(id=1, description="x")
        assert step.ticket == ""
        assert step.done is False

    def test_roundtrip(self):
        original = PlanStep(id=3, description="Test", ticket="ENG-5", done=True)
        rebuilt = PlanStep.from_dict(original.to_dict())
        assert rebuilt.id == original.id
        assert rebuilt.description == original.description
        assert rebuilt.ticket == original.ticket
        assert rebuilt.done == original.done


class TestAssumption:
    def test_to_dict(self):
        a = Assumption(id="P.1", selected=True, statement="Use Redis", rationale="In stack")
        d = a.to_dict()
        assert d == {"id": "P.1", "selected": True, "statement": "Use Redis", "rationale": "In stack"}

    def test_from_dict(self):
        a = Assumption.from_dict({"id": "1.1", "selected": False, "statement": "Skip it"})
        assert a.rationale == ""

    def test_legacy_text_field(self):
        a = Assumption.from_dict({"id": "P.1", "selected": True, "text": "Old field"})
        assert a.statement == "Old field"

    def test_missing_rationale(self):
        a = Assumption.from_dict({"id": "P.2", "selected": False, "statement": "No rationale"})
        assert a.rationale == ""

    def test_roundtrip(self):
        original = Assumption(id="P.1", selected=True, statement="Test", rationale="Because")
        rebuilt = Assumption.from_dict(original.to_dict())
        assert rebuilt.id == original.id
        assert rebuilt.selected == original.selected
        assert rebuilt.statement == original.statement
        assert rebuilt.rationale == original.rationale


class TestExplorationFindings:
    def test_to_dict(self):
        e = ExplorationFindings(patterns=["p1"], relevant_modules=["m1"], similar_implementations=[{"file": "f"}])
        d = e.to_dict()
        assert d["patterns"] == ["p1"]
        assert d["relevant_modules"] == ["m1"]
        assert d["similar_implementations"] == [{"file": "f"}]

    def test_from_dict(self):
        e = ExplorationFindings.from_dict({"patterns": ["a"], "relevant_modules": ["b"]})
        assert e.similar_implementations == []

    def test_empty_defaults(self):
        e = ExplorationFindings()
        assert e.patterns == []
        assert e.relevant_modules == []
        assert e.similar_implementations == []

    def test_roundtrip(self):
        original = ExplorationFindings(
            patterns=["p"], relevant_modules=["m"], similar_implementations=[{"file": "f", "relevance": "r"}]
        )
        rebuilt = ExplorationFindings.from_dict(original.to_dict())
        assert rebuilt.patterns == original.patterns
        assert rebuilt.relevant_modules == original.relevant_modules
        assert rebuilt.similar_implementations == original.similar_implementations


class TestTokenUsage:
    def test_total_property(self):
        t = TokenUsage(input_tokens=100, output_tokens=50)
        assert t.total == 150

    def test_add(self):
        a = TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.01)
        b = TokenUsage(input_tokens=200, output_tokens=100, cost_usd=0.02)
        c = a + b
        assert c.input_tokens == 300
        assert c.output_tokens == 150
        assert c.cost_usd == pytest.approx(0.03)

    def test_identity_add(self):
        a = TokenUsage(input_tokens=100, output_tokens=50)
        b = TokenUsage()
        c = a + b
        assert c.total == 150

    def test_defaults(self):
        t = TokenUsage()
        assert t.input_tokens == 0
        assert t.output_tokens == 0
        assert t.total == 0
        assert t.cost_usd == 0.0


class TestWorkContext:
    def _make_ctx(self, **kwargs):
        defaults = dict(
            ticket_id="ENG-1",
            title="Test",
            description="Desc",
            issue_uuid="uuid-123",
            issue_url="https://linear.app/team/ENG-1",
            branch_name="eng-1-test",
            subtasks=[],
            plan_steps=[],
            all_assumptions=[],
            assumptions=[],
            exploration=None,
            state_iteration=5,
            loop_iter=3,
            iter_start=0.0,
            total_start=0.0,
            current_step=None,
            step_desc=None,
            commit_ticket="ENG-1",
            work_result=None,
            last_test_error=None,
            last_review_issues=None,
            last_completion_issues=None,
            iter_state={},
            tests_passed=True,
            step_done=False,
            review_status="skipped",
            comment_id=None,
            log_entries=[],
            config=RunConfig(ticket_ids=["ENG-1"], max_iterations=10, effort="high", model="sonnet"),
        )
        defaults.update(kwargs)
        return WorkContext(**defaults)

    def test_iteration_property(self):
        ctx = self._make_ctx(state_iteration=5, loop_iter=3)
        assert ctx.iteration == 8

    def test_comment_url_with_comment_id(self):
        ctx = self._make_ctx(comment_id="abcdef1234567890")
        assert ctx.comment_url == "https://linear.app/team/ENG-1#comment-abcdef12"

    def test_comment_url_without_comment_id(self):
        ctx = self._make_ctx()
        assert ctx.comment_url == "https://linear.app/team/ENG-1"
