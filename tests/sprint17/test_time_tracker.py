"""Sprint 17 — TimeTracker unit tests (12 tests)."""
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


TENANT = "cccccccc-0000-0000-0000-000000000017"
ENG_ID = "engagement-uuid-001"


def _base_entry(**overrides):
    """Return kwargs for TimeEntryCreate with safe defaults."""
    defaults = {
        "engagement_id": ENG_ID,
        "auditor_name": "Alice Auditor",
        "auditor_email": "alice@example.com",
        "hours": 4.0,
        "activity_type": "fieldwork",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTimeTracker:

    # 1 — log_hours emits INSERT (never UPDATE or DELETE)
    @pytest.mark.asyncio
    async def test_log_hours_inserts_immutable(self):
        from src.time_tracker import TimeTracker
        from src.models import TimeEntryCreate

        row = {"id": "te-1", "engagement_id": ENG_ID, "hours": 4.0}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            await tracker.log_hours(TENANT, TimeEntryCreate(**_base_entry()))

        sql = conn.fetchrow.call_args[0][0]
        assert "INSERT" in sql.upper()
        assert "UPDATE" not in sql.upper()
        assert "DELETE" not in sql.upper()

    # 2 — log_hours uses CURRENT_DATE when entry_date is None
    @pytest.mark.asyncio
    async def test_log_hours_defaults_today(self):
        from src.time_tracker import TimeTracker
        from src.models import TimeEntryCreate

        row = {"id": "te-2", "hours": 2.0}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            await tracker.log_hours(TENANT, TimeEntryCreate(**_base_entry(entry_date=None)))

        sql = conn.fetchrow.call_args[0][0]
        assert "CURRENT_DATE" in sql

    # 3 — TimeEntryCreate with hours=0 raises ValidationError
    def test_log_hours_validates_positive_hours(self):
        from src.models import TimeEntryCreate

        with pytest.raises(ValidationError) as exc_info:
            TimeEntryCreate(**_base_entry(hours=0))

        assert "hours" in str(exc_info.value).lower() or "greater than 0" in str(exc_info.value)

    # 4 — TimeEntryCreate with hours=25 raises ValidationError
    def test_log_hours_max_24_hours(self):
        from src.models import TimeEntryCreate

        with pytest.raises(ValidationError) as exc_info:
            TimeEntryCreate(**_base_entry(hours=25))

        assert "hours" in str(exc_info.value).lower() or "24" in str(exc_info.value)

    # 5 — get_engagement_hours variance: budget=100, total=80 → variance=20 (under budget)
    @pytest.mark.asyncio
    async def test_get_engagement_hours_returns_variance(self):
        from src.time_tracker import TimeTracker

        eng_row = {"budget_hours": 100.0}
        total_row = {"total_hours": 80.0}

        conn = AsyncMock()
        # Called in order: fetchrow(eng), fetchrow(total), fetch(activity), fetch(auditor), fetch(daily)
        conn.fetchrow = AsyncMock(side_effect=[eng_row, total_row])
        conn.fetch = AsyncMock(return_value=[])
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

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            result = await tracker.get_engagement_hours(TENANT, ENG_ID)

        # variance = budget - total = 100 - 80 = 20 (remaining hours, positive = under budget)
        assert result["total_hours"] == 80.0
        assert result["budget_hours"] == 100.0
        assert result["variance"] == 20.0
        assert result["variance_pct"] == 20.0

    # 6 — get_engagement_hours over budget: total=110, budget=100 → variance=-10 (negative = over)
    @pytest.mark.asyncio
    async def test_get_engagement_hours_over_budget(self):
        from src.time_tracker import TimeTracker

        eng_row = {"budget_hours": 100.0}
        total_row = {"total_hours": 110.0}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[eng_row, total_row])
        conn.fetch = AsyncMock(return_value=[])
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

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            result = await tracker.get_engagement_hours(TENANT, ENG_ID)

        # variance = budget - total = 100 - 110 = -10 (negative means over budget)
        assert result["variance"] == -10.0

    # 7 — get_engagement_hours result has all required keys
    @pytest.mark.asyncio
    async def test_get_engagement_hours_required_keys(self):
        from src.time_tracker import TimeTracker

        eng_row = {"budget_hours": 80.0}
        total_row = {"total_hours": 60.0}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[eng_row, total_row])
        conn.fetch = AsyncMock(return_value=[])
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

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            result = await tracker.get_engagement_hours(TENANT, ENG_ID)

        for key in ("total_hours", "budget_hours", "variance", "variance_pct",
                    "by_activity", "by_auditor", "daily_trend"):
            assert key in result, f"Missing key: {key}"

    # 8 — get_auditor_utilization groups auditor rows (SQL groups by auditor)
    @pytest.mark.asyncio
    async def test_get_auditor_utilization_groups_by_auditor(self):
        from src.time_tracker import TimeTracker

        # Both rows for same auditor (SQL groups them — we mock the aggregated return)
        aggregated_rows = [
            {
                "auditor_name": "Bob Smith",
                "auditor_email": "bob@example.com",
                "total_hours": 32.0,
                "billable_hours": 28.0,
            }
        ]
        pool, conn = make_pool_conn(fetch_val=aggregated_rows)

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            result = await tracker.get_auditor_utilization(
                TENANT, "2026-01-01", "2026-03-31"
            )

        sql_calls = [str(c) for c in conn.fetch.call_args_list]
        assert any("auditor" in s.lower() or "GROUP BY" in s for s in sql_calls)
        assert len(result) == 1
        assert result[0]["auditor_name"] == "Bob Smith"

    # 9 — get_time_report applies date filter in SQL
    @pytest.mark.asyncio
    async def test_get_time_report_applies_date_filter(self):
        from src.time_tracker import TimeTracker

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            await tracker.get_time_report(
                TENANT,
                start_date="2026-01-01",
                end_date="2026-03-31",
            )

        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]
        assert "entry_date" in sql
        assert "2026-01-01" in params
        assert "2026-03-31" in params

    # 10 — get_time_report applies engagement_id filter in SQL
    @pytest.mark.asyncio
    async def test_get_time_report_applies_engagement_filter(self):
        from src.time_tracker import TimeTracker

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            await tracker.get_time_report(TENANT, engagement_id=ENG_ID)

        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]
        assert "engagement_id" in sql
        assert ENG_ID in params

    # 11 — get_budget_status: engagement with logged > budget appears in over_budget_engagements
    @pytest.mark.asyncio
    async def test_get_budget_status_returns_over_budget_list(self):
        from src.time_tracker import TimeTracker

        # logged_hours (120) > budget_hours (100) → over budget
        over_budget_row = {
            "engagement_id": "eng-1",
            "title": "Big Audit",
            "engagement_code": "AUD-2026-001",
            "budget_hours": 100.0,
            "logged_hours": 120.0,
        }
        ok_row = {
            "engagement_id": "eng-2",
            "title": "Small Audit",
            "engagement_code": "AUD-2026-002",
            "budget_hours": 50.0,
            "logged_hours": 40.0,
        }
        pool, conn = make_pool_conn(fetch_val=[over_budget_row, ok_row])

        with patch("src.time_tracker.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            tracker = TimeTracker(pool)
            result = await tracker.get_budget_status(TENANT, "plan-1")

        assert "over_budget_engagements" in result
        over = result["over_budget_engagements"]
        assert len(over) == 1
        assert over[0]["title"] == "Big Audit"

    # 12 — TimeEntryCreate default activity_type is 'fieldwork'
    def test_time_entry_activity_type_default_fieldwork(self):
        from src.models import TimeEntryCreate

        entry = TimeEntryCreate(
            engagement_id="eng-1",
            auditor_name="Carol",
            hours=2.0,
        )
        assert entry.activity_type == "fieldwork"
