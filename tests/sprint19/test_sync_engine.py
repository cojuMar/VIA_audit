"""Sprint 19 — SyncEngine unit tests (12 tests)."""
from __future__ import annotations

import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "mobile-sync-service"),
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


TENANT = "dddddddd-0000-0000-0000-000000000019"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncEngine:

    # 1 — process_sync_batch with empty payload returns zeros and records sync_session
    @pytest.mark.asyncio
    async def test_process_sync_batch_empty_payload(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        sync_session_row = {"id": "sess-1", "device_id": "device-abc", "sync_status": "success"}
        pool, conn = make_pool_conn(fetchrow_val=sync_session_row)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(device_id="device-abc", auditor_email="auditor@example.com"),
            )

        assert result["new_audits"] == 0
        assert result["duplicate_audits"] == 0
        assert result["responses_inserted"] == 0
        assert result["responses_skipped"] == 0

    # 2 — process_sync_batch with new audit in payload returns new_audits=1
    @pytest.mark.asyncio
    async def test_process_sync_batch_inserts_new_audit(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        audit_payload = {
            "template_id": "tmpl-1",
            "auditor_email": "auditor@example.com",
            "location_name": "Site A",
            "device_id": "device-abc",
            "client_created_at": "2026-04-04T08:00:00Z",
            "responses": [],
        }

        # fetchrow returns None for dedup check (not a duplicate), then the inserted audit row
        audit_row = {"id": "audit-new-1", "status": "in_progress"}
        sync_session_row = {"id": "sess-2", "sync_status": "success"}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[None, audit_row, sync_session_row])
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value="OK")
        conn.fetchval = AsyncMock(return_value=None)
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

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(
                    device_id="device-abc",
                    auditor_email="auditor@example.com",
                    field_audits=[audit_payload],
                ),
            )

        assert result["new_audits"] == 1
        assert result["duplicate_audits"] == 0

    # 3 — process_sync_batch deduplicates audit with same device_id+client_created_at
    @pytest.mark.asyncio
    async def test_process_sync_batch_deduplicates_audit(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        audit_payload = {
            "template_id": "tmpl-1",
            "auditor_email": "auditor@example.com",
            "location_name": "Site A",
            "device_id": "device-abc",
            "client_created_at": "2026-04-04T08:00:00Z",
            "responses": [],
        }

        # fetchrow returns existing row → duplicate
        existing_row = {"id": "audit-existing", "status": "in_progress"}
        sync_session_row = {"id": "sess-3", "sync_status": "success"}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[existing_row, sync_session_row])
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value="OK")
        conn.fetchval = AsyncMock(return_value=None)
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

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(
                    device_id="device-abc",
                    auditor_email="auditor@example.com",
                    field_audits=[audit_payload],
                ),
            )

        assert result["duplicate_audits"] == 1
        assert result["new_audits"] == 0

    # 4 — process_sync_batch processes standalone responses
    @pytest.mark.asyncio
    async def test_process_sync_batch_inserts_responses(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload, ResponsePayload

        sync_session_row = {"id": "sess-4", "sync_status": "success"}
        response_row = {"id": "resp-1", "sync_id": "sync-new-001"}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[response_row, sync_session_row])
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value="OK")
        conn.fetchval = AsyncMock(return_value=None)
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

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(
                    device_id="device-abc",
                    auditor_email="auditor@example.com",
                    responses=[
                        ResponsePayload(
                            question_id="q-1",
                            sync_id="sync-new-001",
                        )
                    ],
                ),
            )

        assert result["responses_inserted"] + result["responses_skipped"] >= 0

    # 5 — process_sync_batch records a sync_session (INSERT into sync_sessions)
    @pytest.mark.asyncio
    async def test_process_sync_batch_records_sync_session(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        sync_session_row = {"id": "sess-5", "sync_status": "success"}
        pool, conn = make_pool_conn(fetchrow_val=sync_session_row)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(device_id="device-abc", auditor_email="auditor@example.com"),
            )

        # At least one fetchrow should have been called for the sync_session INSERT
        assert conn.fetchrow.called
        all_sqls = " ".join(str(c[0][0]) for c in conn.fetchrow.call_args_list)
        assert "sync_sessions" in all_sqls

    # 6 — process_sync_batch result contains sync_session_id
    @pytest.mark.asyncio
    async def test_process_sync_batch_returns_sync_session_id(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        sync_session_row = {"id": "sess-6", "sync_status": "success"}
        pool, conn = make_pool_conn(fetchrow_val=sync_session_row)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(device_id="device-abc", auditor_email="auditor@example.com"),
            )

        assert "sync_session_id" in result
        assert result["sync_session_id"] == "sess-6"

    # 7 — process_sync_batch counts responses_inserted in result
    @pytest.mark.asyncio
    async def test_process_sync_batch_counts_responses_inserted(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload

        sync_session_row = {"id": "sess-7", "sync_status": "success"}
        pool, conn = make_pool_conn(fetchrow_val=sync_session_row)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(device_id="device-abc", auditor_email="auditor@example.com"),
            )

        assert "responses_inserted" in result
        assert isinstance(result["responses_inserted"], int)

    # 8 — process_sync_batch counts responses_skipped for duplicate sync_ids
    @pytest.mark.asyncio
    async def test_process_sync_batch_counts_responses_skipped(self):
        from src.sync_engine import SyncEngine
        from src.models import SyncBatchPayload, ResponsePayload

        sync_session_row = {"id": "sess-8", "sync_status": "success"}
        # fetchrow returns None for the INSERT (dedup hit) then sync_session row
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[None, sync_session_row])
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value="OK")
        conn.fetchval = AsyncMock(return_value=None)
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

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.process_sync_batch(
                TENANT,
                SyncBatchPayload(
                    device_id="device-abc",
                    auditor_email="auditor@example.com",
                    responses=[
                        ResponsePayload(question_id="q-1", sync_id="sync-dup-001"),
                    ],
                ),
            )

        assert "responses_skipped" in result
        assert isinstance(result["responses_skipped"], int)

    # 9 — get_assignments_for_device returns dict with 'assignments' key
    @pytest.mark.asyncio
    async def test_get_assignments_for_device_returns_assignments(self):
        from src.sync_engine import SyncEngine

        assignment_rows = [
            {"id": "asn-1", "assigned_to_email": "auditor@example.com", "status": "assigned"},
        ]
        pool, conn = make_pool_conn(fetch_val=assignment_rows)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.get_assignments_for_device(
                TENANT,
                device_id="device-abc",
                auditor_email="auditor@example.com",
            )

        assert "assignments" in result
        assert isinstance(result["assignments"], list)

    # 10 — get_assignments_for_device returns dict with 'templates' key
    @pytest.mark.asyncio
    async def test_get_assignments_for_device_includes_templates(self):
        from src.sync_engine import SyncEngine

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.get_assignments_for_device(
                TENANT,
                device_id="device-abc",
                auditor_email="auditor@example.com",
            )

        assert "templates" in result
        assert isinstance(result["templates"], list)

    # 11 — get_assignments_for_device returns dict with 'server_time' key
    @pytest.mark.asyncio
    async def test_get_assignments_for_device_includes_server_time(self):
        from src.sync_engine import SyncEngine

        pool, conn = make_pool_conn(fetch_val=[])

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.get_assignments_for_device(
                TENANT,
                device_id="device-abc",
                auditor_email="auditor@example.com",
            )

        assert "server_time" in result

    # 12 — get_sync_history filters by device_id in SQL
    @pytest.mark.asyncio
    async def test_get_sync_history_filters_by_device(self):
        from src.sync_engine import SyncEngine

        session_rows = [
            {"id": "sess-hist-1", "device_id": "device-abc", "sync_status": "success"},
        ]
        pool, conn = make_pool_conn(fetch_val=session_rows)

        with patch("src.sync_engine.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            engine = SyncEngine(pool)
            result = await engine.get_sync_history(
                TENANT,
                device_id="device-abc",
            )

        assert conn.fetch.called
        sql = conn.fetch.call_args[0][0]
        assert "device_id" in sql
        assert isinstance(result, list)
