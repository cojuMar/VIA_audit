"""Sprint 16 — RiskScorer unit tests (pure computation, no DB, no mocking)."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/risk-service"),
)

import pytest
from src.risk_scorer import RiskScorer, score, label, color, risk_reduction


class TestRiskScorer:

    # ------------------------------------------------------------------
    # score()
    # ------------------------------------------------------------------

    def test_score_is_likelihood_times_impact(self):
        """score(3, 4) must equal 12.0."""
        assert score(3, 4) == 12.0

    def test_score_max_is_25(self):
        """score(5, 5) must equal 25.0 (maximum possible)."""
        assert score(5, 5) == 25.0

    def test_score_min_is_1(self):
        """score(1, 1) must equal 1.0 (minimum possible)."""
        assert score(1, 1) == 1.0

    # ------------------------------------------------------------------
    # label()
    # ------------------------------------------------------------------

    def test_label_critical_for_high_score(self):
        """label(5, 5) must return 'Critical' for the top cell."""
        assert label(5, 5) == "Critical"

    def test_label_low_for_low_score(self):
        """label(1, 2) must return 'Low'."""
        assert label(1, 2) == "Low"

    def test_label_medium_for_mid_score(self):
        """label(3, 3) must return 'Medium' (score=9)."""
        assert label(3, 3) == "Medium"

    # ------------------------------------------------------------------
    # color()
    # ------------------------------------------------------------------

    def test_color_red_for_critical(self):
        """color(5, 5) → score=25 ≥ 20 → 'red'."""
        assert color(5, 5) == "red"

    def test_color_orange_for_high(self):
        """color(4, 4) → score=16 (12 ≤ s < 20) → 'orange'."""
        assert color(4, 4) == "orange"

    def test_color_yellow_for_medium(self):
        """color(3, 2) → score=6 (6 ≤ s < 12) → 'yellow'."""
        assert color(3, 2) == "yellow"

    def test_color_green_for_low(self):
        """color(1, 2) → score=2 (s < 6) → 'green'."""
        assert color(1, 2) == "green"

    # ------------------------------------------------------------------
    # risk_reduction()
    # ------------------------------------------------------------------

    def test_risk_reduction_100pct_when_eliminated(self):
        """risk_reduction(5, 5, 0, 0) — residual zeroed out.

        When residual = 0, reduction should be 100.0 (full elimination).
        The scorer guards against zero inherent by returning 0.0, but here
        inherent is 25 so we expect 100.0.
        """
        result = risk_reduction(5, 5, 0, 0)
        assert result == 100.0

    def test_risk_reduction_50pct(self):
        """inherent=20 (4,5), residual=10 (2,5) → 50.0 % reduction."""
        result = risk_reduction(4, 5, 2, 5)
        assert result == 50.0

    def test_risk_reduction_zero_when_unchanged(self):
        """Same likelihood & impact for inherent and residual → 0.0 % reduction."""
        result = risk_reduction(3, 4, 3, 4)
        assert result == 0.0

    # ------------------------------------------------------------------
    # Full 5×5 matrix coverage
    # ------------------------------------------------------------------

    def test_all_25_cells_have_labels(self):
        """Every (likelihood, impact) pair in 1..5 × 1..5 returns a non-empty label."""
        for l in range(1, 6):
            for i in range(1, 6):
                result = label(l, i)
                assert isinstance(result, str) and len(result) > 0, (
                    f"label({l}, {i}) returned empty or non-string: {result!r}"
                )
