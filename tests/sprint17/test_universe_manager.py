"""Sprint 17 — UniverseManager unit tests (14 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "audit-planning-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


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


TENANT = "aaaaaaaa-0000-0000-0000-000000000017"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUniverseManager:

    # 1 — create_entity returns dict with 'id'
    @pytest.mark.asyncio
    async def test_create_entity_returns_dict(self):
        from src.universe_manager import UniverseManager
        from src.models import EntityCreate

        row = {
            "id": "entity-uuid-1",
            "name": "Payroll System",
            "risk_score": 7.5,
            "in_universe": True,
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.create_entity(
                TENANT, EntityCreate(name="Payroll System", risk_score=7.5)
            )

        assert isinstance(result, dict)
        assert result["id"] == "entity-uuid-1"

    # 2 — create_entity inserts into audit_entities
    @pytest.mark.asyncio
    async def test_create_entity_inserts_to_correct_table(self):
        from src.universe_manager import UniverseManager
        from src.models import EntityCreate

        row = {"id": "e1", "name": "HR Portal"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            await mgr.create_entity(TENANT, EntityCreate(name="HR Portal"))

        call_args = conn.fetchrow.call_args
        sql = call_args[0][0]
        assert "audit_entities" in sql

    # 3 — list_entities default filters by is_in_universe / in_universe = true
    @pytest.mark.asyncio
    async def test_list_entities_default_in_universe_only(self):
        from src.universe_manager import UniverseManager

        rows = [{"id": "e1", "name": "A"}, {"id": "e2", "name": "B"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.list_entities(TENANT)

        assert len(result) == 2
        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        assert "in_universe" in sql

    # 4 — list_entities with entity_type_id filter passes param
    @pytest.mark.asyncio
    async def test_list_entities_filter_by_type(self):
        from src.universe_manager import UniverseManager

        pool, conn = make_pool_conn(fetch_val=[{"id": "e1", "name": "A"}])

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            await mgr.list_entities(TENANT, entity_type_id="type-uuid-99")

        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]
        assert "entity_type_id" in sql
        assert "type-uuid-99" in params

    # 5 — list_entities with min_risk_score filter
    @pytest.mark.asyncio
    async def test_list_entities_filter_by_min_risk_score(self):
        from src.universe_manager import UniverseManager

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            await mgr.list_entities(TENANT, min_risk_score=7.0)

        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]
        assert "risk_score" in sql
        assert 7.0 in params

    # 6 — list_entities SQL orders by risk_score DESC
    @pytest.mark.asyncio
    async def test_list_entities_orders_by_risk_score_desc(self):
        from src.universe_manager import UniverseManager

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            await mgr.list_entities(TENANT)

        sql = conn.fetch.call_args[0][0]
        assert "ORDER BY" in sql.upper()
        assert "risk_score" in sql
        assert "DESC" in sql.upper()

    # 7 — update_entity SQL contains 'updated_at'
    @pytest.mark.asyncio
    async def test_update_entity_sets_updated_at(self):
        from src.universe_manager import UniverseManager

        row = {"id": "e1", "name": "Updated Name"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            await mgr.update_entity(TENANT, "e1", {"name": "Updated Name"})

        sql = conn.fetchrow.call_args[0][0]
        assert "updated_at" in sql

    # 8 — get_entity returns None when fetchrow returns None
    @pytest.mark.asyncio
    async def test_get_entity_returns_none_when_not_found(self):
        from src.universe_manager import UniverseManager

        pool, conn = make_pool_conn(fetchrow_val=None)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.get_entity(TENANT, "non-existent-id")

        assert result is None

    # 9 — get_entity_types uses pool.acquire directly (no tenant RLS)
    @pytest.mark.asyncio
    async def test_get_entity_types_no_tenant_required(self):
        from src.universe_manager import UniverseManager

        rows = [
            {"id": "t1", "display_name": "Application"},
            {"id": "t2", "display_name": "Business Process"},
            {"id": "t3", "display_name": "Vendor"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        mgr = UniverseManager(pool)
        result = await mgr.get_entity_types()

        assert isinstance(result, list)
        assert len(result) == 3
        # Should use pool.acquire, not tenant_conn
        pool.acquire.assert_called_once()

    # 10 — calculate_coverage returns the four required keys
    @pytest.mark.asyncio
    async def test_calculate_coverage_returns_required_keys(self):
        from src.universe_manager import UniverseManager

        summary_row = {
            "total_entities": 10,
            "entities_with_audits": 7,
            "high_risk_unaudited_json": None,
        }
        pool, conn = make_pool_conn(fetchrow_val=summary_row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.calculate_universe_coverage(TENANT, 2026)

        for key in ("total_entities", "entities_with_audits", "coverage_pct", "high_risk_unaudited"):
            assert key in result, f"Missing key: {key}"

    # 11 — coverage_pct calculation: total=10, with_audits=7 → 70.0
    @pytest.mark.asyncio
    async def test_coverage_pct_calculation(self):
        from src.universe_manager import UniverseManager

        summary_row = {
            "total_entities": 10,
            "entities_with_audits": 7,
            "high_risk_unaudited_json": None,
        }
        pool, conn = make_pool_conn(fetchrow_val=summary_row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.calculate_universe_coverage(TENANT, 2026)

        assert result["coverage_pct"] == 70.0

    # 12 — coverage_pct is 0.0 when total_entities=0 (no ZeroDivisionError)
    @pytest.mark.asyncio
    async def test_coverage_pct_zero_when_no_entities(self):
        from src.universe_manager import UniverseManager

        summary_row = {
            "total_entities": 0,
            "entities_with_audits": 0,
            "high_risk_unaudited_json": None,
        }
        pool, conn = make_pool_conn(fetchrow_val=summary_row)

        with patch("src.universe_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = UniverseManager(pool)
            result = await mgr.calculate_universe_coverage(TENANT, 2026)

        assert result["coverage_pct"] == 0.0

    # 13 — EntityCreate default risk_score is 5.0
    def test_entity_risk_score_default_5(self):
        from src.models import EntityCreate

        entity = EntityCreate(name="Test Entity")
        assert entity.risk_score == 5.0

    # 14 — EntityCreate default audit_frequency_months is 12
    def test_entity_audit_frequency_default_12(self):
        from src.models import EntityCreate

        entity = EntityCreate(name="Test Entity")
        assert entity.audit_frequency_months == 12
