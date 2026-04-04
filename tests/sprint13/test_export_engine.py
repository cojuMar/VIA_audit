"""Sprint 13 — ExportEngine unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/pbc-service"),
)

import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.export_engine import ExportEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000013"
ENGAGEMENT_ID = "aaaa1303-0000-0000-0000-000000000001"
LIST_ID = "bbbb1303-0000-0000-0000-000000000001"
ISSUE_ID = "cccc1303-0000-0000-0000-000000000001"
WORKPAPER_ID = "dddd1303-0000-0000-0000-000000000001"


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


_LIST_DICT = {
    "id": LIST_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "list_name": "Q1 2026 PBC List",
    "description": "Initial PBC list",
    "due_date": date.today() + timedelta(days=30),
    "status": "in_progress",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-10T00:00:00Z",
}

_FULFILLMENT_1 = {
    "id": "f1110000-0000-0000-0000-000000000001",
    "tenant_id": TENANT,
    "request_id": "rrrr1303-0000-0000-0000-000000000001",
    "submitted_by": "controller@example.com",
    "response_text": "GL attached.",
    "minio_key": None,
    "file_name": None,
    "file_size_bytes": None,
    "submission_notes": None,
    "submitted_at": "2026-01-10T00:00:00Z",
}


def _make_request(req_id, req_num, status="open", fulfillments=None):
    return {
        "id": req_id,
        "tenant_id": TENANT,
        "list_id": LIST_ID,
        "request_number": req_num,
        "title": f"Request {req_num}",
        "description": f"Description for request {req_num}",
        "category": "financial",
        "priority": "medium",
        "assigned_to": "controller@example.com",
        "due_date": date.today() + timedelta(days=14),
        "status": status,
        "framework_control_ref": None,
        "fulfillments": fulfillments if fulfillments is not None else [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


_REQUESTS_5 = [
    _make_request(f"rrrr1303-0000-0000-0000-00000000000{i}", i,
                  status="fulfilled" if i <= 3 else "open")
    for i in range(1, 6)
]

_ISSUE_DICT = {
    "id": ISSUE_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "issue_number": 1,
    "title": "Inadequate Access Review Process",
    "description": "Quarterly access reviews not consistently performed.",
    "finding_type": "deficiency",
    "severity": "high",
    "status": "open",
    "control_reference": "AC-2",
    "framework_references": ["SOC2"],
    "root_cause": None,
    "management_owner": "CISO",
    "target_remediation_date": date.today() + timedelta(days=90),
    "actual_remediation_date": None,
    "responses": [],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_WORKPAPER_DICT = {
    "id": WORKPAPER_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "template_id": None,
    "title": "Risk Assessment — Q1 2026",
    "wp_reference": "WP-001",
    "workpaper_type": "risk_assessment",
    "preparer": "auditor@example.com",
    "reviewer": None,
    "status": "draft",
    "review_notes": None,
    "finalized_at": None,
    "sections": [
        {"id": "s1", "section_key": "objective", "title": "Objective", "content": {}, "is_complete": True},
    ],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_ENGAGEMENT_DICT = {
    "id": ENGAGEMENT_ID,
    "tenant_id": TENANT,
    "engagement_name": "Q1 2026 Internal Audit",
    "engagement_type": "internal_audit",
    "fiscal_year": 2026,
    "period_start": date(2026, 1, 1),
    "period_end": date(2026, 3, 31),
    "lead_auditor": "lead@example.com",
    "status": "fieldwork",
    "description": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

_METRICS_DICT = {
    "total": 2,
    "by_severity": {"critical": 0, "high": 1, "medium": 1, "low": 0, "informational": 0},
    "by_status": {"open": 2, "in_remediation": 0, "resolved": 0, "closed": 0, "risk_accepted": 0},
    "open_count": 2,
    "avg_days_open": 10.0,
    "past_target_date": 0,
}


# ---------------------------------------------------------------------------
# TestExportEngine
# ---------------------------------------------------------------------------


class TestExportEngine:

    # 1. test_export_pbc_list_structure
    @pytest.mark.asyncio
    async def test_export_pbc_list_structure(self):
        """export_pbc_list() returns dict with list, summary, requests, exported_at keys."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_LIST_DICT)
        conn.fetch = AsyncMock(return_value=_REQUESTS_5)

        engine = ExportEngine()
        result = await engine.export_pbc_list(pool, TENANT, LIST_ID)

        assert "list" in result
        assert "summary" in result
        assert "requests" in result
        assert "exported_at" in result

    # 2. test_export_pbc_includes_fulfillments
    @pytest.mark.asyncio
    async def test_export_pbc_includes_fulfillments(self):
        """export_pbc_list() requests include a 'fulfillments' list on each request."""
        pool, conn = make_pool_conn()
        requests_with_fulfillments = [
            dict(_make_request("rrrr1303-0000-0000-0000-000000000001", 1, "fulfilled"),
                 fulfillments=[_FULFILLMENT_1]),
        ]
        conn.fetchrow = AsyncMock(return_value=_LIST_DICT)
        conn.fetch = AsyncMock(return_value=requests_with_fulfillments)

        engine = ExportEngine()
        result = await engine.export_pbc_list(pool, TENANT, LIST_ID)

        requests = result["requests"]
        assert len(requests) >= 1
        assert "fulfillments" in requests[0]

    # 3. test_export_issue_register_structure
    @pytest.mark.asyncio
    async def test_export_issue_register_structure(self):
        """export_issue_register() returns dict with engagement, metrics, issues, exported_at keys."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(side_effect=[_ENGAGEMENT_DICT, _METRICS_DICT])
        conn.fetch = AsyncMock(return_value=[_ISSUE_DICT])

        engine = ExportEngine()
        result = await engine.export_issue_register(pool, TENANT, ENGAGEMENT_ID)

        assert "engagement" in result
        assert "metrics" in result
        assert "issues" in result
        assert "exported_at" in result

    # 4. test_export_issues_includes_responses
    @pytest.mark.asyncio
    async def test_export_issues_includes_responses(self):
        """export_issue_register() each issue has a 'responses' list."""
        pool, conn = make_pool_conn()
        issue_with_responses = dict(_ISSUE_DICT, responses=[
            {
                "id": "resp-0000-0000-0000-000000000001",
                "response_type": "management_response",
                "response_text": "We will remediate by Q2.",
                "submitted_by": "ciso@example.com",
                "new_status": None,
                "responded_at": "2026-01-15T00:00:00Z",
            }
        ])
        conn.fetchrow = AsyncMock(side_effect=[_ENGAGEMENT_DICT, _METRICS_DICT])
        conn.fetch = AsyncMock(return_value=[issue_with_responses])

        engine = ExportEngine()
        result = await engine.export_issue_register(pool, TENANT, ENGAGEMENT_ID)

        issues = result["issues"]
        assert len(issues) >= 1
        assert "responses" in issues[0]

    # 5. test_export_workpaper_structure
    @pytest.mark.asyncio
    async def test_export_workpaper_structure(self):
        """export_workpaper() returns dict with 'workpaper' and 'sections' keys."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_WORKPAPER_DICT)
        conn.fetch = AsyncMock(return_value=_WORKPAPER_DICT["sections"])

        engine = ExportEngine()
        result = await engine.export_workpaper(pool, TENANT, WORKPAPER_ID)

        assert "workpaper" in result
        assert "sections" in result

    # 6. test_ai_summary_no_api_key_returns_fallback
    @pytest.mark.asyncio
    async def test_ai_summary_no_api_key_returns_fallback(self):
        """generate_ai_summary() with api_key='' returns a non-empty template-based string."""
        engine = ExportEngine()
        result = await engine.generate_ai_summary(
            context={"engagement_name": "Q1 2026 Audit", "total_issues": 3},
            summary_type="pbc",
            api_key="",
        )

        assert isinstance(result, str)
        assert len(result) > 0

    # 7. test_ai_summary_with_api_key_calls_claude
    @pytest.mark.asyncio
    async def test_ai_summary_with_api_key_calls_claude(self):
        """generate_ai_summary() with a real api_key calls anthropic client messages.create."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="AI-generated summary of the PBC list.")]

        mock_messages = MagicMock()
        mock_messages.create = MagicMock(return_value=mock_message)

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        with patch("src.export_engine.anthropic.Anthropic", return_value=mock_client):
            engine = ExportEngine()
            result = await engine.generate_ai_summary(
                context={"engagement_name": "Q1 2026 Audit", "total_issues": 3},
                summary_type="pbc",
                api_key="sk-ant-test-key-00000000",
            )

        mock_messages.create.assert_called_once()
        assert isinstance(result, str)
        assert len(result) > 0

    # 8. test_export_pbc_completion_pct_computed
    @pytest.mark.asyncio
    async def test_export_pbc_completion_pct_computed(self):
        """export_pbc_list() summary.completion_pct = 60.0 when 3 of 5 requests are fulfilled."""
        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_LIST_DICT)
        # 3 fulfilled, 2 open — 5 total
        requests = [
            _make_request(f"rrrr1303-0000-0000-0000-00000000000{i}", i,
                          status="fulfilled" if i <= 3 else "open")
            for i in range(1, 6)
        ]
        conn.fetch = AsyncMock(return_value=requests)

        engine = ExportEngine()
        result = await engine.export_pbc_list(pool, TENANT, LIST_ID)

        assert result["summary"]["completion_pct"] == 60.0
