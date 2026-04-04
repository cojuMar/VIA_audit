"""Sprint 13 — IssueTracker unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/pbc-service"),
)

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.issue_tracker import IssueTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000011"
ENGAGEMENT_ID = "aaaa1301-0000-0000-0000-000000000001"
ISSUE_ID = "bbbb1301-0000-0000-0000-000000000001"
RESPONSE_ID = "cccc1301-0000-0000-0000-000000000001"


def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=tx)
    return mock_pool, mock_conn


_ISSUE_DICT = {
    "id": ISSUE_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "issue_number": 1,
    "title": "Inadequate Access Review Process",
    "description": "Quarterly access reviews are not being performed consistently.",
    "finding_type": "deficiency",
    "severity": "high",
    "status": "open",
    "control_reference": "AC-2",
    "framework_references": ["SOC2", "ISO27001"],
    "root_cause": "Lack of defined ownership for access review process.",
    "management_owner": "CISO",
    "target_remediation_date": date.today() + timedelta(days=90),
    "actual_remediation_date": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_RESPONSE_DICT = {
    "id": RESPONSE_ID,
    "tenant_id": TENANT,
    "issue_id": ISSUE_ID,
    "response_type": "management_response",
    "response_text": "We will implement a quarterly access review process by Q2.",
    "submitted_by": "ciso@example.com",
    "new_status": "in_remediation",
    "minio_key": None,
    "file_name": None,
    "responded_at": "2026-01-15T00:00:00Z",
}


# ---------------------------------------------------------------------------
# TestIssueTracker
# ---------------------------------------------------------------------------


class TestIssueTracker:

    # 1. test_create_issue_auto_increments_number
    @pytest.mark.asyncio
    async def test_create_issue_auto_increments_number(self):
        """create_issue() calls fetchval to get max issue_number; fetchval=2 → issue_number=3."""
        pool, conn = make_pool_conn()
        conn.fetchval = AsyncMock(return_value=2)
        expected_issue = dict(_ISSUE_DICT, issue_number=3)
        conn.fetchrow = AsyncMock(return_value=expected_issue)

        tracker = IssueTracker()
        result = await tracker.create_issue(
            pool,
            TENANT,
            ENGAGEMENT_ID,
            title="Inadequate Access Review Process",
            description="Quarterly access reviews not performed consistently.",
            finding_type="deficiency",
            severity="high",
            control_reference="AC-2",
            management_owner="CISO",
            target_remediation_date=date.today() + timedelta(days=90),
        )

        conn.fetchval.assert_called_once()
        assert result["issue_number"] == 3

    # 2. test_create_issue_starts_at_1
    @pytest.mark.asyncio
    async def test_create_issue_starts_at_1(self):
        """create_issue() starts at issue_number=1 when no existing issues (fetchval=0)."""
        pool, conn = make_pool_conn()
        conn.fetchval = AsyncMock(return_value=0)
        expected_issue = dict(_ISSUE_DICT, issue_number=1)
        conn.fetchrow = AsyncMock(return_value=expected_issue)

        tracker = IssueTracker()
        result = await tracker.create_issue(
            pool,
            TENANT,
            ENGAGEMENT_ID,
            title="First Issue",
            description="The very first issue for this engagement.",
            finding_type="observation",
            severity="medium",
            control_reference=None,
            management_owner=None,
            target_remediation_date=None,
        )

        assert result["issue_number"] == 1

    # 3. test_add_response_inserts_immutable_record
    @pytest.mark.asyncio
    async def test_add_response_inserts_immutable_record(self):
        """add_response() INSERTs into issue_responses; must not UPDATE issue_responses."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_RESPONSE_DICT)
        conn.execute = AsyncMock(return_value=None)

        tracker = IssueTracker()
        await tracker.add_response(
            pool,
            TENANT,
            ISSUE_ID,
            response_type="management_response",
            response_text="We will implement a quarterly access review process by Q2.",
            submitted_by="ciso@example.com",
            new_status=None,
            file_bytes=None,
            file_name=None,
        )

        fetchrow_queries = [c[0][0] for c in conn.fetchrow.call_args_list]
        response_inserts = [q for q in fetchrow_queries if "INSERT INTO issue_responses" in q]
        assert len(response_inserts) >= 1

        # Must not UPDATE issue_responses
        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        bad_updates = [q for q in execute_queries if "UPDATE issue_responses" in q]
        assert len(bad_updates) == 0

    # 4. test_add_response_updates_issue_status
    @pytest.mark.asyncio
    async def test_add_response_updates_issue_status(self):
        """add_response() with new_status set issues UPDATE on audit_issues."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_RESPONSE_DICT)
        conn.execute = AsyncMock(return_value=None)

        tracker = IssueTracker()
        await tracker.add_response(
            pool,
            TENANT,
            ISSUE_ID,
            response_type="status_change",
            response_text="Moving to in_remediation.",
            submitted_by="auditor@example.com",
            new_status="in_remediation",
            file_bytes=None,
            file_name=None,
        )

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        issue_updates = [q for q in execute_queries if "UPDATE audit_issues" in q]
        assert len(issue_updates) >= 1

    # 5. test_add_response_sets_actual_remediation_on_resolved
    @pytest.mark.asyncio
    async def test_add_response_sets_actual_remediation_on_resolved(self):
        """add_response() with new_status='resolved' → actual_remediation_date is set in UPDATE."""
        pool, conn = make_pool_conn()
        resolved_response = dict(_RESPONSE_DICT, new_status="resolved")
        conn.fetchrow = AsyncMock(return_value=resolved_response)
        conn.execute = AsyncMock(return_value=None)

        tracker = IssueTracker()
        await tracker.add_response(
            pool,
            TENANT,
            ISSUE_ID,
            response_type="remediation_update",
            response_text="All access reviews are now complete and documented.",
            submitted_by="ciso@example.com",
            new_status="resolved",
            file_bytes=None,
            file_name=None,
        )

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        remediation_updates = [
            q for q in execute_queries
            if "actual_remediation_date" in q and "UPDATE audit_issues" in q
        ]
        assert len(remediation_updates) >= 1

    # 6. test_add_response_without_status_change
    @pytest.mark.asyncio
    async def test_add_response_without_status_change(self):
        """add_response() with new_status=None must not UPDATE audit_issues."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_RESPONSE_DICT)
        conn.execute = AsyncMock(return_value=None)

        tracker = IssueTracker()
        await tracker.add_response(
            pool,
            TENANT,
            ISSUE_ID,
            response_type="auditor_note",
            response_text="Note: Reviewed management's response. Follow-up scheduled.",
            submitted_by="auditor@example.com",
            new_status=None,
            file_bytes=None,
            file_name=None,
        )

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        issue_updates = [q for q in execute_queries if "UPDATE audit_issues" in q]
        assert len(issue_updates) == 0

    # 7. test_get_issue_register_returns_list
    @pytest.mark.asyncio
    async def test_get_issue_register_returns_list(self):
        """get_issue_register() returns a list of issue dicts."""
        pool, conn = make_pool_conn()
        issue2 = dict(_ISSUE_DICT, id="bbbb1301-0000-0000-0000-000000000002", issue_number=2)
        conn.fetch = AsyncMock(return_value=[_ISSUE_DICT, issue2])

        tracker = IssueTracker()
        result = await tracker.get_issue_register(pool, TENANT, ENGAGEMENT_ID)

        assert isinstance(result, list)
        assert len(result) == 2

    # 8. test_get_issue_includes_responses
    @pytest.mark.asyncio
    async def test_get_issue_includes_responses(self):
        """get_issue() returns a dict that includes a 'responses' key with list."""
        pool, conn = make_pool_conn()
        issue_with_responses = dict(_ISSUE_DICT, responses=[_RESPONSE_DICT])
        conn.fetchrow = AsyncMock(return_value=issue_with_responses)
        conn.fetch = AsyncMock(return_value=[_RESPONSE_DICT])

        tracker = IssueTracker()
        result = await tracker.get_issue(pool, TENANT, ISSUE_ID)

        assert "responses" in result

    # 9. test_get_issue_metrics_structure
    @pytest.mark.asyncio
    async def test_get_issue_metrics_structure(self):
        """get_issue_metrics() returns dict with total, by_severity, by_status, open_count, avg_days_open, past_target_date."""
        pool, conn = make_pool_conn()
        metrics_row = {
            "total": 5,
            "critical": 1,
            "high": 2,
            "medium": 1,
            "low": 1,
            "informational": 0,
            "open": 3,
            "in_remediation": 1,
            "resolved": 1,
            "closed": 0,
            "risk_accepted": 0,
            "management_response_pending": 0,
            "avg_days_open": 14.5,
            "past_target_date": 1,
        }
        conn.fetchrow = AsyncMock(return_value=metrics_row)

        tracker = IssueTracker()
        result = await tracker.get_issue_metrics(pool, TENANT, ENGAGEMENT_ID)

        assert "total" in result
        assert "by_severity" in result
        assert "by_status" in result
        assert "open_count" in result
        assert "avg_days_open" in result
        assert "past_target_date" in result

    # 10. test_metrics_past_target_date_count
    @pytest.mark.asyncio
    async def test_metrics_past_target_date_count(self):
        """get_issue_metrics() correctly surfaces past_target_date=2."""
        pool, conn = make_pool_conn()
        metrics_row = {
            "total": 5,
            "critical": 0,
            "high": 2,
            "medium": 2,
            "low": 1,
            "informational": 0,
            "open": 4,
            "in_remediation": 1,
            "resolved": 0,
            "closed": 0,
            "risk_accepted": 0,
            "management_response_pending": 0,
            "avg_days_open": 30.0,
            "past_target_date": 2,
        }
        conn.fetchrow = AsyncMock(return_value=metrics_row)

        tracker = IssueTracker()
        result = await tracker.get_issue_metrics(pool, TENANT, ENGAGEMENT_ID)

        assert result["past_target_date"] == 2

    # 11. test_get_issues_by_status_filters
    @pytest.mark.asyncio
    async def test_get_issues_by_status_filters(self):
        """get_issues_by_status() SQL query must include the status filter parameter."""
        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=[_ISSUE_DICT])

        tracker = IssueTracker()
        result = await tracker.get_issues_by_status(pool, TENANT, ENGAGEMENT_ID, status="open")

        conn.fetch.assert_called_once()
        query = conn.fetch.call_args[0][0]
        assert "status" in query.lower()
        assert len(result) == 1

    # 12. test_file_upload_on_response_called_when_file_provided
    @pytest.mark.asyncio
    async def test_file_upload_on_response_called_when_file_provided(self):
        """add_response() with file_bytes provided calls minio_client.put_object."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(
            return_value=dict(_RESPONSE_DICT, minio_key="issues/evidence/test.pdf")
        )
        conn.execute = AsyncMock(return_value=None)

        mock_minio = MagicMock()
        mock_minio.put_object = MagicMock()

        tracker = IssueTracker()
        await tracker.add_response(
            pool,
            TENANT,
            ISSUE_ID,
            response_type="evidence_uploaded",
            response_text="Attaching evidence of remediation.",
            submitted_by="ciso@example.com",
            new_status=None,
            file_bytes=b"PDF_CONTENT_BYTES",
            file_name="access_review_evidence.pdf",
            minio_client=mock_minio,
        )

        mock_minio.put_object.assert_called_once()
