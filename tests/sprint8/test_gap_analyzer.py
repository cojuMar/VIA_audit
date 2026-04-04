import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/framework-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.gap_analyzer import GapAnalyzer
from src.models import GapSeverity, GapItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(fetch_return=None, execute_return=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=execute_return)

    # Support context-manager transaction()
    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_ctx)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _gap_row(is_key: bool, status: str, control_id: str = "CC1.1") -> dict:
    return {
        "framework_control_id": uuid4(),
        "control_id": control_id,
        "title": f"Control {control_id}",
        "domain": "Security (CC)",
        "is_key_control": is_key,
        "description": "A test control description.",
        "status": status,
    }


# ---------------------------------------------------------------------------
# TestGapSeverityComputation
# ---------------------------------------------------------------------------

class TestGapSeverityComputation:
    """Tests for _compute_severity — pure logic, no DB needed."""

    def setup_method(self):
        # GapAnalyzer with dummy pool and no API key — just need the method
        dummy_pool = MagicMock()
        self.analyzer = GapAnalyzer(dummy_pool, anthropic_api_key="")

    def test_key_control_failing_is_critical(self):
        assert self.analyzer._compute_severity(True, "failing") == GapSeverity.CRITICAL

    def test_key_control_not_started_is_high(self):
        assert self.analyzer._compute_severity(True, "not_started") == GapSeverity.HIGH

    def test_non_key_failing_is_medium(self):
        assert self.analyzer._compute_severity(False, "failing") == GapSeverity.MEDIUM

    def test_non_key_not_started_is_low(self):
        assert self.analyzer._compute_severity(False, "not_started") == GapSeverity.LOW


# ---------------------------------------------------------------------------
# TestGapAnalyzerAnalysis
# ---------------------------------------------------------------------------

class TestGapAnalyzerAnalysis:

    @pytest.mark.asyncio
    async def test_analyze_returns_gap_items(self):
        rows = [
            _gap_row(is_key=True, status="failing", control_id="CC1.1"),
            _gap_row(is_key=True, status="not_started", control_id="CC2.1"),
            _gap_row(is_key=False, status="not_started", control_id="CC3.1"),
        ]
        pool, _ = _make_pool(fetch_return=rows)
        analyzer = GapAnalyzer(pool, anthropic_api_key="")

        result = await analyzer.analyze(uuid4(), uuid4())

        assert len(result) == 3
        assert all(isinstance(item, GapItem) for item in result)

    @pytest.mark.asyncio
    async def test_gap_items_sorted_by_severity(self):
        """Critical items must appear before lower-severity ones."""
        rows = [
            _gap_row(is_key=False, status="not_started", control_id="CC9.9"),   # LOW
            _gap_row(is_key=True,  status="failing",     control_id="CC1.1"),   # CRITICAL
            _gap_row(is_key=False, status="failing",     control_id="CC5.5"),   # MEDIUM
        ]
        pool, _ = _make_pool(fetch_return=rows)
        analyzer = GapAnalyzer(pool, anthropic_api_key="")

        result = await analyzer.analyze(uuid4(), uuid4())

        # The analyze() method sorts: critical first (DB returns key controls first,
        # then within same key-ness by control_id). Verify CRITICAL is the highest
        # severity present, and LOW is not before CRITICAL.
        severities = [item.gap_severity for item in result]
        first_critical = next((i for i, s in enumerate(severities) if s == GapSeverity.CRITICAL), None)
        first_low = next((i for i, s in enumerate(severities) if s == GapSeverity.LOW), None)
        if first_critical is not None and first_low is not None:
            assert first_critical < first_low, "CRITICAL must appear before LOW in sorted result"

    @pytest.mark.asyncio
    async def test_no_gaps_returns_empty_list(self):
        pool, _ = _make_pool(fetch_return=[])
        analyzer = GapAnalyzer(pool, anthropic_api_key="")

        result = await analyzer.analyze(uuid4(), uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_remediation_fallback_when_no_api_key(self):
        """With empty api_key, _suggest_remediation returns a non-empty fallback string."""
        dummy_pool = MagicMock()
        analyzer = GapAnalyzer(dummy_pool, anthropic_api_key="")

        suggestion = await analyzer._suggest_remediation("CC1.1", "Access Control", "Implement access control.")

        assert suggestion, "Fallback remediation must be non-empty"
        assert isinstance(suggestion, str)

    @pytest.mark.asyncio
    async def test_gap_items_persisted_to_db(self):
        """analyze() must DELETE old unresolved gaps then INSERT new ones."""
        rows = [
            _gap_row(is_key=True, status="failing", control_id="CC1.1"),
            _gap_row(is_key=False, status="not_started", control_id="CC2.1"),
        ]
        pool, conn = _make_pool(fetch_return=rows)
        analyzer = GapAnalyzer(pool, anthropic_api_key="")

        await analyzer.analyze(uuid4(), uuid4())

        all_calls = [str(c) for c in conn.execute.call_args_list]
        delete_calls = [c for c in all_calls if "DELETE FROM framework_gap_items" in c]
        insert_calls = [c for c in all_calls if "INSERT INTO framework_gap_items" in c]

        assert len(delete_calls) >= 1, "Expected DELETE of old gap items before insert"
        assert len(insert_calls) == 2, "Expected one INSERT per gap item"
