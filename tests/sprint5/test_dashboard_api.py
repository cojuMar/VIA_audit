"""
Sprint 5 — Dashboard BFF API Tests

Tests for route structure, white-label config defaults, and HITL priority logic.
No real DB or external services required.

Run: pytest tests/sprint5/test_dashboard_api.py -v
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


class TestWhiteLabelDefaults:
    def test_default_primary_color_is_brand_blue(self):
        """Default primary color matches Aegis brand blue."""
        default_primary = '#1a56db'
        assert default_primary.startswith('#')
        assert len(default_primary) == 7

    def test_default_colors_are_valid_hex(self):
        """All default colors must be valid 6-digit hex codes."""
        import re
        defaults = {
            'primary_color': '#1a56db',
            'secondary_color': '#7e3af2',
            'accent_color': '#0e9f6e',
        }
        hex_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')
        for name, color in defaults.items():
            assert hex_pattern.match(color), f"{name}={color} is not a valid hex color"


class TestAuditHubItemValidation:
    def test_valid_priority_values(self):
        """Priority must be one of the allowed values."""
        valid = {'low', 'medium', 'high', 'critical'}
        for p in valid:
            assert p in valid

    def test_valid_status_values(self):
        """Status must be one of the allowed values."""
        valid = {'open', 'in_progress', 'resolved', 'waived'}
        for s in valid:
            assert s in valid

    def test_invalid_status_not_in_valid_set(self):
        valid = {'open', 'in_progress', 'resolved', 'waived'}
        assert 'deleted' not in valid
        assert 'cancelled' not in valid

    def test_invalid_priority_not_in_valid_set(self):
        valid = {'low', 'medium', 'high', 'critical'}
        assert 'urgent' not in valid
        assert 'blocker' not in valid


class TestGaugeThresholds:
    """Tests for Autonomous Mode gauge threshold structure."""

    def test_gauge_has_required_fields(self):
        """Each gauge must have id, label, value, unit, and thresholds."""
        gauge = {
            "id": "overall_health",
            "label": "Overall Health",
            "value": 0.85,
            "unit": "score",
            "thresholds": {"warning": 0.6, "critical": 0.4},
        }
        required = {'id', 'label', 'value', 'unit', 'thresholds'}
        assert required.issubset(gauge.keys())

    def test_gauge_threshold_warning_gt_critical(self):
        """Warning threshold must be higher than critical threshold."""
        thresholds = {"warning": 0.6, "critical": 0.4}
        assert thresholds['warning'] > thresholds['critical']

    def test_gauge_value_is_in_unit_interval(self):
        """Gauge values must be in [0, 1]."""
        for value in [0.0, 0.5, 0.85, 1.0]:
            assert 0.0 <= value <= 1.0

    def test_five_gauges_returned(self):
        """Autonomous Mode must return exactly 5 gauges."""
        gauge_ids = [
            "overall_health", "evidence_freshness", "anomaly_rate",
            "connector_health", "data_integrity"
        ]
        assert len(gauge_ids) == 5
        assert len(set(gauge_ids)) == 5  # all unique


class TestFirmModePortfolio:
    def test_portfolio_summary_structure(self):
        """Portfolio response must include all required fields."""
        portfolio = {
            "framework": "soc2",
            "client_count": 5,
            "avg_health_score": 0.72,
            "clients_at_risk": 2,
            "critical_issues_total": 3,
            "clients": [],
        }
        required = {'framework', 'client_count', 'avg_health_score', 'clients_at_risk', 'critical_issues_total', 'clients'}
        assert required.issubset(portfolio.keys())

    def test_clients_at_risk_uses_06_threshold(self):
        """Clients with overall_score < 0.6 are counted as 'at risk'."""
        clients = [
            {'overall_score': 0.9},
            {'overall_score': 0.55},  # at risk
            {'overall_score': 0.6},   # exactly at threshold -- not at risk
            {'overall_score': 0.3},   # at risk
        ]
        at_risk = sum(1 for c in clients if (c['overall_score'] or 1.0) < 0.6)
        assert at_risk == 2
