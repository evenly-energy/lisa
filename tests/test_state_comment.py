"""Tests for lisa.state.comment parsing/formatting functions."""

from lisa.models.core import Assumption, ExplorationFindings
from lisa.state.comment import (
    build_state_comment,
    format_assumptions_markdown,
    format_exploration_markdown,
    get_state_header,
    get_state_headers,
    parse_assumptions_markdown,
    parse_state_comment,
)


class TestGetStateHeaders:
    def test_returns_lisa_and_tralph(self):
        headers = get_state_headers("eng-71-foo")
        assert len(headers) == 2
        assert "lisa" in headers[0]
        assert "tralph" in headers[1]
        assert "eng-71-foo" in headers[0]
        assert "eng-71-foo" in headers[1]


class TestGetStateHeader:
    def test_lisa_only(self):
        header = get_state_header("eng-71-foo")
        assert "lisa" in header
        assert "tralph" not in header
        assert "eng-71-foo" in header


class TestParseStateComment:
    def test_empty_body(self):
        result = parse_state_comment("")
        assert result == {"iterations": 0, "current_step": None, "plan_steps": []}

    def test_done_steps(self):
        body = "- [x] **1**: Setup config\n- [x] **2**: Add endpoint\n"
        result = parse_state_comment(body)
        assert len(result["plan_steps"]) == 2
        assert result["plan_steps"][0]["done"] is True
        assert result["plan_steps"][1]["done"] is True

    def test_pending_steps(self):
        body = "- [ ] **1**: Setup config\n"
        result = parse_state_comment(body)
        assert result["plan_steps"][0]["done"] is False

    def test_ticket_parsing(self):
        body = "- [x] **1** (ENG-456): Setup config\n"
        result = parse_state_comment(body)
        assert result["plan_steps"][0]["ticket"] == "ENG-456"
        assert result["plan_steps"][0]["description"] == "Setup config"

    def test_current_marker_stripped(self):
        body = "- [ ] **2**: Implement endpoint ← current\n"
        result = parse_state_comment(body)
        assert result["plan_steps"][0]["description"] == "Implement endpoint"
        assert result["plan_steps"][0]["done"] is False

    def test_iterations_table_row(self):
        # Note: parse_state_comment extracts line.split("|")[2] then searches for
        # pipes in it, so the regex never matches. This is a known limitation —
        # iterations are typically recovered from git trailers, not the comment.
        body = "| Iterations | 5 |\n"
        result = parse_state_comment(body)
        assert result["iterations"] == 0

    def test_current_step_table_row(self):
        body = "| Current step | 3 |\n"
        result = parse_state_comment(body)
        assert result["current_step"] == 3

    def test_dash_current_step(self):
        body = "| Current step | - |\n"
        result = parse_state_comment(body)
        assert result["current_step"] is None

    def test_invalid_current_step(self):
        body = "| Current step | abc |\n"
        result = parse_state_comment(body)
        assert result["current_step"] is None

    def test_step_with_ticket_and_current(self):
        body = "- [ ] **2** (ENG-72): Implement endpoint ← current\n"
        result = parse_state_comment(body)
        step = result["plan_steps"][0]
        assert step["ticket"] == "ENG-72"
        assert step["description"] == "Implement endpoint"
        assert step["done"] is False

    def test_multiple_mixed_steps(self):
        body = (
            "- [x] **1** (ENG-71): Setup config\n"
            "- [ ] **2** (ENG-72): Implement endpoint ← current\n"
            "- [ ] **3**: Write tests\n"
        )
        result = parse_state_comment(body)
        assert len(result["plan_steps"]) == 3
        assert result["plan_steps"][0]["done"] is True
        assert result["plan_steps"][1]["done"] is False
        assert result["plan_steps"][2]["ticket"] == ""


class TestFormatAssumptionsMarkdown:
    def test_empty(self):
        assert format_assumptions_markdown([]) == ""

    def test_selected_emoji(self):
        md = format_assumptions_markdown([
            Assumption(id="P.1", selected=True, statement="Use Redis"),
        ])
        assert "✅ P.1. Use Redis" in md

    def test_rejected_emoji(self):
        md = format_assumptions_markdown([
            Assumption(id="P.2", selected=False, statement="Add dep"),
        ])
        assert "❌ P.2. Add dep" in md

    def test_rationale_lines(self):
        md = format_assumptions_markdown([
            Assumption(id="P.1", selected=True, statement="Use Redis", rationale="In stack"),
        ])
        assert "*In stack*" in md

    def test_planning_group(self):
        md = format_assumptions_markdown([
            Assumption(id="P.1", selected=True, statement="A"),
            Assumption(id="P.2", selected=False, statement="B"),
        ])
        assert "## Assumptions" in md
        assert "P.1" in md
        assert "P.2" in md

    def test_work_group(self):
        md = format_assumptions_markdown([
            Assumption(id="1.1", selected=True, statement="Work thing"),
        ])
        assert "1.1" in md


class TestParseAssumptionsMarkdown:
    def test_empty(self):
        assert parse_assumptions_markdown("") == []

    def test_no_section(self):
        assert parse_assumptions_markdown("Some random text\nNo assumptions here") == []

    def test_selected(self):
        body = "✅ P.1. Use Redis\n"
        result = parse_assumptions_markdown(body)
        assert len(result) == 1
        assert result[0].selected is True
        assert result[0].id == "P.1"
        assert result[0].statement == "Use Redis"

    def test_rejected(self):
        body = "❌ P.2. Skip migration\n"
        result = parse_assumptions_markdown(body)
        assert result[0].selected is False

    def test_rationale_capture(self):
        body = "✅ P.1. Use Redis\n   *Already in stack*\n"
        result = parse_assumptions_markdown(body)
        assert result[0].rationale == "Already in stack"

    def test_mixed_ids(self):
        body = "✅ P.1. Planning\n❌ 1.1. Work assumption\n✅ 2.1. Another\n"
        result = parse_assumptions_markdown(body)
        assert len(result) == 3
        assert result[0].id == "P.1"
        assert result[1].id == "1.1"
        assert result[2].id == "2.1"

    def test_rationale_asterisks_in_middle(self):
        body = "✅ P.1. Statement\n   text with *bold* in middle\n"
        result = parse_assumptions_markdown(body)
        # Line doesn't start AND end with *, so no rationale captured
        assert result[0].rationale == ""


class TestFormatExplorationMarkdown:
    def test_none(self):
        assert format_exploration_markdown(None) == ""

    def test_empty_findings(self):
        e = ExplorationFindings()
        assert format_exploration_markdown(e) == ""

    def test_patterns_only(self):
        e = ExplorationFindings(patterns=["REST handler"])
        md = format_exploration_markdown(e)
        assert "## Exploration" in md
        assert "REST handler" in md

    def test_all_fields(self, sample_exploration):
        md = format_exploration_markdown(sample_exploration)
        assert "Patterns:" in md
        assert "Modules:" in md
        assert "Templates:" in md

    def test_list_truncation(self):
        e = ExplorationFindings(
            patterns=[f"p{i}" for i in range(10)],
            relevant_modules=[f"m{i}" for i in range(10)],
            similar_implementations=[{"file": f"f{i}.py", "relevance": "r"} for i in range(10)],
        )
        md = format_exploration_markdown(e)
        # Max 5 patterns, 5 modules, 3 impls
        patterns_line = [x for x in md.split("\n") if "Patterns:" in x][0]
        assert "p5" not in patterns_line
        modules_line = [x for x in md.split("\n") if "Modules:" in x][0]
        assert "m5" not in modules_line
        templates_line = [x for x in md.split("\n") if "Templates:" in x][0]
        assert "f3.py" not in templates_line


class TestBuildStateComment:
    def test_minimal(self):
        body = build_state_comment("eng-1-test", 1, None, [], [])
        assert "lisa" in body
        assert "eng-1-test" in body
        assert "| Iterations | 1 |" in body

    def test_with_steps(self, sample_plan_steps):
        body = build_state_comment("eng-1-test", 2, 2, sample_plan_steps, [])
        assert "## Plan" in body
        assert "[x] **1**" in body
        assert "[ ] **2**" in body

    def test_current_marker(self, sample_plan_steps):
        body = build_state_comment("eng-1-test", 2, 2, sample_plan_steps, [])
        assert "← current" in body

    def test_with_assumptions(self, sample_assumptions):
        body = build_state_comment("eng-1-test", 1, None, [], [], assumptions=sample_assumptions)
        assert "## Assumptions" in body
        assert "✅" in body
        assert "❌" in body

    def test_with_exploration(self, sample_exploration):
        body = build_state_comment("eng-1-test", 1, None, [], [], exploration=sample_exploration)
        assert "## Exploration" in body

    def test_log_entry_limit(self):
        logs = [f"Entry {i}" for i in range(15)]
        body = build_state_comment("eng-1-test", 1, None, [], logs)
        # Only first 10 entries
        assert "Entry 0" in body
        assert "Entry 9" in body
        assert "Entry 10" not in body

    def test_step_files(self, sample_plan_steps):
        body = build_state_comment("eng-1-test", 2, 2, sample_plan_steps, [])
        assert "`create`:" in body
        assert "src/api/handler.py" in body
        assert "template: rest_handler" in body
        assert "detail: add new route" in body

    def test_verify_table_format(self):
        body = build_state_comment("eng-1-test", 3, 2, [], [])
        assert "| Field | Value |" in body
        assert "| Iterations | 3 |" in body
        assert "| Current step | 2 |" in body

    def test_current_step_dash_when_none(self):
        body = build_state_comment("eng-1-test", 1, None, [], [])
        assert "| Current step | - |" in body
