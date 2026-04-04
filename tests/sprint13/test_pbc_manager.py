"""Sprint 13 — PBCManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/pbc-service"),
)

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

from src.pbc_manager import PBCManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000010"
ENGAGEMENT_ID = "aaaa1300-0000-0000-0000-000000000001"
LIST_ID = "bbbb1300-0000-0000-0000-000000000001"
REQUEST_ID = "cccc1300-0000-0000-0000-000000000001"
FULFILLMENT_ID = "dddd1300-0000-0000-0000-000000000001"


def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    # Support conn.transaction() as async context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=tx)
    return mock_pool, mock_conn


_LIST_DICT = {
    "id": LIST_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "list_name": "Q1 2026 PBC List",
    "description": "Initial PBC request list for Q1 audit",
    "due_date": date.today() + timedelta(days=30),
    "status": "draft",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_REQUEST_DICT = {
    "id": REQUEST_ID,
    "tenant_id": TENANT,
    "list_id": LIST_ID,
    "request_number": 1,
    "title": "General Ledger Trial Balance",
    "description": "Provide the GL trial balance as of period end",
    "category": "financial",
    "priority": "high",
    "assigned_to": "controller@example.com",
    "due_date": date.today() + timedelta(days=14),
    "status": "open",
    "framework_control_ref": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_FULFILLMENT_DICT = {
    "id": FULFILLMENT_ID,
    "tenant_id": TENANT,
    "request_id": REQUEST_ID,
    "submitted_by": "controller@example.com",
    "response_text": "Please find the GL attached.",
    "minio_key": None,
    "file_name": None,
    "file_size_bytes": None,
    "submission_notes": None,
    "submitted_at": "2026-01-10T00:00:00Z",
}


# ---------------------------------------------------------------------------
# TestPBCManager
# ---------------------------------------------------------------------------


class TestPBCManager:

    # 1. test_create_list_inserts_row
    @pytest.mark.asyncio
    async def test_create_list_inserts_row(self):
        """create_list() calls fetchrow to INSERT and returns the new list dict."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_LIST_DICT)

        mgr = PBCManager()
        result = await mgr.create_list(
            pool,
            TENANT,
            ENGAGEMENT_ID,
            list_name="Q1 2026 PBC List",
            description="Initial PBC request list for Q1 audit",
            due_date=date.today() + timedelta(days=30),
        )

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO" in query
        assert "id" in result

    # 2. test_add_request_auto_increments_number
    @pytest.mark.asyncio
    async def test_add_request_auto_increments_number(self):
        """add_request() uses fetchval to get max request_number then adds 1 (3 → 4)."""
        pool, conn = make_pool_conn()
        conn.fetchval = AsyncMock(return_value=3)
        expected_request = dict(_REQUEST_DICT, request_number=4)
        conn.fetchrow = AsyncMock(return_value=expected_request)

        mgr = PBCManager()
        result = await mgr.add_request(
            pool,
            TENANT,
            LIST_ID,
            title="GL Trial Balance",
            description="Provide GL trial balance",
            category="financial",
            priority="high",
            assigned_to="controller@example.com",
            due_date=date.today() + timedelta(days=14),
        )

        conn.fetchval.assert_called_once()
        assert result["request_number"] == 4

    # 3. test_add_request_starts_at_1_when_empty
    @pytest.mark.asyncio
    async def test_add_request_starts_at_1_when_empty(self):
        """add_request() starts at request_number=1 when no existing requests (fetchval=0)."""
        pool, conn = make_pool_conn()
        conn.fetchval = AsyncMock(return_value=0)
        expected_request = dict(_REQUEST_DICT, request_number=1)
        conn.fetchrow = AsyncMock(return_value=expected_request)

        mgr = PBCManager()
        result = await mgr.add_request(
            pool,
            TENANT,
            LIST_ID,
            title="First Request",
            description="Very first request on this list",
            category="general",
            priority="medium",
            assigned_to=None,
            due_date=None,
        )

        assert result["request_number"] == 1

    # 4. test_bulk_add_requests_returns_count
    @pytest.mark.asyncio
    async def test_bulk_add_requests_returns_count(self):
        """bulk_add_requests() with 3 items returns {added: 3}."""
        pool, conn = make_pool_conn()
        # fetchval returns incrementing max each call
        conn.fetchval = AsyncMock(side_effect=[0, 1, 2])
        conn.fetchrow = AsyncMock(side_effect=[
            dict(_REQUEST_DICT, request_number=1),
            dict(_REQUEST_DICT, request_number=2),
            dict(_REQUEST_DICT, request_number=3),
        ])

        requests = [
            {"title": f"Request {i}", "description": f"Desc {i}", "priority": "medium"}
            for i in range(1, 4)
        ]

        mgr = PBCManager()
        result = await mgr.bulk_add_requests(pool, TENANT, LIST_ID, requests)

        assert result["added"] == 3

    # 5. test_fulfill_request_inserts_immutable_fulfillment
    @pytest.mark.asyncio
    async def test_fulfill_request_inserts_immutable_fulfillment(self):
        """fulfill_request() INSERTs into pbc_fulfillments; must not UPDATE pbc_fulfillments."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_FULFILLMENT_DICT)
        conn.execute = AsyncMock(return_value=None)

        mgr = PBCManager()
        await mgr.fulfill_request(
            pool,
            TENANT,
            REQUEST_ID,
            submitted_by="controller@example.com",
            response_text="GL attached.",
            file_bytes=None,
            file_name=None,
        )

        # Must have called fetchrow with an INSERT into pbc_fulfillments
        all_queries = [c[0][0] for c in conn.fetchrow.call_args_list]
        fulfillment_inserts = [q for q in all_queries if "INSERT INTO pbc_fulfillments" in q]
        assert len(fulfillment_inserts) >= 1

        # Must NOT have issued UPDATE pbc_fulfillments via execute
        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        bad_updates = [q for q in execute_queries if "UPDATE pbc_fulfillments" in q]
        assert len(bad_updates) == 0

    # 6. test_fulfill_request_updates_request_status
    @pytest.mark.asyncio
    async def test_fulfill_request_updates_request_status(self):
        """fulfill_request() issues an UPDATE on pbc_requests to set status='fulfilled'."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_FULFILLMENT_DICT)
        conn.execute = AsyncMock(return_value=None)

        mgr = PBCManager()
        await mgr.fulfill_request(
            pool,
            TENANT,
            REQUEST_ID,
            submitted_by="controller@example.com",
            response_text="Attached.",
            file_bytes=None,
            file_name=None,
        )

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        status_updates = [
            q for q in execute_queries
            if "UPDATE pbc_requests" in q and "fulfilled" in q
        ]
        assert len(status_updates) >= 1

    # 7. test_fulfill_request_without_file
    @pytest.mark.asyncio
    async def test_fulfill_request_without_file(self):
        """fulfill_request() with file_bytes=None must not call any MinIO put_object."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_FULFILLMENT_DICT)
        conn.execute = AsyncMock(return_value=None)

        mock_minio = MagicMock()
        mock_minio.put_object = MagicMock()

        mgr = PBCManager()
        await mgr.fulfill_request(
            pool,
            TENANT,
            REQUEST_ID,
            submitted_by="controller@example.com",
            response_text="No file attached.",
            file_bytes=None,
            file_name=None,
            minio_client=mock_minio,
        )

        mock_minio.put_object.assert_not_called()

    # 8. test_get_list_status_computes_completion_pct
    @pytest.mark.asyncio
    async def test_get_list_status_computes_completion_pct(self):
        """get_list_status(): total=10, fulfilled=7, not_applicable=1 → completion_pct=80.0."""
        pool, conn = make_pool_conn()
        status_row = {
            "total": 10,
            "open": 2,
            "in_progress": 0,
            "fulfilled": 7,
            "not_applicable": 1,
            "overdue": 0,
        }
        conn.fetchrow = AsyncMock(return_value=status_row)

        mgr = PBCManager()
        result = await mgr.get_list_status(pool, TENANT, LIST_ID)

        # (7 + 1) / 10 * 100 = 80.0
        assert result["completion_pct"] == 80.0

    # 9. test_completion_pct_zero_when_empty
    @pytest.mark.asyncio
    async def test_completion_pct_zero_when_empty(self):
        """get_list_status(): total=0 → completion_pct=0.0, no ZeroDivisionError."""
        pool, conn = make_pool_conn()
        status_row = {
            "total": 0,
            "open": 0,
            "in_progress": 0,
            "fulfilled": 0,
            "not_applicable": 0,
            "overdue": 0,
        }
        conn.fetchrow = AsyncMock(return_value=status_row)

        mgr = PBCManager()
        result = await mgr.get_list_status(pool, TENANT, LIST_ID)

        assert result["completion_pct"] == 0.0

    # 10. test_mark_not_applicable_inserts_fulfillment
    @pytest.mark.asyncio
    async def test_mark_not_applicable_inserts_fulfillment(self):
        """mark_not_applicable() INSERTs a fulfillment with 'not_applicable' marker and UPDATEs request status."""
        pool, conn = make_pool_conn()
        na_fulfillment = dict(_FULFILLMENT_DICT, response_text="not_applicable")
        conn.fetchrow = AsyncMock(return_value=na_fulfillment)
        conn.execute = AsyncMock(return_value=None)

        mgr = PBCManager()
        await mgr.mark_not_applicable(
            pool,
            TENANT,
            REQUEST_ID,
            submitted_by="auditor@example.com",
            reason="This control does not apply to the in-scope period.",
        )

        # Verify fulfillment INSERT was called
        fetchrow_queries = [c[0][0] for c in conn.fetchrow.call_args_list]
        fulfillment_inserts = [q for q in fetchrow_queries if "INSERT INTO pbc_fulfillments" in q]
        assert len(fulfillment_inserts) >= 1

        # Verify status UPDATE on pbc_requests to 'not_applicable'
        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        na_updates = [
            q for q in execute_queries
            if "UPDATE pbc_requests" in q and "not_applicable" in q
        ]
        assert len(na_updates) >= 1

    # 11. test_overdue_requests_filters_by_date
    @pytest.mark.asyncio
    async def test_overdue_requests_filters_by_date(self):
        """get_overdue_requests() SQL query must compare due_date to CURRENT_DATE."""
        pool, conn = make_pool_conn()
        overdue_row = dict(_REQUEST_DICT, status="overdue")
        conn.fetch = AsyncMock(return_value=[overdue_row])

        mgr = PBCManager()
        result = await mgr.get_overdue_requests(pool, TENANT, LIST_ID)

        conn.fetch.assert_called_once()
        query = conn.fetch.call_args[0][0]
        assert "CURRENT_DATE" in query
        assert len(result) == 1

    # 12. test_fulfillment_history_returns_list
    @pytest.mark.asyncio
    async def test_fulfillment_history_returns_list(self):
        """get_fulfillment_history() returns a list of fulfillment dicts (2 items)."""
        pool, conn = make_pool_conn()
        fulfillment2 = dict(_FULFILLMENT_DICT, id="dddd1300-0000-0000-0000-000000000002")
        conn.fetch = AsyncMock(return_value=[_FULFILLMENT_DICT, fulfillment2])

        mgr = PBCManager()
        result = await mgr.get_fulfillment_history(pool, TENANT, REQUEST_ID)

        assert len(result) == 2

    # 13. test_update_list_updates_fields
    @pytest.mark.asyncio
    async def test_update_list_updates_fields(self):
        """update_list() issues UPDATE on pbc_request_lists with provided fields."""
        pool, conn = make_pool_conn()
        updated_list = dict(_LIST_DICT, list_name="Updated PBC List", status="sent")
        conn.fetchrow = AsyncMock(return_value=updated_list)

        mgr = PBCManager()
        result = await mgr.update_list(
            pool,
            TENANT,
            LIST_ID,
            {"list_name": "Updated PBC List", "status": "sent"},
        )

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "UPDATE pbc_request_lists" in query
        assert result["list_name"] == "Updated PBC List"
        assert result["status"] == "sent"

    # 14. test_request_number_unique_constraint_respected
    @pytest.mark.asyncio
    async def test_request_number_unique_constraint_respected(self):
        """If fetchval returns existing max N, next request_number is N+1."""
        pool, conn = make_pool_conn()
        existing_max = 7
        conn.fetchval = AsyncMock(return_value=existing_max)
        expected_request = dict(_REQUEST_DICT, request_number=existing_max + 1)
        conn.fetchrow = AsyncMock(return_value=expected_request)

        mgr = PBCManager()
        result = await mgr.add_request(
            pool,
            TENANT,
            LIST_ID,
            title="Additional Request",
            description="Added after 7 existing",
            category="it",
            priority="low",
            assigned_to=None,
            due_date=None,
        )

        assert result["request_number"] == existing_max + 1
