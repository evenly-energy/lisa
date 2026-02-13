"""Tests for lisa.clients.claude.TokenTracker."""

import pytest

from lisa.clients.claude import TokenTracker
from lisa.models.results import TokenUsage


class TestTokenTracker:
    def test_initial_state(self):
        tt = TokenTracker()
        assert tt.iteration.total == 0
        assert tt.total.total == 0

    def test_add_single(self):
        tt = TokenTracker()
        tt.add(TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.01))
        assert tt.iteration.total == 150
        assert tt.total.total == 150
        assert tt.total.cost_usd == 0.01

    def test_add_multiple_cumulative(self):
        tt = TokenTracker()
        tt.add(TokenUsage(input_tokens=100, output_tokens=50))
        tt.add(TokenUsage(input_tokens=200, output_tokens=100))
        assert tt.iteration.total == 450
        assert tt.total.total == 450

    def test_reset_iteration_zeros_iteration_keeps_total(self):
        tt = TokenTracker()
        tt.add(TokenUsage(input_tokens=100, output_tokens=50))
        tt.reset_iteration()
        assert tt.iteration.total == 0
        assert tt.total.total == 150

    def test_add_after_reset(self):
        tt = TokenTracker()
        tt.add(TokenUsage(input_tokens=100, output_tokens=50))
        tt.reset_iteration()
        tt.add(TokenUsage(input_tokens=200, output_tokens=100))
        assert tt.iteration.total == 300
        assert tt.total.total == 450

    def test_cost_accumulates(self):
        tt = TokenTracker()
        tt.add(TokenUsage(cost_usd=0.01))
        tt.add(TokenUsage(cost_usd=0.02))
        assert tt.total.cost_usd == pytest.approx(0.03)
