"""Sprint 16 — IndicatorManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/risk-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helper — pool/connection mock (async context-manager protocol)
# ---------------------------------------------------------------------------

def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


TENANT = "30000000-0000-0000-0000-000000000016"
RISK_UUID = "risk-uuid-0000-0000-0000-000000000001"
INDICATOR_UUID = "ind-uuid-0000-0000-0000-000000000001"

INDICATOR_PAYLOAD = {
    "risk_id": RISK_UUID,
    "indicator_name": "Failed login attempts per hour",
    "description": "Count of failed authentication attempts",
    "metric_type": "kri",
    "threshold_green": 10.0,
    "threshold_amber": 20.0,
    "threshold_red": 50.0,
    "data_source": "SIEM",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIndicatorManager:

    # ------------------------------------------------------------------
    # create_indicator
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_indicator_inserts_row(self):
        """create_indicator must execute an INSERT into risk_indicators."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorCreate

        pool, conn = make_pool_conn()
        conn.fetchval.return_value = INDICATOR_UUID

        mgr = IndicatorManager(pool, TENANT)
        payload = IndicatorCreate(**INDICATOR_PAYLOAD)
        await mgr.create_indicator(payload)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "INSERT" in sql and "risk_indicators" in sql for sql in executed_sqls
        ), "Expected INSERT INTO risk_indicators"

    # ------------------------------------------------------------------
    # record_reading — status thresholds
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_record_reading_green_when_below_green_threshold(self):
        """value=5 with threshold_green=10 must produce status='green'."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorReading

        pool, conn = make_pool_conn()
        indicator_row = {
            "id": INDICATOR_UUID,
            "risk_id": RISK_UUID,
            "threshold_green": 10.0,
            "threshold_amber": 20.0,
            "threshold_red": 50.0,
        }
        conn.fetchrow.return_value = indicator_row

        mgr = IndicatorManager(pool, TENANT)
        reading = IndicatorReading(indicator_id=INDICATOR_UUID, value=5.0)
        await mgr.record_reading(reading)

        all_execute_args = str(conn.execute.call_args_list)
        assert "green" in all_execute_args, (
            "Expected status='green' when value=5 < threshold_green=10"
        )

    @pytest.mark.asyncio
    async def test_record_reading_amber_when_between_thresholds(self):
        """value=15 with threshold_green=10, threshold_amber=20 → status='amber'."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorReading

        pool, conn = make_pool_conn()
        indicator_row = {
            "id": INDICATOR_UUID,
            "risk_id": RISK_UUID,
            "threshold_green": 10.0,
            "threshold_amber": 20.0,
            "threshold_red": 50.0,
        }
        conn.fetchrow.return_value = indicator_row

        mgr = IndicatorManager(pool, TENANT)
        reading = IndicatorReading(indicator_id=INDICATOR_UUID, value=15.0)
        await mgr.record_reading(reading)

        all_execute_args = str(conn.execute.call_args_list)
        assert "amber" in all_execute_args, (
            "Expected status='amber' when threshold_green < value < threshold_amber"
        )

    @pytest.mark.asyncio
    async def test_record_reading_red_when_above_amber_threshold(self):
        """value=25 with threshold_amber=20 → status='red'."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorReading

        pool, conn = make_pool_conn()
        indicator_row = {
            "id": INDICATOR_UUID,
            "risk_id": RISK_UUID,
            "threshold_green": 10.0,
            "threshold_amber": 20.0,
            "threshold_red": 50.0,
        }
        conn.fetchrow.return_value = indicator_row

        mgr = IndicatorManager(pool, TENANT)
        reading = IndicatorReading(indicator_id=INDICATOR_UUID, value=25.0)
        await mgr.record_reading(reading)

        all_execute_args = str(conn.execute.call_args_list)
        assert "red" in all_execute_args, (
            "Expected status='red' when value=25 > threshold_amber=20"
        )

    # ------------------------------------------------------------------
    # record_reading — persistence guarantees
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_record_reading_inserts_immutable_record(self):
        """record_reading must INSERT into risk_indicator_readings (never UPDATE it)."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorReading

        pool, conn = make_pool_conn()
        indicator_row = {
            "id": INDICATOR_UUID,
            "risk_id": RISK_UUID,
            "threshold_green": 10.0,
            "threshold_amber": 20.0,
            "threshold_red": 50.0,
        }
        conn.fetchrow.return_value = indicator_row

        mgr = IndicatorManager(pool, TENANT)
        reading = IndicatorReading(indicator_id=INDICATOR_UUID, value=15.0)
        await mgr.record_reading(reading)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "INSERT" in sql and "risk_indicator_readings" in sql
            for sql in executed_sqls
        ), "Expected INSERT INTO risk_indicator_readings"
        # Must never UPDATE risk_indicator_readings (immutable audit table)
        assert not any(
            "UPDATE" in sql and "risk_indicator_readings" in sql
            for sql in executed_sqls
        ), "risk_indicator_readings must be append-only — no UPDATE allowed"

    @pytest.mark.asyncio
    async def test_record_reading_updates_current_value_on_indicator(self):
        """record_reading must UPDATE risk_indicators with the new current_value."""
        from src.indicator_manager import IndicatorManager
        from src.models import IndicatorReading

        pool, conn = make_pool_conn()
        indicator_row = {
            "id": INDICATOR_UUID,
            "risk_id": RISK_UUID,
            "threshold_green": 10.0,
            "threshold_amber": 20.0,
            "threshold_red": 50.0,
        }
        conn.fetchrow.return_value = indicator_row

        mgr = IndicatorManager(pool, TENANT)
        reading = IndicatorReading(indicator_id=INDICATOR_UUID, value=42.0)
        await mgr.record_reading(reading)

        executed_sqls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any(
            "UPDATE" in sql and "risk_indicators" in sql
            for sql in executed_sqls
        ), "Expected UPDATE risk_indicators to refresh current_value"

    # ------------------------------------------------------------------
    # get_for_risk / get_red_indicators
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_for_risk_returns_list(self):
        """get_for_risk must return a list."""
        from src.indicator_manager import IndicatorManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []

        mgr = IndicatorManager(pool, TENANT)
        result = await mgr.get_for_risk(RISK_UUID)

        assert isinstance(result, list), "get_for_risk must return a list"

    @pytest.mark.asyncio
    async def test_get_red_indicators_filters_by_status(self):
        """get_red_indicators must filter on current_status='red' in the SQL."""
        from src.indicator_manager import IndicatorManager

        pool, conn = make_pool_conn()
        conn.fetch.return_value = []

        mgr = IndicatorManager(pool, TENANT)
        await mgr.get_red_indicators()

        fetch_call_sql = conn.fetch.call_args[0][0]
        all_fetch_args = str(conn.fetch.call_args)
        assert (
            "red" in fetch_call_sql or "red" in all_fetch_args
        ), "get_red_indicators must filter by current_status='red'"
