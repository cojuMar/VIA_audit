"""
V027 must have set FORCE ROW LEVEL SECURITY on every RLS-enabled table.
Without FORCE, the table owner (aegis_admin) bypasses the tenant_isolation
policy entirely — RLS becomes a no-op for migrations and anyone else who
connects as the owner.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_every_rls_enabled_table_is_forced(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = true
          AND c.relforcerowsecurity = false
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    """)
    unforced = [f"{r['schema_name']}.{r['table_name']}" for r in rows]
    assert unforced == [], f"tables with RLS but NOT forced: {unforced}"
