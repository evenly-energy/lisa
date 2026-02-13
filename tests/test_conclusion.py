"""Tests for lisa.phases.conclusion.format_conclusion_markdown."""

from lisa.phases.conclusion import format_conclusion_markdown


class TestFormatConclusionMarkdown:
    def test_minimal(self):
        result = format_conclusion_markdown({"purpose": "Add auth"})
        assert "## Review Guide" in result
        assert "Add auth" in result

    def test_with_entry_point(self):
        result = format_conclusion_markdown({
            "purpose": "Add auth",
            "entry_point": "src/auth/handler.py",
        })
        assert "`src/auth/handler.py`" in result

    def test_with_flow(self):
        result = format_conclusion_markdown({
            "purpose": "Add auth",
            "flow": "1. Request comes in\n2. Auth check\n3. Response",
        })
        assert "### Flow" in result
        assert "Request comes in" in result

    def test_with_error_handling(self):
        result = format_conclusion_markdown({
            "purpose": "Add auth",
            "error_handling": [
                {"location": "handler.py:25", "description": "Catches auth errors"},
            ],
        })
        assert "### Error Handling" in result
        assert "`handler.py:25`" in result

    def test_with_key_review_points(self):
        result = format_conclusion_markdown({
            "purpose": "Add auth",
            "key_review_points": [
                {
                    "location": "handler.py:30",
                    "what_it_does": "Validates JWT",
                    "risk": "Token expiry not checked",
                },
            ],
        })
        assert "### Key Review Points" in result
        assert "**handler.py:30**" in result
        assert "Validates JWT" in result
        assert "Token expiry" in result

    def test_with_tests(self):
        result = format_conclusion_markdown({
            "purpose": "Add auth",
            "tests": {
                "covered": ["JWT validation", "Login flow"],
                "missing": ["Refresh token"],
            },
        })
        assert "### Test Coverage" in result
        assert "[x] JWT validation" in result
        assert "[ ] Refresh token" in result
