"""Sprint 19 — TemplateManager unit tests (10 tests)."""
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

class TestTemplateManager:

    # 1 — get_template_types returns list without tenant context
    @pytest.mark.asyncio
    async def test_get_template_types_no_tenant(self):
        from src.template_manager import TemplateManager

        rows = [
            {"id": "tt-1", "type_key": "safety_inspection", "display_name": "Safety Inspection"},
            {"id": "tt-2", "type_key": "it_asset_audit",    "display_name": "IT Asset Audit"},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        mgr = TemplateManager(pool)
        result = await mgr.get_template_types()

        assert conn.fetch.called
        assert isinstance(result, list)
        assert len(result) == 2
        # No tenant_conn patch needed — this method uses pool.acquire directly
        sql = conn.fetch.call_args[0][0]
        assert "field_audit_template_types" in sql

    # 2 — get_templates with active_only=True includes 'is_active' in SQL
    @pytest.mark.asyncio
    async def test_get_templates_active_only(self):
        from src.template_manager import TemplateManager

        rows = [
            {"id": "tmpl-1", "display_name": "Safety Walkthrough", "is_active": True},
        ]
        pool, conn = make_pool_conn(fetch_val=rows)

        mgr = TemplateManager(pool)
        await mgr.get_templates(active_only=True)

        sql = conn.fetch.call_args[0][0]
        assert "is_active" in sql

    # 3 — get_templates with type_id filter passes it through to SQL
    @pytest.mark.asyncio
    async def test_get_templates_filter_by_type(self):
        from src.template_manager import TemplateManager

        rows = [{"id": "tmpl-2", "display_name": "IT Asset Inventory", "template_type_id": "tt-2"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        mgr = TemplateManager(pool)
        await mgr.get_templates(type_id="tt-2", active_only=False)

        sql = conn.fetch.call_args[0][0]
        assert "template_type_id" in sql
        # The type_id value should be in the positional args
        call_args = conn.fetch.call_args[0]
        assert "tt-2" in call_args

    # 4 — get_template_with_questions groups questions into sections dict
    @pytest.mark.asyncio
    async def test_get_template_with_questions_groups_by_section(self):
        from src.template_manager import TemplateManager

        template_row = {"id": "tmpl-1", "display_name": "Safety Walkthrough", "template_type_name": "Safety Inspection"}
        question_rows = [
            {"id": "q-1", "section_name": "Fire Safety",      "sequence_number": 1, "question_text": "Are fire exits clear?"},
            {"id": "q-2", "section_name": "Fire Safety",      "sequence_number": 2, "question_text": "Extinguishers in date?"},
            {"id": "q-3", "section_name": "Electrical Safety","sequence_number": 1, "question_text": "Panels labeled?"},
        ]
        pool, conn = make_pool_conn(fetchrow_val=template_row, fetch_val=question_rows)

        mgr = TemplateManager(pool)
        result = await mgr.get_template_with_questions("tmpl-1")

        assert result is not None
        assert "sections" in result
        section_names = [s["name"] for s in result["sections"]]
        assert "Fire Safety" in section_names
        assert "Electrical Safety" in section_names
        fire_section = next(s for s in result["sections"] if s["name"] == "Fire Safety")
        assert len(fire_section["questions"]) == 2

    # 5 — get_template_with_questions returns None when fetchrow returns None
    @pytest.mark.asyncio
    async def test_get_template_returns_none_when_not_found(self):
        from src.template_manager import TemplateManager

        pool, conn = make_pool_conn(fetchrow_val=None)

        mgr = TemplateManager(pool)
        result = await mgr.get_template_with_questions("nonexistent-id")

        assert result is None

    # 6 — get_assignments with email filter includes email in SQL
    @pytest.mark.asyncio
    async def test_get_assignments_filter_by_email(self):
        from src.template_manager import TemplateManager

        rows = [{"id": "asn-1", "assigned_to_email": "auditor@example.com", "status": "assigned"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.template_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = TemplateManager(pool)
            await mgr.get_assignments(TENANT, email="auditor@example.com")

        sql = conn.fetch.call_args[0][0]
        assert "assigned_to_email" in sql

    # 7 — get_assignments with status filter includes status in SQL
    @pytest.mark.asyncio
    async def test_get_assignments_filter_by_status(self):
        from src.template_manager import TemplateManager

        rows = [{"id": "asn-2", "assigned_to_email": "auditor@example.com", "status": "assigned"}]
        pool, conn = make_pool_conn(fetch_val=rows)

        with patch("src.template_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = TemplateManager(pool)
            await mgr.get_assignments(TENANT, status="assigned")

        sql = conn.fetch.call_args[0][0]
        assert "status" in sql
        call_args = conn.fetch.call_args[0]
        assert "assigned" in call_args

    # 8 — create_assignment INSERTs into field_audit_assignments
    @pytest.mark.asyncio
    async def test_create_assignment_inserts_row(self):
        from src.template_manager import TemplateManager
        from src.models import AssignmentCreate

        row = {
            "id": "asn-3",
            "template_id": "tmpl-1",
            "assigned_to_email": "auditor@example.com",
            "status": "pending",
        }
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.template_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = TemplateManager(pool)
            result = await mgr.create_assignment(
                TENANT,
                AssignmentCreate(
                    template_id="tmpl-1",
                    assigned_to_email="auditor@example.com",
                    location_name="HQ Building A",
                    scheduled_date="2026-05-01",
                    due_date="2026-05-15",
                ),
            )

        sql = conn.fetchrow.call_args[0][0]
        assert "INSERT" in sql.upper()
        assert "field_audit_assignments" in sql
        assert result["id"] == "asn-3"

    # 9 — AssignmentCreate default priority is 'medium'
    @pytest.mark.asyncio
    async def test_create_assignment_default_priority_medium(self):
        from src.models import AssignmentCreate

        assignment = AssignmentCreate(
            template_id="tmpl-1",
            assigned_to_email="auditor@example.com",
            location_name="Branch Office",
            scheduled_date="2026-06-01",
            due_date="2026-06-30",
        )
        assert assignment.priority == "medium"

    # 10 — update_assignment_status executes UPDATE status in SQL
    @pytest.mark.asyncio
    async def test_update_assignment_status_updates_field(self):
        from src.template_manager import TemplateManager

        row = {"id": "asn-4", "status": "in_progress", "updated_at": "2026-04-04T10:00:00"}
        pool, conn = make_pool_conn(fetchrow_val=row)

        with patch("src.template_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = TemplateManager(pool)
            result = await mgr.update_assignment_status(TENANT, "asn-4", "in_progress")

        sql = conn.fetchrow.call_args[0][0]
        assert "UPDATE" in sql.upper()
        assert "status" in sql
        assert result["status"] == "in_progress"
