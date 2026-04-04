"""Sprint 13 — WorkpaperManager unit tests."""
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/pbc-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.workpaper_manager import WorkpaperManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-0000-0000-000000000012"
ENGAGEMENT_ID = "aaaa1302-0000-0000-0000-000000000001"
TEMPLATE_ID = "eeee1302-0000-0000-0000-000000000001"
WORKPAPER_ID = "ffff1302-0000-0000-0000-000000000001"
SECTION_ID_1 = "1111130200000000000000000000001a"
SECTION_ID_2 = "1111130200000000000000000000002a"
SECTION_ID_3 = "1111130200000000000000000000003a"
SECTION_ID_4 = "1111130200000000000000000000004a"


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


_TEMPLATE_DICT = {
    "id": TEMPLATE_ID,
    "template_key": "risk_assessment_template",
    "title": "Risk Assessment Workpaper",
    "description": "Structured workpaper for conducting and documenting risk assessments.",
    "template_type": "risk_assessment",
    "sections": [
        {"section_key": "objective", "title": "Objective and Scope", "instructions": "...", "fields": []},
        {"section_key": "methodology", "title": "Methodology", "instructions": "...", "fields": []},
        {"section_key": "risk_matrix", "title": "Risk Identification and Rating", "instructions": "...", "fields": []},
    ],
    "framework_references": ["SOC2", "ISO27001", "NIST"],
    "is_active": True,
}

_WORKPAPER_DICT = {
    "id": WORKPAPER_ID,
    "tenant_id": TENANT,
    "engagement_id": ENGAGEMENT_ID,
    "template_id": TEMPLATE_ID,
    "title": "Risk Assessment — Q1 2026",
    "wp_reference": "WP-001",
    "workpaper_type": "risk_assessment",
    "preparer": "auditor@example.com",
    "reviewer": None,
    "status": "draft",
    "review_notes": None,
    "finalized_at": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


def _make_section(section_id, section_key, title, sort_order, is_complete=False):
    return {
        "id": section_id,
        "tenant_id": TENANT,
        "workpaper_id": WORKPAPER_ID,
        "section_key": section_key,
        "title": title,
        "content": {},
        "sort_order": sort_order,
        "is_complete": is_complete,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


_SECTIONS_4 = [
    _make_section(SECTION_ID_1, "objective", "Objective and Scope", 0),
    _make_section(SECTION_ID_2, "methodology", "Methodology", 1),
    _make_section(SECTION_ID_3, "risk_matrix", "Risk Identification", 2),
    _make_section(SECTION_ID_4, "conclusions", "Conclusions", 3),
]

_SECTIONS_4_ALL_COMPLETE = [
    _make_section(SECTION_ID_1, "objective", "Objective and Scope", 0, is_complete=True),
    _make_section(SECTION_ID_2, "methodology", "Methodology", 1, is_complete=True),
    _make_section(SECTION_ID_3, "risk_matrix", "Risk Identification", 2, is_complete=True),
    _make_section(SECTION_ID_4, "conclusions", "Conclusions", 3, is_complete=True),
]


# ---------------------------------------------------------------------------
# TestWorkpaperManager
# ---------------------------------------------------------------------------


class TestWorkpaperManager:

    # 1. test_list_templates_no_tenant
    @pytest.mark.asyncio
    async def test_list_templates_no_tenant(self):
        """list_templates() fetches from workpaper_templates without tenant SET LOCAL (platform table)."""
        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=[_TEMPLATE_DICT])

        mgr = WorkpaperManager()
        result = await mgr.list_templates(pool)

        conn.fetch.assert_called_once()
        query = conn.fetch.call_args[0][0]
        # Should query workpaper_templates directly; no tenant SET LOCAL required
        assert "workpaper_templates" in query
        # Should NOT attempt to set tenant context for this platform-wide table
        execute_calls = [c[0][0] for c in conn.execute.call_args_list]
        tenant_sets = [q for q in execute_calls if "SET LOCAL app.tenant_id" in q]
        assert len(tenant_sets) == 0

    # 2. test_create_from_template_inserts_workpaper
    @pytest.mark.asyncio
    async def test_create_from_template_inserts_workpaper(self):
        """create_workpaper() with template_id inserts workpaper + one section per template section."""
        pool, conn = make_pool_conn()
        # fetchrow: template lookup, then workpaper INSERT
        conn.fetchrow = AsyncMock(side_effect=[_TEMPLATE_DICT, _WORKPAPER_DICT])
        # execute: once per section (3 sections in template)
        conn.execute = AsyncMock(return_value=None)

        mgr = WorkpaperManager()
        result = await mgr.create_workpaper(
            pool,
            TENANT,
            ENGAGEMENT_ID,
            title="Risk Assessment — Q1 2026",
            workpaper_type="risk_assessment",
            template_id=TEMPLATE_ID,
            preparer="auditor@example.com",
            wp_reference="WP-001",
        )

        # Should have called fetchrow at least twice (template + workpaper INSERT)
        assert conn.fetchrow.call_count >= 2

        # Should have called execute for each of the 3 template sections
        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        section_inserts = [q for q in execute_queries if "INSERT INTO workpaper_sections" in q]
        assert len(section_inserts) == 3

    # 3. test_create_blank_no_sections
    @pytest.mark.asyncio
    async def test_create_blank_no_sections(self):
        """create_workpaper() with template_id=None inserts workpaper only; no section INSERTs."""
        pool, conn = make_pool_conn()
        blank_workpaper = dict(_WORKPAPER_DICT, template_id=None)
        conn.fetchrow = AsyncMock(return_value=blank_workpaper)
        conn.execute = AsyncMock(return_value=None)

        mgr = WorkpaperManager()
        result = await mgr.create_workpaper(
            pool,
            TENANT,
            ENGAGEMENT_ID,
            title="Ad-hoc Workpaper",
            workpaper_type="other",
            template_id=None,
            preparer="auditor@example.com",
            wp_reference=None,
        )

        execute_queries = [c[0][0] for c in conn.execute.call_args_list]
        section_inserts = [q for q in execute_queries if "INSERT INTO workpaper_sections" in q]
        assert len(section_inserts) == 0

    # 4. test_get_workpaper_includes_sections
    @pytest.mark.asyncio
    async def test_get_workpaper_includes_sections(self):
        """get_workpaper() returns dict with 'sections' key containing list of sections."""
        pool, conn = make_pool_conn()
        workpaper_with_sections = dict(_WORKPAPER_DICT, sections=_SECTIONS_4)
        conn.fetchrow = AsyncMock(return_value=workpaper_with_sections)
        conn.fetch = AsyncMock(return_value=_SECTIONS_4)

        mgr = WorkpaperManager()
        result = await mgr.get_workpaper(pool, TENANT, WORKPAPER_ID)

        assert "sections" in result

    # 5. test_update_section_updates_content
    @pytest.mark.asyncio
    async def test_update_section_updates_content(self):
        """update_section() issues UPDATE on workpaper_sections with content and is_complete."""
        pool, conn = make_pool_conn()
        updated_section = dict(_SECTIONS_4[0], content={"objective_text": "Assess IT general controls."})
        conn.fetchrow = AsyncMock(return_value=updated_section)

        mgr = WorkpaperManager()
        result = await mgr.update_section(
            pool,
            TENANT,
            SECTION_ID_1,
            content={"objective_text": "Assess IT general controls."},
            is_complete=False,
        )

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "UPDATE workpaper_sections" in query

    # 6. test_update_section_marks_complete
    @pytest.mark.asyncio
    async def test_update_section_marks_complete(self):
        """update_section() with is_complete=True stores True in the record."""
        pool, conn = make_pool_conn()
        complete_section = dict(_SECTIONS_4[0], is_complete=True)
        conn.fetchrow = AsyncMock(return_value=complete_section)

        mgr = WorkpaperManager()
        result = await mgr.update_section(
            pool,
            TENANT,
            SECTION_ID_1,
            content={"objective_text": "Assess IT general controls."},
            is_complete=True,
        )

        assert result["is_complete"] is True

    # 7. test_get_completion_status_correct_pct
    @pytest.mark.asyncio
    async def test_get_completion_status_correct_pct(self):
        """get_completion_status(): 2 of 4 sections complete → completion_pct=50.0."""
        pool, conn = make_pool_conn()
        two_complete = [
            dict(_SECTIONS_4[0], is_complete=True),
            dict(_SECTIONS_4[1], is_complete=True),
            _SECTIONS_4[2],
            _SECTIONS_4[3],
        ]
        conn.fetch = AsyncMock(return_value=two_complete)

        mgr = WorkpaperManager()
        result = await mgr.get_completion_status(pool, TENANT, WORKPAPER_ID)

        assert result["completion_pct"] == 50.0

    # 8. test_get_completion_status_100_when_all_done
    @pytest.mark.asyncio
    async def test_get_completion_status_100_when_all_done(self):
        """get_completion_status(): all 4 sections complete → completion_pct=100.0."""
        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=_SECTIONS_4_ALL_COMPLETE)

        mgr = WorkpaperManager()
        result = await mgr.get_completion_status(pool, TENANT, WORKPAPER_ID)

        assert result["completion_pct"] == 100.0

    # 9. test_finalize_raises_if_sections_incomplete
    @pytest.mark.asyncio
    async def test_finalize_raises_if_sections_incomplete(self):
        """finalize_workpaper() raises ValueError if any section is not complete."""
        pool, conn = make_pool_conn()
        # 1 section incomplete
        mixed_sections = [
            dict(_SECTIONS_4[0], is_complete=True),
            dict(_SECTIONS_4[1], is_complete=True),
            dict(_SECTIONS_4[2], is_complete=True),
            _SECTIONS_4[3],  # is_complete=False
        ]
        conn.fetch = AsyncMock(return_value=mixed_sections)

        mgr = WorkpaperManager()
        with pytest.raises(ValueError):
            await mgr.finalize_workpaper(pool, TENANT, WORKPAPER_ID)

    # 10. test_finalize_succeeds_when_all_complete
    @pytest.mark.asyncio
    async def test_finalize_succeeds_when_all_complete(self):
        """finalize_workpaper() UPDATEs status='final' and sets finalized_at when all sections complete."""
        pool, conn = make_pool_conn()
        conn.fetch = AsyncMock(return_value=_SECTIONS_4_ALL_COMPLETE)
        final_workpaper = dict(_WORKPAPER_DICT, status="final", finalized_at="2026-03-01T00:00:00Z")
        conn.fetchrow = AsyncMock(return_value=final_workpaper)

        mgr = WorkpaperManager()
        result = await mgr.finalize_workpaper(pool, TENANT, WORKPAPER_ID)

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "UPDATE workpaper" in query
        assert "final" in query
        assert "finalized_at" in query
        assert result["status"] == "final"

    # 11. test_submit_for_review_updates_status
    @pytest.mark.asyncio
    async def test_submit_for_review_updates_status(self):
        """submit_for_review() issues UPDATE setting status='in_review'."""
        pool, conn = make_pool_conn()
        in_review_workpaper = dict(_WORKPAPER_DICT, status="in_review")
        conn.fetchrow = AsyncMock(return_value=in_review_workpaper)

        mgr = WorkpaperManager()
        result = await mgr.submit_for_review(
            pool,
            TENANT,
            WORKPAPER_ID,
            reviewer="senior_auditor@example.com",
        )

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "UPDATE workpaper" in query
        assert "in_review" in query
        assert result["status"] == "in_review"

    # 12. test_add_section_inserts_row
    @pytest.mark.asyncio
    async def test_add_section_inserts_row(self):
        """add_section() INSERTs into workpaper_sections and returns the new section."""
        pool, conn = make_pool_conn()
        new_section = _make_section(
            "new-section-id-0000-0000-0000-0001",
            "additional_notes",
            "Additional Notes",
            sort_order=5,
        )
        conn.fetchrow = AsyncMock(return_value=new_section)

        mgr = WorkpaperManager()
        result = await mgr.add_section(
            pool,
            TENANT,
            WORKPAPER_ID,
            section_key="additional_notes",
            title="Additional Notes",
            sort_order=5,
        )

        conn.fetchrow.assert_called_once()
        query = conn.fetchrow.call_args[0][0]
        assert "INSERT INTO workpaper_sections" in query
        assert result["section_key"] == "additional_notes"
