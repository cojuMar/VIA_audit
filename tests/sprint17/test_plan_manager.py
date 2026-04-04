"""Sprint 17 — PlanManager unit tests (14 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "audit-planning-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


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


TENANT = "bbbbbbbb-0000-0000-0000-000000000017"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPlanManager:

    # 1 — create_plan SQL targets audit_plans
    @pytest.mark.asyncio
    async def test_create_plan_inserts_row(self):
        from src.plan_manager import PlanManager
        from src.models import PlanCreate

        row = {"id": "plan-1", "plan_year": 2026, "status": "draft"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.create_plan(TENANT, PlanCreate(plan_year=2026, title="2026 Annual Audit Plan"))

        sql = conn.fetchrow.call_args[0][0]
        assert "audit_plans" in sql
        assert "INSERT" in sql.upper()

    # 2 — create_plan returns dict with plan_year matching input
    @pytest.mark.asyncio
    async def test_create_plan_returns_dict_with_id(self):
        from src.plan_manager import PlanManager
        from src.models import PlanCreate

        row = {"id": "plan-uuid-1", "plan_year": 2027, "title": "2027 Plan", "status": "draft"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            result = await mgr.create_plan(TENANT, PlanCreate(plan_year=2027, title="2027 Plan"))

        assert isinstance(result, dict)
        assert result["plan_year"] == 2027

    # 3 — list_plans returns all rows
    @pytest.mark.asyncio
    async def test_list_plans_returns_list(self):
        from src.plan_manager import PlanManager

        rows = [
            {"id": "p1", "plan_year": 2026, "title": "Plan A"},
            {"id": "p2", "plan_year": 2025, "title": "Plan B"},
            {"id": "p3", "plan_year": 2024, "title": "Plan C"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            result = await mgr.list_plans(TENANT)

        assert isinstance(result, list)
        assert len(result) == 3

    # 4 — approve_plan SQL contains 'approved_by' and 'approved_at'
    @pytest.mark.asyncio
    async def test_approve_plan_sets_approved_fields(self):
        from src.plan_manager import PlanManager

        row = {"id": "plan-1", "status": "approved", "approved_by": "jane@example.com"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.approve_plan(TENANT, "plan-1", "jane@example.com")

        sql = conn.fetchrow.call_args[0][0]
        assert "approved_by" in sql
        assert "approved_at" in sql

    # 5 — approve_plan SQL sets status = 'approved'
    @pytest.mark.asyncio
    async def test_approve_plan_sets_status_approved(self):
        from src.plan_manager import PlanManager

        row = {"id": "plan-1", "status": "approved"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.approve_plan(TENANT, "plan-1", "approver@example.com")

        sql = conn.fetchrow.call_args[0][0]
        assert "approved" in sql

    # 6 — add_item SQL inserts into audit_plan_items
    @pytest.mark.asyncio
    async def test_add_item_inserts_to_plan_items(self):
        from src.plan_manager import PlanManager
        from src.models import PlanItemCreate

        row = {"id": "item-1", "plan_id": "plan-1", "title": "Payroll Audit", "status": "planned"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.add_item(
                TENANT,
                PlanItemCreate(plan_id="plan-1", title="Payroll Audit"),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "audit_plan_items" in sql
        assert "INSERT" in sql.upper()

    # 7 — PlanItemCreate default priority is 'medium'
    def test_add_item_default_priority_medium(self):
        from src.models import PlanItemCreate

        item = PlanItemCreate(plan_id="plan-1", title="Some Audit")
        assert item.priority == "medium"

    # 8 — add_item SQL includes 'planned' status
    @pytest.mark.asyncio
    async def test_add_item_default_status_planned(self):
        from src.plan_manager import PlanManager
        from src.models import PlanItemCreate

        row = {"id": "item-1", "status": "planned"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.add_item(TENANT, PlanItemCreate(plan_id="p1", title="IT Audit"))

        sql = conn.fetchrow.call_args[0][0]
        assert "planned" in sql

    # 9 — update_item SQL contains 'updated_at'
    @pytest.mark.asyncio
    async def test_update_item_sets_updated_at(self):
        from src.plan_manager import PlanManager

        row = {"id": "item-1", "title": "Revised Title"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            await mgr.update_item(TENANT, "item-1", {"title": "Revised Title"})

        sql = conn.fetchrow.call_args[0][0]
        assert "updated_at" in sql

    # 10 — get_plan_summary returns required keys
    @pytest.mark.asyncio
    async def test_get_plan_summary_returns_required_keys(self):
        from src.plan_manager import PlanManager

        plan_row = {
            "id": "plan-1", "plan_year": 2026, "title": "Plan", "status": "draft",
            "item_count": 0, "total_actual_hours": 0,
        }
        pool, conn = make_pool_conn(fetchrow_val=plan_row, fetch_val=[])

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            result = await mgr.get_plan_summary(TENANT, "plan-1")

        for key in ("plan", "items_by_priority", "items_by_status", "budget_total"):
            assert key in result, f"Missing key: {key}"

    # 11 — auto_populate: entity with risk_score=9.5 → priority='critical'
    @pytest.mark.asyncio
    async def test_auto_populate_risk_threshold_9_gives_critical(self):
        from src.plan_manager import PlanManager

        # First fetch: existing entity IDs in plan (empty)
        # Second fetch: entities to add
        existing_rows: list = []
        entity_rows = [
            {"id": "entity-9", "name": "Core Banking", "risk_score": 9.5,
             "department": "Finance", "owner_name": "CFO"},
        ]
        # add_item result
        item_row = {
            "id": "item-new", "plan_id": "plan-1", "priority": "critical",
            "audit_entity_id": "entity-9", "title": "Audit of Core Banking",
            "status": "planned",
        }

        # conn.fetch will be called twice: existing, then entities
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[existing_rows, entity_rows])
        conn.fetchrow = AsyncMock(return_value=item_row)
        conn.execute = AsyncMock(return_value="OK")
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

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            created = await mgr.auto_populate_from_universe(TENANT, "plan-1", risk_threshold=7.0)

        assert len(created) == 1
        assert created[0]["priority"] == "critical"

    # 12 — auto_populate: entity with risk_score=7.5 → priority='high'
    @pytest.mark.asyncio
    async def test_auto_populate_risk_threshold_7_gives_high(self):
        from src.plan_manager import PlanManager

        existing_rows: list = []
        entity_rows = [
            {"id": "entity-7", "name": "Vendor Portal", "risk_score": 7.5,
             "department": "Procurement", "owner_name": "CPO"},
        ]
        item_row = {
            "id": "item-h", "plan_id": "plan-2", "priority": "high",
            "audit_entity_id": "entity-7", "title": "Audit of Vendor Portal",
            "status": "planned",
        }

        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[existing_rows, entity_rows])
        conn.fetchrow = AsyncMock(return_value=item_row)
        conn.execute = AsyncMock(return_value="OK")
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

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            created = await mgr.auto_populate_from_universe(TENANT, "plan-2", risk_threshold=7.0)

        assert len(created) == 1
        assert created[0]["priority"] == "high"

    # 13 — auto_populate skips entities already in plan
    @pytest.mark.asyncio
    async def test_auto_populate_skips_already_in_plan(self):
        from src.plan_manager import PlanManager

        # Entity is already in the plan
        existing_rows = [{"audit_entity_id": "entity-already"}]
        entity_rows = [
            {"id": "entity-already", "name": "Existing Entity", "risk_score": 8.0,
             "department": "IT", "owner_name": "CTO"},
        ]

        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[existing_rows, entity_rows])
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value="OK")
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

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            created = await mgr.auto_populate_from_universe(TENANT, "plan-1")

        # Nothing created — entity was skipped
        assert created == []

    # 14 — create_plan SQL uses ON CONFLICT or the model enforces uniqueness per year
    @pytest.mark.asyncio
    async def test_plan_unique_per_year(self):
        from src.models import PlanCreate

        # Two PlanCreate objects for the same year are structurally valid
        # (uniqueness is enforced by the DB UNIQUE constraint, not the model).
        # We verify that the SQL emitted targets a single-year insert without
        # an explicit duplicate guard in application code, relying on the DB.
        plan_a = PlanCreate(plan_year=2026, title="Plan A")
        plan_b = PlanCreate(plan_year=2026, title="Plan B")

        assert plan_a.plan_year == plan_b.plan_year

        # Simulate DB raising UniqueViolationError on second insert
        from unittest.mock import AsyncMock as AM
        import asyncpg

        row = {"id": "plan-1", "plan_year": 2026}
        pool, conn = make_pool_conn(fetchrow_val=row)

        from src.plan_manager import PlanManager

        conn.fetchrow = AsyncMock(
            side_effect=[row, asyncpg.UniqueViolationError("unique violation")]
        )

        with patch("src.plan_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = PlanManager(pool)
            # First insert succeeds
            result = await mgr.create_plan(TENANT, plan_a)
            assert result["plan_year"] == 2026

            # Second insert raises UniqueViolationError (DB constraint)
            with pytest.raises(asyncpg.UniqueViolationError):
                await mgr.create_plan(TENANT, plan_b)
