"""Tests for lisa.utils.formatting."""

from lisa.utils.formatting import fmt_cost, fmt_duration, fmt_tokens


class TestFmtDuration:
    def test_zero(self):
        assert fmt_duration(0) == "0s"

    def test_under_minute(self):
        assert fmt_duration(45) == "45s"

    def test_exactly_60(self):
        assert fmt_duration(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert fmt_duration(125) == "2m 5s"

    def test_under_hour(self):
        assert fmt_duration(3599) == "59m 59s"

    def test_exactly_one_hour(self):
        assert fmt_duration(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert fmt_duration(3661) == "1h 1m 1s"

    def test_fractional_under_minute(self):
        assert fmt_duration(45.7) == "46s"


class TestFmtTokens:
    def test_zero(self):
        assert fmt_tokens(0) == "0"

    def test_under_1k(self):
        assert fmt_tokens(500) == "500"

    def test_exactly_1k(self):
        assert fmt_tokens(1000) == "1.0k"

    def test_large(self):
        assert fmt_tokens(15200) == "15.2k"


class TestFmtCost:
    def test_zero(self):
        assert fmt_cost(0) == "$0.0000"

    def test_under_penny(self):
        assert fmt_cost(0.0045) == "$0.0045"

    def test_exactly_penny(self):
        assert fmt_cost(0.01) == "$0.01"

    def test_dollars(self):
        assert fmt_cost(1.50) == "$1.50"
