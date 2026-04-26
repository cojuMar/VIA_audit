"""Sprint 19 — FieldAuditManager unit tests (14 tests)."""
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

class TestFieldAuditManager:

    # 1 — create_audit INSERTs into field_audits
    @pytest.mark.asyncio
    async def test_create_audit_inserts_row(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import FieldAuditCreate

        row = {
            "id": "audit-1",
            "template_id": "tmpl-1",
            "auditor_email": "auditor@example.com",
            "status": "in_progress",
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.create_audit(
                TENANT,
                FieldAuditCreate(
                    template_id="tmpl-1",
                    auditor_email="auditor@example.com",
                    location_name="HQ Building A",
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "INSERT" in sql.upper()
        assert "field_audits" in sql
        assert result["id"] == "audit-1"

    # 2 — create_audit hardcodes 'in_progress' in INSERT SQL
    @pytest.mark.asyncio
    async def test_create_audit_default_status_in_progress(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import FieldAuditCreate

        row = {"id": "audit-2", "status": "in_progress"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.create_audit(
                TENANT,
                FieldAuditCreate(
                    template_id="tmpl-1",
                    auditor_email="auditor@example.com",
                    location_name="Branch Office",
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "in_progress" in sql

    # 3 — create_audit with assignment_id triggers a second conn.execute for assignment UPDATE
    @pytest.mark.asyncio
    async def test_create_audit_updates_assignment_status(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import FieldAuditCreate

        row = {"id": "audit-3", "assignment_id": "asn-1", "status": "in_progress"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.create_audit(
                TENANT,
                FieldAuditCreate(
                    template_id="tmpl-1",
                    auditor_email="auditor@example.com",
                    location_name="Site B",
                    assignment_id="asn-1",
                ),
            )

        assert conn.execute.called
        execute_sql = conn.execute.call_args[0][0]
        assert "UPDATE" in execute_sql.upper()
        assert "field_audit_assignments" in execute_sql

    # 4 — submit_audit sets status='submitted' and submitted_at in UPDATE
    @pytest.mark.asyncio
    async def test_submit_audit_sets_status_submitted(self):
        from src.field_audit_manager import FieldAuditManager

        response_rows = []  # no yes_no responses → overall_score=None, risk_level='low'
        submitted_row = {
            "id": "audit-4",
            "status": "submitted",
            "submitted_at": "2026-04-04T12:00:00",
            "overall_score": None,
            "risk_level": "low",
        }
        pool, conn = make_pool_conn(fetchrow_val=submitted_row, fetch_val=response_rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.submit_audit(TENANT, "audit-4")

        sql = conn.fetchrow.call_args[0][0]
        assert "UPDATE" in sql.upper()
        assert "submitted" in sql
        assert "submitted_at" in sql
        assert result["status"] == "submitted"

    # 5 — submit_audit stores auditor_signature in the UPDATE call
    @pytest.mark.asyncio
    async def test_submit_audit_stores_signature(self):
        from src.field_audit_manager import FieldAuditManager

        response_rows = []
        submitted_row = {
            "id": "audit-5",
            "status": "submitted",
            "auditor_signature": "data:image/png;base64,abc123",
        }
        pool, conn = make_pool_conn(fetchrow_val=submitted_row, fetch_val=response_rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.submit_audit(
                TENANT, "audit-5", auditor_signature="data:image/png;base64,abc123"
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "auditor_signature" in sql
        # Signature value should appear in positional args
        call_args = conn.fetchrow.call_args[0]
        assert "data:image/png;base64,abc123" in call_args

    # 6 — submit_audit computes risk_level='critical' when score < 50
    @pytest.mark.asyncio
    async def test_submit_audit_computes_risk_level_critical(self):
        from src.field_audit_manager import FieldAuditManager

        # 1 yes_no question with weight=1, boolean_response=False → score=0 → critical
        response_rows = [
            {"boolean_response": False, "is_finding": False, "weight": 1.0, "question_type": "yes_no"},
        ]
        submitted_row = {
            "id": "audit-6",
            "status": "submitted",
            "overall_score": 0.0,
            "risk_level": "critical",
        }
        pool, conn = make_pool_conn(fetchrow_val=submitted_row, fetch_val=response_rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.submit_audit(TENANT, "audit-6")

        # Verify the risk_level arg passed to fetchrow is 'critical'
        call_args = conn.fetchrow.call_args[0]
        assert "critical" in call_args

    # 7 — submit_audit computes risk_level='low' when score >= 85
    @pytest.mark.asyncio
    async def test_submit_audit_computes_risk_level_low(self):
        from src.field_audit_manager import FieldAuditManager

        # 20 yes_no questions all True, weight=1 → score=100 → low
        response_rows = [
            {"boolean_response": True, "is_finding": False, "weight": 1.0, "question_type": "yes_no"}
            for _ in range(20)
        ]
        submitted_row = {
            "id": "audit-7",
            "status": "submitted",
            "overall_score": 100.0,
            "risk_level": "low",
        }
        pool, conn = make_pool_conn(fetchrow_val=submitted_row, fetch_val=response_rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.submit_audit(TENANT, "audit-7")

        call_args = conn.fetchrow.call_args[0]
        assert "low" in call_args

    # 8 — get_audit returns None when fetchrow returns None
    @pytest.mark.asyncio
    async def test_get_audit_returns_none_when_not_found(self):
        from src.field_audit_manager import FieldAuditManager

        pool, conn = make_pool_conn(fetchrow_val=None)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.get_audit(TENANT, "nonexistent-id")

        assert result is None

    # 9 — list_audits with email filter includes auditor_email in SQL
    @pytest.mark.asyncio
    async def test_list_audits_filter_by_email(self):
        from src.field_audit_manager import FieldAuditManager

        rows = [{"id": "audit-9", "auditor_email": "field@example.com", "status": "in_progress"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.list_audits(TENANT, email="field@example.com")

        sql = conn.fetch.call_args[0][0]
        assert "auditor_email" in sql

    # 10 — list_audits with status filter includes status in SQL
    @pytest.mark.asyncio
    async def test_list_audits_filter_by_status(self):
        from src.field_audit_manager import FieldAuditManager

        rows = [{"id": "audit-10", "auditor_email": "field@example.com", "status": "submitted"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.list_audits(TENANT, status="submitted")

        sql = conn.fetch.call_args[0][0]
        assert "status" in sql
        call_args = conn.fetch.call_args[0]
        assert "submitted" in call_args

    # 11 — add_response INSERTs into field_audit_responses, no UPDATE
    @pytest.mark.asyncio
    async def test_add_response_inserts_immutable(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import ResponsePayload

        row = {"id": "resp-1", "field_audit_id": "audit-1", "question_id": "q-1", "sync_id": "sync-uuid-001"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.add_response(
                TENANT,
                "audit-1",
                ResponsePayload(question_id="q-1", sync_id="sync-uuid-001"),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "INSERT" in sql.upper()
        assert "field_audit_responses" in sql
        # Must not use UPDATE anywhere in the insert statement
        assert "UPDATE" not in sql.upper()

    # 12 — add_response SQL uses sync_id for deduplication (WHERE NOT EXISTS)
    @pytest.mark.asyncio
    async def test_add_response_dedup_by_sync_id(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import ResponsePayload

        row = {"id": "resp-2", "sync_id": "sync-uuid-002"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            await mgr.add_response(
                TENANT,
                "audit-1",
                ResponsePayload(question_id="q-2", sync_id="sync-uuid-002"),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "sync_id" in sql

    # 13 — add_responses_batch returns dict with 'inserted' and 'skipped' counts
    @pytest.mark.asyncio
    async def test_add_responses_batch_returns_counts(self):
        from src.field_audit_manager import FieldAuditManager
        from src.models import ResponsePayload

        # First call returns a row (inserted), second returns None (skipped)
        inserted_row = {"id": "resp-3"}
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[inserted_row, None])
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

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.add_responses_batch(
                TENANT,
                "audit-1",
                [
                    ResponsePayload(question_id="q-1", sync_id="sync-uuid-new"),
                    ResponsePayload(question_id="q-2", sync_id="sync-uuid-dup"),
                ],
            )

        assert "inserted" in result
        assert "skipped" in result
        assert result["inserted"] == 1
        assert result["skipped"] == 1

    # 14 — get_audit_summary returns all required top-level keys
    @pytest.mark.asyncio
    async def test_get_audit_summary_returns_required_keys(self):
        from src.field_audit_manager import FieldAuditManager

        audit_row = {
            "id": "audit-14",
            "status": "submitted",
            "overall_score": 88.0,
            "risk_level": "low",
            "total_findings": 1,
        }
        severity_rows = [
            {"finding_severity": "high", "cnt": 1},
        ]
        section_rows = [
            {"section_name": "Fire Safety", "total_yn": 4, "compliant_yn": 4, "finding_count": 0},
        ]
        photo_rows = [
            {"id": "photo-1", "minio_object_key": "tenant/audit-14/photo-1.jpg", "caption": None, "taken_at": None},
        ]

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=audit_row)
        conn.fetchval = AsyncMock(side_effect=[10, 1])  # response_count=10, finding_count=1
        conn.fetch = AsyncMock(side_effect=[severity_rows, section_rows, photo_rows])
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

        with patch("src.field_audit_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = FieldAuditManager(pool)
            result = await mgr.get_audit_summary(TENANT, "audit-14")

        assert "audit" in result
        assert "response_count" in result
        assert "finding_count" in result
        assert "findings_by_severity" in result
        assert "section_scores" in result
        assert "photos" in result
        assert isinstance(result["findings_by_severity"], dict)
        assert isinstance(result["section_scores"], list)
        assert isinstance(result["photos"], list)
