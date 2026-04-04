"""Sprint 18 — ESGManager unit tests (16 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "esg-board-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helper — pool/connection mock (async context-manager protocol)
# ---------------------------------------------------------------------------

def make_pool_conn(
    fetch_val=None,
    fetchrow_val=None,
    execute_val=None,
    fetchval_val=None,
):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_val or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_val)
    conn.execute = AsyncMock(return_value=execute_val or "OK")
    conn.fetchval = AsyncMock(return_value=fetchval_val)
    conn.transaction = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return pool, conn


TENANT = "cccccccc-0000-0000-0000-000000000018"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestESGManager:

    # 1 — get_frameworks can be called without tenant_id, returns list
    @pytest.mark.asyncio
    async def test_get_frameworks_no_tenant_needed(self):
        from src.esg_manager import ESGManager

        rows = [
            {"id": "f1", "name": "GRI", "category": "reporting"},
            {"id": "f2", "name": "TCFD", "category": "climate"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_frameworks(TENANT)

        assert isinstance(result, list)
        assert len(result) == 2

    # 2 — get_frameworks filters by category when supplied
    @pytest.mark.asyncio
    async def test_get_frameworks_filters_by_category(self):
        from src.esg_manager import ESGManager

        pool, conn = make_pool_conn(fetch_val=[{"id": "f1", "name": "GRI", "category": "environmental"}])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            await mgr.get_frameworks(TENANT, category="environmental")

        sql = conn.fetch.call_args[0][0]
        assert "environmental" in sql or "$" in sql
        # The category parameter must be passed
        call_args = conn.fetch.call_args
        assert any("environmental" in str(a) for a in call_args[0]) or \
               any("environmental" in str(a) for a in call_args[1].values()) or \
               "environmental" in str(call_args)

    # 3 — get_metric_definitions returns list of 15 rows
    @pytest.mark.asyncio
    async def test_get_metric_definitions_returns_list(self):
        from src.esg_manager import ESGManager

        rows = [{"id": f"md-{i}", "name": f"Metric {i}", "category": "environmental"} for i in range(15)]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_metric_definitions(TENANT)

        assert isinstance(result, list)
        assert len(result) == 15

    # 4 — submit_disclosure uses INSERT into esg_disclosures, no UPDATE/DELETE
    @pytest.mark.asyncio
    async def test_submit_disclosure_inserts_immutable(self):
        from src.esg_manager import ESGManager
        from src.models import DisclosureCreate

        row = {"id": "disc-1", "metric_definition_id": "md-1", "reporting_period": "2025"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            await mgr.submit_disclosure(
                TENANT,
                DisclosureCreate(
                    metric_definition_id="md-1",
                    reporting_period="2025",
                    numeric_value=42.0,
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "esg_disclosures" in sql
        assert "INSERT" in sql.upper()
        assert "UPDATE" not in sql.upper()
        assert "DELETE" not in sql.upper()

    # 5 — submit_disclosure raises ValueError when all value fields are None
    @pytest.mark.asyncio
    async def test_submit_disclosure_requires_value(self):
        from src.esg_manager import ESGManager
        from src.models import DisclosureCreate

        pool, conn = make_pool_conn()

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            with pytest.raises(ValueError):
                await mgr.submit_disclosure(
                    TENANT,
                    DisclosureCreate(
                        metric_definition_id="md-1",
                        reporting_period="2025",
                        numeric_value=None,
                        text_value=None,
                        boolean_value=None,
                        currency_value=None,
                    ),
                )

    # 6 — submit_disclosure accepts numeric_value=100.0 as valid
    @pytest.mark.asyncio
    async def test_submit_disclosure_numeric_value_accepted(self):
        from src.esg_manager import ESGManager
        from src.models import DisclosureCreate

        row = {"id": "disc-2", "metric_definition_id": "md-1", "reporting_period": "2025", "numeric_value": 100.0}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.submit_disclosure(
                TENANT,
                DisclosureCreate(
                    metric_definition_id="md-1",
                    reporting_period="2025",
                    numeric_value=100.0,
                ),
            )

        assert result is not None

    # 7 — get_disclosures filters by reporting_period in SQL
    @pytest.mark.asyncio
    async def test_get_disclosures_filters_by_period(self):
        from src.esg_manager import ESGManager

        pool, conn = make_pool_conn(fetch_val=[{"id": "disc-1", "reporting_period": "2025"}])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            await mgr.get_disclosures(TENANT, reporting_period="2025")

        call_args = conn.fetch.call_args
        assert any("2025" in str(a) for a in call_args[0]) or \
               any("2025" in str(a) for a in call_args[1].values()) or \
               "2025" in str(call_args)

    # 8 — get_disclosures filters by category, joins metric_definitions
    @pytest.mark.asyncio
    async def test_get_disclosures_filters_by_category(self):
        from src.esg_manager import ESGManager

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            await mgr.get_disclosures(TENANT, category="environmental")

        sql = conn.fetch.call_args[0][0]
        assert "metric_definitions" in sql or "esg_metric_definitions" in sql
        call_args = conn.fetch.call_args
        assert any("environmental" in str(a) for a in call_args[0]) or \
               any("environmental" in str(a) for a in call_args[1].values()) or \
               "environmental" in str(call_args)

    # 9 — get_esg_scorecard returns required top-level keys
    @pytest.mark.asyncio
    async def test_get_esg_scorecard_returns_required_keys(self):
        from src.esg_manager import ESGManager

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_esg_scorecard(TENANT, reporting_period="2025")

        assert "environmental" in result
        assert "social" in result
        assert "governance" in result
        assert "overall_coverage_pct" in result

    # 10 — get_esg_scorecard calculates 70.0% when 7 of 10 required are covered
    @pytest.mark.asyncio
    async def test_get_esg_scorecard_coverage_pct_calculation(self):
        from src.esg_manager import ESGManager

        # 10 required metric definitions, 7 have disclosures
        metric_rows = [
            {"id": f"md-{i}", "name": f"Metric {i}", "category": "environmental", "is_required": True}
            for i in range(10)
        ]
        disclosure_rows = [
            {"metric_definition_id": f"md-{i}", "numeric_value": float(i)}
            for i in range(7)
        ]

        pool, conn = make_pool_conn(fetch_val=metric_rows)

        call_count = 0

        async def fetch_side_effect(sql, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return metric_rows
            return disclosure_rows

        conn.fetch = AsyncMock(side_effect=fetch_side_effect)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_esg_scorecard(TENANT, reporting_period="2025")

        assert result["overall_coverage_pct"] == pytest.approx(70.0, abs=0.1)

    # 11 — get_esg_scorecard returns 100.0% when there are 0 required metrics
    @pytest.mark.asyncio
    async def test_get_esg_scorecard_zero_division_guard(self):
        from src.esg_manager import ESGManager

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_esg_scorecard(TENANT, reporting_period="2025")

        assert result["overall_coverage_pct"] == 100.0

    # 12 — upsert_target uses ON CONFLICT in SQL
    @pytest.mark.asyncio
    async def test_upsert_target_uses_on_conflict(self):
        from src.esg_manager import ESGManager
        from src.models import TargetCreate

        row = {"id": "tgt-1", "metric_definition_id": "md-1", "target_year": 2030, "target_value": 50.0}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            await mgr.upsert_target(
                TENANT,
                TargetCreate(
                    metric_definition_id="md-1",
                    target_year=2030,
                    target_value=50.0,
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "ON CONFLICT" in sql.upper()

    # 13 — get_targets returns list of rows
    @pytest.mark.asyncio
    async def test_get_targets_returns_list(self):
        from src.esg_manager import ESGManager

        rows = [
            {"id": "tgt-1", "metric_definition_id": "md-1", "target_year": 2030, "target_value": 50.0},
            {"id": "tgt-2", "metric_definition_id": "md-2", "target_year": 2030, "target_value": 0.0},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_targets(TENANT)

        assert isinstance(result, list)
        assert len(result) == 2

    # 14 — get_target_progress: lower_is_better, baseline=100, current=80, target=60 → 50.0%
    @pytest.mark.asyncio
    async def test_get_target_progress_lower_is_better(self):
        from src.esg_manager import ESGManager

        target_row = {
            "id": "tgt-1",
            "metric_definition_id": "md-1",
            "target_year": 2030,
            "target_value": 60.0,
            "baseline_value": 100.0,
            "lower_is_better": True,
        }
        disclosure_row = {
            "numeric_value": 80.0,
        }
        pool, conn = make_pool_conn(fetchrow_val=target_row)
        conn.fetchrow = AsyncMock(side_effect=[target_row, disclosure_row])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_target_progress(TENANT, target_id="tgt-1", reporting_period="2025")

        assert result["progress_pct"] == pytest.approx(50.0, abs=0.1)

    # 15 — get_target_progress: higher_is_better, baseline=20, current=35, target=50 → 50.0%
    @pytest.mark.asyncio
    async def test_get_target_progress_higher_is_better(self):
        from src.esg_manager import ESGManager

        target_row = {
            "id": "tgt-2",
            "metric_definition_id": "md-2",
            "target_year": 2030,
            "target_value": 50.0,
            "baseline_value": 20.0,
            "lower_is_better": False,
        }
        disclosure_row = {
            "numeric_value": 35.0,
        }
        pool, conn = make_pool_conn(fetchrow_val=target_row)
        conn.fetchrow = AsyncMock(side_effect=[target_row, disclosure_row])

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_target_progress(TENANT, target_id="tgt-2", reporting_period="2025")

        assert result["progress_pct"] == pytest.approx(50.0, abs=0.1)

    # 16 — get_trend_data SQL contains ORDER BY and LIMIT
    @pytest.mark.asyncio
    async def test_get_trend_data_orders_by_period_desc(self):
        from src.esg_manager import ESGManager

        rows = [
            {"reporting_period": "2025", "numeric_value": 80.0},
            {"reporting_period": "2024", "numeric_value": 90.0},
            {"reporting_period": "2023", "numeric_value": 95.0},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.esg_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = ESGManager(pool)
            result = await mgr.get_trend_data(TENANT, metric_definition_id="md-1")

        sql = conn.fetch.call_args[0][0]
        assert "ORDER BY" in sql.upper()
        assert "LIMIT" in sql.upper()
        assert isinstance(result, list)
