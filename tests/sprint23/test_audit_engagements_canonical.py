"""
audit_engagements is reconciled to the V021 + V028 canonical shape.
Inserting via the canonical column names succeeds; legacy column names
(engagement_name, engagement_type, period_start, period_end, description)
no longer exist on the table.
"""
from __future__ import annotations

import uuid
import pytest


CANONICAL_COLS = {
    "id", "tenant_id", "plan_item_id", "title", "engagement_code",
    "audit_type", "status", "scope", "objectives",
    "planned_start_date", "planned_end_date",
    "actual_start_date", "actual_end_date",
    "budget_hours", "lead_auditor", "team_members", "engagement_manager",
    "status_notes", "created_at", "updated_at",
}

LEGACY_REMOVED = {
    "engagement_name", "engagement_type",
    "period_start", "period_end", "description", "fiscal_year",
}


@pytest.mark.asyncio
async def test_canonical_columns_present(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='audit_engagements'
    """)
    cols = {r["column_name"] for r in rows}
    missing = CANONICAL_COLS - cols
    assert not missing, f"audit_engagements missing canonical columns: {missing}"


@pytest.mark.asyncio
async def test_legacy_columns_absent(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='audit_engagements'
    """)
    cols = {r["column_name"] for r in rows}
    leftover = LEGACY_REMOVED & cols
    assert not leftover, (
        f"Legacy column names still on audit_engagements: {leftover} "
        "— code that used them will compile but break at INSERT time."
    )


@pytest.mark.asyncio
async def test_canonical_insert_succeeds(admin_conn, demo_tenant):
    eng_id = str(uuid.uuid4())
    async with admin_conn.transaction():
        await admin_conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", demo_tenant
        )
        await admin_conn.execute(
            """
            INSERT INTO audit_engagements
                (id, tenant_id, title, audit_type,
                 planned_start_date, planned_end_date,
                 scope, objectives, budget_hours, status_notes)
            VALUES ($1,$2,'Sprint23 probe','internal',
                    '2026-01-01','2026-03-31',
                    'IT general controls','Test objectives',120.0,'on track')
            """,
            eng_id, demo_tenant,
        )
        row = await admin_conn.fetchrow(
            "SELECT title, status_notes FROM audit_engagements WHERE id=$1", eng_id,
        )
        assert row["title"] == "Sprint23 probe"
        assert row["status_notes"] == "on track"
        await admin_conn.execute("DELETE FROM audit_engagements WHERE id=$1", eng_id)
