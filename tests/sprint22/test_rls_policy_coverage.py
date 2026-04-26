"""
Every RLS-enabled table must also have at least one policy, otherwise
RLS silently rejects every row. And every tenant-scoped table (has a
`tenant_id` column) must have RLS enabled.
"""
from __future__ import annotations

import pytest


EXEMPT_TENANT_ID_TABLES = {"tenants", "flyway_schema_history"}


@pytest.mark.asyncio
async def test_rls_enabled_tables_have_policies(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = true
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND NOT EXISTS (
              SELECT 1 FROM pg_policies p
              WHERE p.schemaname = n.nspname AND p.tablename = c.relname
          )
    """)
    gaps = [f"{r['schema_name']}.{r['table_name']}" for r in rows]
    assert gaps == [], f"RLS-enabled tables WITHOUT policies: {gaps}"


@pytest.mark.asyncio
async def test_tenant_id_tables_have_rls(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT a.table_schema, a.table_name
        FROM information_schema.columns a
        JOIN pg_class c ON c.relname = a.table_name
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = a.table_schema
        WHERE a.column_name = 'tenant_id'
          AND c.relkind = 'r'
          AND c.relrowsecurity = false
          AND a.table_schema NOT IN ('pg_catalog', 'information_schema')
    """)
    missing = [
        f"{r['table_schema']}.{r['table_name']}" for r in rows
        if r["table_name"] not in EXEMPT_TENANT_ID_TABLES
    ]
    assert missing == [], f"tenant_id tables WITHOUT RLS: {missing}"
