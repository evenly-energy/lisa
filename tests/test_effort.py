"""Tests for lisa.constants.resolve_effort."""

import pytest

from lisa.constants import resolve_effort


class TestResolveEffort:
    def test_no_cap(self):
        assert resolve_effort("high") == "high"

    def test_cap_lower(self):
        assert resolve_effort("high", "low") == "low"

    def test_cap_equal(self):
        assert resolve_effort("medium", "medium") == "medium"

    def test_cap_higher(self):
        assert resolve_effort("low", "high") == "low"

    def test_unknown_phase_defaults_rank_2(self):
        assert resolve_effort("unknown", "low") == "low"

    def test_unknown_cap_defaults_rank_2(self):
        assert resolve_effort("low", "unknown") == "low"

    @pytest.mark.parametrize(
        "phase,cap,expected",
        [
            ("low", "low", "low"),
            ("low", "medium", "low"),
            ("low", "high", "low"),
            ("medium", "low", "low"),
            ("medium", "medium", "medium"),
            ("medium", "high", "medium"),
            ("high", "low", "low"),
            ("high", "medium", "medium"),
            ("high", "high", "high"),
        ],
    )
    def test_all_combos(self, phase, cap, expected):
        assert resolve_effort(phase, cap) == expected
