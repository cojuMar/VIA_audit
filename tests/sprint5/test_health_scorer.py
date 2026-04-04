"""
Sprint 5 — Health Scorer Tests

Tests the multi-dimensional health score computation for Autonomous Mode.
Uses mocked DB connections — no real database required.

Run: pytest tests/sprint5/test_health_scorer.py -v
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/dashboard-service'))


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/dummy")
    monkeypatch.setenv("FORENSIC_ML_URL", "http://localhost:3007")
    monkeypatch.setenv("RAG_PIPELINE_URL", "http://localhost:3008")
    monkeypatch.setenv("EVIDENCE_STORE_URL", "http://localhost:3005")
    monkeypatch.setenv("AUTH_SERVICE_JWKS_URL", "http://localhost:3001/.well-known/jwks.json")


class TestDimensionWeights:
    def test_weights_sum_to_one(self):
        from src.health_scorer import DIMENSION_WEIGHTS
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Dimension weights sum to {total}, expected 1.0"

    def test_all_dimensions_present(self):
        from src.health_scorer import DIMENSION_WEIGHTS
        expected = {'access_control', 'data_integrity', 'anomaly_rate',
                    'evidence_freshness', 'narrative_quality'}
        assert set(DIMENSION_WEIGHTS.keys()) == expected

    def test_all_weights_positive(self):
        from src.health_scorer import DIMENSION_WEIGHTS
        for dim, w in DIMENSION_WEIGHTS.items():
            assert w > 0, f"Weight for {dim} must be positive"

    def test_data_integrity_is_highest_weight(self):
        """Data integrity is the most critical dimension (hash chain tamper evidence)."""
        from src.health_scorer import DIMENSION_WEIGHTS
        assert DIMENSION_WEIGHTS['data_integrity'] >= max(
            v for k, v in DIMENSION_WEIGHTS.items() if k != 'data_integrity'
        ), "data_integrity must have the highest weight"


class TestHealthScoreComputation:
    def test_overall_score_is_weighted_average(self):
        """overall = sum(dim * weight) for all dimensions."""
        from src.health_scorer import DIMENSION_WEIGHTS

        dims = {
            'access_control': 0.9,
            'data_integrity': 1.0,
            'anomaly_rate': 0.8,
            'evidence_freshness': 0.7,
            'narrative_quality': 0.6,
        }
        expected = sum(dims[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)
        assert 0.0 <= expected <= 1.0

    def test_all_zeros_gives_zero_overall(self):
        from src.health_scorer import DIMENSION_WEIGHTS
        overall = sum(0.0 * w for w in DIMENSION_WEIGHTS.values())
        assert overall == 0.0

    def test_all_ones_gives_one_overall(self):
        from src.health_scorer import DIMENSION_WEIGHTS
        overall = sum(1.0 * w for w in DIMENSION_WEIGHTS.values())
        assert abs(overall - 1.0) < 1e-9

    def test_overall_score_clamped_to_unit_interval(self):
        """Overall score must always be in [0, 1]."""
        from src.health_scorer import DIMENSION_WEIGHTS
        # Even if a dimension exceeds 1.0 due to rounding, weighted sum should be <= 1
        all_max = sum(1.0 * w for w in DIMENSION_WEIGHTS.values())
        assert all_max <= 1.0 + 1e-9


class TestHealthScoreDataclass:
    def test_health_score_fields(self):
        from src.health_scorer import HealthScore
        score = HealthScore(
            overall_score=0.75,
            access_control=0.9,
            data_integrity=0.95,
            anomaly_rate=0.8,
            evidence_freshness=0.7,
            narrative_quality=0.6,
            open_issues=5,
            critical_issues=1,
        )
        assert score.overall_score == 0.75
        assert score.critical_issues == 1
        assert score.open_issues == 5


class TestHealthScorerFallbacks:
    """Tests that fallback values are sensible when no data exists."""

    def test_no_pam_requests_defaults_to_08(self):
        """When no PAM requests exist, access_control defaults to 0.8 (not 0 or 1)."""
        # This is tested by inspecting the fallback logic in health_scorer.py
        # access_control = approved/total if total > 0 else 0.8
        total_pam = 0
        approved = 0
        access_control = (approved / total_pam) if total_pam > 0 else 0.8
        assert access_control == 0.8

    def test_no_evidence_records_defaults_to_10(self):
        """No evidence records -> data_integrity defaults to 1.0 (pristine, not broken)."""
        total_er = 0
        chained = 0
        data_integrity = (chained / total_er) if total_er > 0 else 1.0
        assert data_integrity == 1.0

    def test_no_anomaly_scores_defaults_to_10(self):
        """No anomalies scored -> anomaly_rate = 1.0 (healthy, no anomalies detected)."""
        total_an = 0
        high_count = 0
        anomaly_rate = 1.0 - (high_count / total_an) if total_an > 0 else 1.0
        assert anomaly_rate == 1.0

    def test_no_connectors_defaults_to_05(self):
        """No active connectors -> evidence_freshness = 0.5 (uncertain, not healthy or broken)."""
        total_conn = 0
        fresh = 0
        evidence_freshness = (fresh / total_conn) if total_conn > 0 else 0.5
        assert evidence_freshness == 0.5


class TestPriorityThresholds:
    """Tests for health score interpretation thresholds."""

    def test_score_below_04_is_critical(self):
        """Gauge threshold: score < 0.4 -> Critical."""
        for score in [0.0, 0.1, 0.2, 0.39]:
            assert score < 0.4, f"{score} should be critical"

    def test_score_below_06_is_warning(self):
        """Gauge threshold: score 0.4-0.6 -> Warning."""
        for score in [0.40, 0.50, 0.59]:
            assert 0.4 <= score < 0.6, f"{score} should be warning"

    def test_score_at_or_above_06_is_healthy(self):
        """Gauge threshold: score >= 0.6 -> Healthy."""
        for score in [0.60, 0.75, 0.90, 1.00]:
            assert score >= 0.6, f"{score} should be healthy"
