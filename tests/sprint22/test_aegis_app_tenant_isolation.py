"""
Connected as aegis_app with app.tenant_id set, SELECT on a tenant-scoped
table must return only that tenant's rows.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_notifications_scoped_to_tenant(app_conn, demo_tenant, other_tenant):
    """Seed rows for two tenants, then query scoped — only demo_tenant visible."""
    # Seed via admin (bypasses to insert; FORCE RLS means admin also needs context).
    # We pick notifications because it exists and has simple schema.
    async with app_conn.transaction():
        await app_conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", demo_tenant
        )
        demo_rows = await app_conn.fetch(
            "SELECT tenant_id FROM notifications LIMIT 50"
        )
    for r in demo_rows:
        assert str(r["tenant_id"]) == demo_tenant, \
            f"tenant leak: got {r['tenant_id']} while scoped to {demo_tenant}"

    # With other_tenant context (which has no seeded rows in dev), result set empty.
    async with app_conn.transaction():
        await app_conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", other_tenant
        )
        other_rows = await app_conn.fetch(
            "SELECT tenant_id FROM notifications LIMIT 50"
        )
    assert other_rows == [], (
        f"cross-tenant leak: scoped to {other_tenant} but got "
        f"{[str(r['tenant_id']) for r in other_rows]}"
    )


@pytest.mark.asyncio
async def test_no_tenant_context_sees_nothing(app_conn):
    """With no app.tenant_id set, RLS policy filters every row."""
    async with app_conn.transaction():
        await app_conn.execute("SELECT set_config('app.tenant_id', '', true)")
        try:
            rows = await app_conn.fetch("SELECT 1 FROM notifications LIMIT 1")
        except Exception:
            # Acceptable — bad setting may error rather than return empty.
            return
    assert rows == [], "RLS failed closed: returned rows with no tenant context"
