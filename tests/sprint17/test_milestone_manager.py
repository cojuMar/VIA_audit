"""Sprint 17 — MilestoneManager unit tests (8 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "audit-planning-service"),
)

import pytest
from datetime import date, timedelta
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


TENANT = "dddddddd-0000-0000-0000-000000000017"
ENG_ID = "engagement-ms-001"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMilestoneManager:

    # 1 — create_milestone SQL inserts into audit_milestones
    @pytest.mark.asyncio
    async def test_create_milestone_inserts_row(self):
        from src.milestone_manager import MilestoneManager
        from src.models import MilestoneCreate

        future_due = (date.today() + timedelta(days=14)).isoformat()
        row = {
            "id": "ms-1", "engagement_id": ENG_ID,
            "title": "Kickoff Meeting", "status": "pending",
            "due_date": future_due,
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            result = await mgr.create_milestone(
                TENANT,
                MilestoneCreate(
                    engagement_id=ENG_ID,
                    title="Kickoff Meeting",
                    due_date=future_due,
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "audit_milestones" in sql
        assert "INSERT" in sql.upper()
        assert isinstance(result, dict)

    # 2 — create_milestone sets status='overdue' when due_date is in the past
    @pytest.mark.asyncio
    async def test_create_milestone_overdue_if_past_due(self):
        from src.milestone_manager import MilestoneManager
        from src.models import MilestoneCreate

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        row = {
            "id": "ms-2", "engagement_id": ENG_ID,
            "title": "Overdue Task", "status": "overdue",
            "due_date": yesterday,
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            result = await mgr.create_milestone(
                TENANT,
                MilestoneCreate(
                    engagement_id=ENG_ID,
                    title="Overdue Task",
                    due_date=yesterday,
                ),
            )

        # Verify the 'overdue' status was passed as a parameter to fetchrow
        call_args = conn.fetchrow.call_args[0]
        params = call_args[1:]  # skip sql
        assert "overdue" in params, "Expected 'overdue' to be passed as status param"

    # 3 — complete_milestone SQL sets completed_date and status='completed'
    @pytest.mark.asyncio
    async def test_complete_milestone_sets_completed_date(self):
        from src.milestone_manager import MilestoneManager

        row = {
            "id": "ms-3", "status": "completed",
            "completed_date": "2026-04-01",
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            result = await mgr.complete_milestone(
                TENANT, "ms-3", completed_date="2026-04-01"
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "completed_date" in sql
        assert "completed" in sql

    # 4 — complete_milestone without completed_date uses CURRENT_DATE in SQL
    @pytest.mark.asyncio
    async def test_complete_milestone_defaults_to_today(self):
        from src.milestone_manager import MilestoneManager

        row = {"id": "ms-4", "status": "completed", "completed_date": None}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            await mgr.complete_milestone(TENANT, "ms-4")

        sql = conn.fetchrow.call_args[0][0]
        assert "CURRENT_DATE" in sql

    # 5 — get_engagement_milestones SQL orders by due_date
    @pytest.mark.asyncio
    async def test_get_engagement_milestones_ordered_by_due(self):
        from src.milestone_manager import MilestoneManager

        today = date.today()
        rows = [
            {"id": "ms-a", "engagement_id": ENG_ID, "title": "Early",
             "due_date": today + timedelta(days=3), "status": "pending",
             "completed_date": None},
            {"id": "ms-b", "engagement_id": ENG_ID, "title": "Later",
             "due_date": today + timedelta(days=10), "status": "pending",
             "completed_date": None},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            result = await mgr.get_engagement_milestones(TENANT, ENG_ID)

        sql = conn.fetch.call_args[0][0]
        assert "ORDER BY" in sql.upper()
        assert "due_date" in sql
        assert len(result) == 2

    # 6 — check_overdue_milestones UPDATE sets status='overdue'
    @pytest.mark.asyncio
    async def test_check_overdue_updates_status(self):
        from src.milestone_manager import MilestoneManager

        overdue_rows = [
            {"id": "ms-old", "status": "overdue", "engagement_id": ENG_ID},
        ]
        pool, conn = make_pool_conn(fetch_val=overdue_rows)

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            result = await mgr.check_overdue_milestones(TENANT)

        sql = conn.fetch.call_args[0][0]
        assert "UPDATE" in sql.upper()
        assert "overdue" in sql
        assert isinstance(result, list)

    # 7 — seed_default_milestones creates exactly 8 milestones
    @pytest.mark.asyncio
    async def test_seed_default_milestones_creates_8(self):
        from src.milestone_manager import MilestoneManager

        start = "2026-05-01"
        end = "2026-06-30"

        call_count = 0

        async def fake_create(tenant_id, data):
            nonlocal call_count
            call_count += 1
            return {
                "id": f"ms-seed-{call_count}",
                "title": data.title,
                "due_date": data.due_date,
                "status": "pending",
            }

        pool, conn = make_pool_conn()

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            mgr.create_milestone = fake_create  # type: ignore[method-assign]
            created = await mgr.seed_default_milestones(TENANT, ENG_ID, start, end)

        assert len(created) == 8

    # 8 — first seeded milestone due_date equals planned_start_date
    @pytest.mark.asyncio
    async def test_seed_milestones_kickoff_equals_start_date(self):
        from src.milestone_manager import MilestoneManager

        start = "2026-06-01"
        end = "2026-07-31"
        recorded: list[dict] = []

        async def fake_create(tenant_id, data):
            ms = {
                "id": f"ms-{len(recorded) + 1}",
                "title": data.title,
                "due_date": data.due_date,
                "status": "pending",
            }
            recorded.append(ms)
            return ms

        pool, conn = make_pool_conn()

        with patch("src.milestone_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MilestoneManager(pool)
            mgr.create_milestone = fake_create  # type: ignore[method-assign]
            await mgr.seed_default_milestones(TENANT, ENG_ID, start, end)

        # First milestone (kickoff) must be due on the planned start date
        assert recorded[0]["due_date"] == start
