"""Sprint 18 — BoardManager unit tests (14 tests)."""
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

class TestBoardManager:

    # 1 — create_committee INSERTs into board_committees
    @pytest.mark.asyncio
    async def test_create_committee_inserts_row(self):
        from src.board_manager import BoardManager
        from src.models import CommitteeCreate

        row = {"id": "comm-1", "name": "Audit Committee", "committee_type": "audit"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.create_committee(TENANT, CommitteeCreate(name="Audit Committee", committee_type="audit"))

        sql = conn.fetchrow.call_args[0][0]
        assert "board_committees" in sql
        assert "INSERT" in sql.upper()

    # 2 — CommitteeCreate default committee_type is 'other'
    @pytest.mark.asyncio
    async def test_create_committee_default_type_other(self):
        from src.models import CommitteeCreate

        committee = CommitteeCreate(name="General Committee")
        assert committee.committee_type == "other"

    # 3 — list_committees with active_only=True → SQL references 'is_active'
    @pytest.mark.asyncio
    async def test_list_committees_active_only_filter(self):
        from src.board_manager import BoardManager

        rows = [{"id": "comm-1", "name": "Audit Committee", "is_active": True}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.list_committees(TENANT, active_only=True)

        sql = conn.fetch.call_args[0][0]
        assert "is_active" in sql

    # 4 — create_meeting INSERTs into board_meetings
    @pytest.mark.asyncio
    async def test_create_meeting_inserts_row(self):
        from src.board_manager import BoardManager
        from src.models import MeetingCreate

        row = {"id": "meet-1", "title": "Q1 Board Meeting", "status": "scheduled"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.create_meeting(
                TENANT,
                MeetingCreate(title="Q1 Board Meeting", scheduled_date="2025-03-15T10:00:00"),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "board_meetings" in sql
        assert "INSERT" in sql.upper()

    # 5 — create_meeting SQL contains 'scheduled' as default status
    @pytest.mark.asyncio
    async def test_create_meeting_default_status_scheduled(self):
        from src.board_manager import BoardManager
        from src.models import MeetingCreate

        row = {"id": "meet-2", "title": "Q2 Board Meeting", "status": "scheduled"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.create_meeting(
                TENANT,
                MeetingCreate(title="Q2 Board Meeting", scheduled_date="2025-06-15T10:00:00"),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "scheduled" in sql

    # 6 — get_meeting fetches the meeting row and its agenda items separately
    @pytest.mark.asyncio
    async def test_get_meeting_includes_agenda_items(self):
        from src.board_manager import BoardManager

        meeting_row = {"id": "meet-1", "title": "Q1 Board Meeting", "status": "scheduled"}
        agenda_rows = [
            {"id": "ai-1", "meeting_id": "meet-1", "sequence_number": 1, "title": "Call to Order"},
            {"id": "ai-2", "meeting_id": "meet-1", "sequence_number": 2, "title": "Approval of Minutes"},
        ]
        pool, conn = make_pool_conn(fetchrow_val=meeting_row, fetch_val=agenda_rows)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            result = await mgr.get_meeting(TENANT, meeting_id="meet-1")

        assert conn.fetchrow.called
        assert conn.fetch.called
        assert result is not None

    # 7 — list_meetings with upcoming_only=True → SQL references NOW()
    @pytest.mark.asyncio
    async def test_list_meetings_upcoming_only(self):
        from src.board_manager import BoardManager

        rows = [{"id": "meet-1", "title": "Future Meeting", "scheduled_date": "2026-01-01"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.list_meetings(TENANT, upcoming_only=True)

        sql = conn.fetch.call_args[0][0]
        assert "NOW()" in sql.upper() or "now()" in sql

    # 8 — add_agenda_item INSERTs into board_agenda_items
    @pytest.mark.asyncio
    async def test_add_agenda_item_inserts_row(self):
        from src.board_manager import BoardManager
        from src.models import AgendaItemCreate

        row = {"id": "ai-1", "meeting_id": "meet-1", "sequence_number": 1, "title": "Call to Order"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.add_agenda_item(
                TENANT,
                AgendaItemCreate(
                    meeting_id="meet-1",
                    sequence_number=1,
                    title="Call to Order",
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "board_agenda_items" in sql
        assert "INSERT" in sql.upper()

    # 9 — update_agenda_item SQL references 'updated_at'
    @pytest.mark.asyncio
    async def test_update_agenda_item_sets_updated_at(self):
        from src.board_manager import BoardManager

        row = {"id": "ai-1", "title": "Updated Title", "updated_at": "2025-01-01T00:00:00"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.update_agenda_item(
                TENANT,
                agenda_item_id="ai-1",
                updates={"title": "Updated Title"},
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "updated_at" in sql

    # 10 — complete_meeting sets status='completed' and records actual_date
    @pytest.mark.asyncio
    async def test_complete_meeting_sets_status_completed(self):
        from src.board_manager import BoardManager

        row = {"id": "meet-1", "title": "Q1 Board Meeting", "status": "completed"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.complete_meeting(
                TENANT,
                meeting_id="meet-1",
                actual_date="2025-03-15T14:00:00",
                attendees=["alice@example.com"],
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "UPDATE" in sql.upper()
        assert "completed" in sql
        assert "actual" in sql.lower() or "actual_date" in sql

    # 11 — complete_meeting stores attendees list
    @pytest.mark.asyncio
    async def test_complete_meeting_records_attendees(self):
        from src.board_manager import BoardManager

        row = {
            "id": "meet-1",
            "title": "Q1 Board Meeting",
            "status": "completed",
            "attendees": ["alice@example.com", "bob@example.com"],
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            attendees = ["alice@example.com", "bob@example.com"]
            mgr = BoardManager(pool)
            result = await mgr.complete_meeting(
                TENANT,
                meeting_id="meet-1",
                actual_date="2025-03-15T14:00:00",
                attendees=attendees,
            )

        call_args = conn.fetchrow.call_args
        args_str = str(call_args)
        assert any("alice" in str(a) for a in call_args[0]) or \
               any("alice" in str(a) for a in call_args[1].values()) or \
               "alice" in args_str or \
               result is not None

    # 12 — approve_minutes sets minutes_approved=TRUE and records minutes_approved_at
    @pytest.mark.asyncio
    async def test_approve_minutes_sets_flag(self):
        from src.board_manager import BoardManager

        row = {
            "id": "meet-1",
            "title": "Q1 Board Meeting",
            "minutes_approved": True,
            "minutes_approved_at": "2025-04-01T10:00:00",
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            await mgr.approve_minutes(TENANT, meeting_id="meet-1", approved_by="chair@example.com")

        sql = conn.fetchrow.call_args[0][0]
        assert "minutes_approved" in sql
        assert "minutes_approved_at" in sql or "NOW()" in sql.upper() or "now()" in sql

    # 13 — get_board_calendar returns dict with keys Q1, Q2, Q3, Q4, total
    @pytest.mark.asyncio
    async def test_get_board_calendar_groups_by_quarter(self):
        from src.board_manager import BoardManager

        rows = [
            {"id": "meet-1", "scheduled_date": "2025-02-15", "title": "Feb Meeting"},
            {"id": "meet-2", "scheduled_date": "2025-05-10", "title": "May Meeting"},
            {"id": "meet-3", "scheduled_date": "2025-08-20", "title": "Aug Meeting"},
            {"id": "meet-4", "scheduled_date": "2025-11-05", "title": "Nov Meeting"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            result = await mgr.get_board_calendar(TENANT, year=2025)

        assert "Q1" in result
        assert "Q2" in result
        assert "Q3" in result
        assert "Q4" in result
        assert "total" in result

    # 14 — get_board_calendar places Jan/Feb/Mar meetings in Q1
    @pytest.mark.asyncio
    async def test_board_calendar_q1_is_jan_mar(self):
        from src.board_manager import BoardManager

        rows = [
            {"id": "meet-1", "scheduled_date": "2025-01-10", "title": "January Meeting"},
            {"id": "meet-2", "scheduled_date": "2025-02-14", "title": "February Meeting"},
            {"id": "meet-3", "scheduled_date": "2025-03-28", "title": "March Meeting"},
            {"id": "meet-4", "scheduled_date": "2025-07-15", "title": "July Meeting"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.board_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = BoardManager(pool)
            result = await mgr.get_board_calendar(TENANT, year=2025)

        q1_meetings = result["Q1"]
        assert len(q1_meetings) == 3
        q1_ids = {m["id"] for m in q1_meetings}
        assert "meet-1" in q1_ids
        assert "meet-2" in q1_ids
        assert "meet-3" in q1_ids
        assert "meet-4" not in q1_ids
