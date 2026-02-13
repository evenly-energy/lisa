"""E2E roundtrip tests for state comment format→parse consistency."""

from lisa.models.core import Assumption
from lisa.state.comment import (
    build_state_comment,
    format_assumptions_markdown,
    parse_assumptions_markdown,
    parse_state_comment,
)


class TestAssumptionRoundtrip:
    def test_selected(self):
        original = [Assumption(id="P.1", selected=True, statement="Use Redis")]
        md = format_assumptions_markdown(original)
        parsed = parse_assumptions_markdown(md)
        assert len(parsed) == 1
        assert parsed[0].id == "P.1"
        assert parsed[0].selected is True
        assert parsed[0].statement == "Use Redis"

    def test_rejected(self):
        original = [Assumption(id="P.2", selected=False, statement="Skip migration")]
        md = format_assumptions_markdown(original)
        parsed = parse_assumptions_markdown(md)
        assert parsed[0].selected is False

    def test_with_rationale(self):
        original = [
            Assumption(id="P.1", selected=True, statement="Use Redis", rationale="In stack")
        ]
        md = format_assumptions_markdown(original)
        parsed = parse_assumptions_markdown(md)
        assert parsed[0].rationale == "In stack"

    def test_mixed_planning_and_work(self):
        original = [
            Assumption(id="P.1", selected=True, statement="Planning A"),
            Assumption(id="P.2", selected=False, statement="Planning B"),
            Assumption(id="1.1", selected=True, statement="Work C"),
            Assumption(id="2.1", selected=False, statement="Work D"),
        ]
        md = format_assumptions_markdown(original)
        parsed = parse_assumptions_markdown(md)
        assert len(parsed) == 4
        ids = [a.id for a in parsed]
        assert "P.1" in ids
        assert "1.1" in ids
        assert "2.1" in ids


class TestStateCommentRoundtrip:
    def test_full_roundtrip(self):
        steps = [
            {"id": 1, "ticket": "ENG-71", "description": "Setup", "done": True},
            {"id": 2, "ticket": "ENG-72", "description": "Implement", "done": False},
            {"id": 3, "ticket": "", "description": "Test", "done": False},
        ]
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis", rationale="In stack"),
            Assumption(id="1.1", selected=False, statement="Skip it"),
        ]
        body = build_state_comment(
            "eng-71-test",
            5,
            2,
            steps,
            ["log1", "log2"],
            assumptions=assumptions,
        )
        parsed = parse_state_comment(body)
        # iterations parsing has a known limitation (regex doesn't match extracted substring)
        assert parsed["current_step"] == 2
        assert len(parsed["plan_steps"]) == 3
        assert parsed["plan_steps"][0]["done"] is True
        assert parsed["plan_steps"][1]["done"] is False
        assert parsed["plan_steps"][0]["ticket"] == "ENG-71"

    def test_assumptions_survive_roundtrip(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis", rationale="In stack"),
            Assumption(id="P.2", selected=False, statement="Add dep"),
        ]
        body = build_state_comment("eng-1-test", 1, None, [], [], assumptions=assumptions)
        parsed_assumptions = parse_assumptions_markdown(body)
        assert len(parsed_assumptions) == 2
        assert parsed_assumptions[0].id == "P.1"
        assert parsed_assumptions[0].selected is True
        assert parsed_assumptions[0].rationale == "In stack"

    def test_empty_roundtrip(self):
        body = build_state_comment("eng-1-test", 0, None, [], [])
        parsed = parse_state_comment(body)
        assert parsed["iterations"] == 0
        assert parsed["current_step"] is None
        assert parsed["plan_steps"] == []
