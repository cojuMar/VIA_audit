"""Sprint 16 — AppetiteManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/risk-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date


# ---------------------------------------------------------------------------
# Helper — pool/connection mock (async context-manager protocol)
# ---------------------------------------------------------------------------

def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


TENANT = "20000000-0000-0000-0000-000000000016"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def appetite_manager():
    from src.appetite_manager import AppetiteManager

    pool, _ = make_pool_conn()
    return AppetiteManager(pool, TENANT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAppetiteManager:

    # ------------------------------------------------------------------
    # upsert
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_upsert_inserts_on_conflict(self):
        """upsert must use ON CONFLICT logic in the SQL statement."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-compliance", "category_key": "compliance"}
        conn.fetchrow.return_value = category_row

        mgr = AppetiteManager(pool, TENANT)
        await mgr.upsert(
            category_key="compliance",
            appetite_level="low",
            max_acceptable_score=12.0,
        )

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "ON CONFLICT" in sql for sql in executed_sqls
        ), "upsert must use ON CONFLICT in its SQL"

    @pytest.mark.asyncio
    async def test_upsert_looks_up_category(self):
        """upsert must fetchrow from risk_categories to resolve category_key → id."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-strategic", "category_key": "strategic"}
        conn.fetchrow.return_value = category_row

        mgr = AppetiteManager(pool, TENANT)
        await mgr.upsert(
            category_key="strategic",
            appetite_level="moderate",
            max_acceptable_score=15.0,
        )

        first_call_sql = conn.fetchrow.call_args_list[0][0][0]
        assert "risk_categories" in first_call_sql, (
            "upsert must look up the category from risk_categories"
        )

    # ------------------------------------------------------------------
    # get_all
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_all_returns_list(self):
        """get_all must return a list (even when the table is empty)."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []

        mgr = AppetiteManager(pool, TENANT)
        result = await mgr.get_all()

        assert isinstance(result, list), "get_all must return a list"

    # ------------------------------------------------------------------
    # check_risk
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_risk_returns_exceeds_appetite_true(self):
        """residual_score=18 against max_acceptable_score=12 → exceeds_appetite=True."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        appetite_row = {
            "max_acceptable_score": 12.0,
            "appetite_level": "low",
            "category_key": "cybersecurity",
        }
        conn.fetchrow.return_value = appetite_row

        mgr = AppetiteManager(pool, TENANT)
        result = await mgr.check_risk(
            category_key="cybersecurity",
            residual_score=18.0,
        )

        assert result["exceeds_appetite"] is True, (
            f"Expected exceeds_appetite=True when residual_score=18 > max=12, got {result}"
        )

    @pytest.mark.asyncio
    async def test_check_risk_returns_exceeds_appetite_false(self):
        """residual_score=8 against max_acceptable_score=12 → exceeds_appetite=False."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        appetite_row = {
            "max_acceptable_score": 12.0,
            "appetite_level": "low",
            "category_key": "cybersecurity",
        }
        conn.fetchrow.return_value = appetite_row

        mgr = AppetiteManager(pool, TENANT)
        result = await mgr.check_risk(
            category_key="cybersecurity",
            residual_score=8.0,
        )

        assert result["exceeds_appetite"] is False, (
            f"Expected exceeds_appetite=False when residual_score=8 ≤ max=12, got {result}"
        )

    @pytest.mark.asyncio
    async def test_check_risk_gap_computed(self):
        """gap must equal residual_score − max_acceptable_score (= 18 − 12 = 6.0)."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        appetite_row = {
            "max_acceptable_score": 12.0,
            "appetite_level": "low",
            "category_key": "cybersecurity",
        }
        conn.fetchrow.return_value = appetite_row

        mgr = AppetiteManager(pool, TENANT)
        result = await mgr.check_risk(
            category_key="cybersecurity",
            residual_score=18.0,
        )

        assert result["gap"] == pytest.approx(6.0), (
            f"Expected gap=6.0, got {result.get('gap')}"
        )

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_summary_returns_required_keys(self):
        """summary must return a dict containing total_configured, risks_above_appetite, by_category."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []
        conn.fetchval.return_value = 0

        mgr = AppetiteManager(pool, TENANT)
        result = await mgr.summary()

        required_keys = {"total_configured", "risks_above_appetite", "by_category"}
        missing = required_keys - set(result.keys())
        assert not missing, f"summary result missing keys: {missing}"

    # ------------------------------------------------------------------
    # effective_date default
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_upsert_effective_date_defaults_to_today(self):
        """upsert must pass today's date as effective_date when none is provided."""
        from src.appetite_manager import AppetiteManager

        pool, conn = make_pool_conn()
        category_row = {"id": "cat-uuid-financial", "category_key": "financial"}
        conn.fetchrow.return_value = category_row

        mgr = AppetiteManager(pool, TENANT)
        await mgr.upsert(
            category_key="financial",
            appetite_level="moderate",
            max_acceptable_score=15.0,
            # effective_date intentionally omitted
        )

        today = date.today()
        all_execute_args = str(conn.execute.call_args_list)
        assert str(today) in all_execute_args, (
            f"Expected today's date ({today}) in upsert arguments when effective_date is omitted"
        )
