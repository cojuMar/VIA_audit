-- ============================================================================
--  Sprint 22 CI check — Row-Level Security coverage
-- ============================================================================
--
-- Emits RAISE EXCEPTION if any of the following defects are found:
--   1. A table has RLS ENABLED but has NO policy (silent rejection of all rows).
--   2. A table has RLS ENABLED but is NOT forced (owner bypasses RLS).
--   3. A tenant-scoped table (has `tenant_id` column) does NOT have RLS.
--
-- Usage in CI:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f infra/db/check_rls_coverage.sql
--
-- Exit code 0 = clean, non-zero = defects (pipeline fails).
-- ============================================================================

DO $$
DECLARE
    r            RECORD;
    defect_count INTEGER := 0;
    msg          TEXT;
BEGIN
    -- Defect 1: RLS enabled but no policy
    FOR r IN
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
    LOOP
        RAISE WARNING 'RLS ENABLED but NO POLICY: %.%', r.schema_name, r.table_name;
        defect_count := defect_count + 1;
    END LOOP;

    -- Defect 2: RLS enabled but not forced (owner bypasses)
    FOR r IN
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = true
          AND c.relforcerowsecurity = false
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    LOOP
        RAISE WARNING 'RLS ENABLED but NOT FORCED: %.% (owner bypasses)',
                      r.schema_name, r.table_name;
        defect_count := defect_count + 1;
    END LOOP;

    -- Defect 3: tenant_id column exists but RLS is off
    FOR r IN
        SELECT a.table_schema AS schema_name, a.table_name
        FROM information_schema.columns a
        JOIN pg_class c ON c.relname = a.table_name
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = a.table_schema
        WHERE a.column_name = 'tenant_id'
          AND c.relkind = 'r'
          AND c.relrowsecurity = false
          AND a.table_schema NOT IN ('pg_catalog', 'information_schema')
          -- Allow a small set of infra tables that legitimately track tenant_id
          -- without RLS (e.g. the tenants registry itself).
          AND a.table_name NOT IN ('tenants', 'flyway_schema_history')
    LOOP
        RAISE WARNING 'tenant_id column WITHOUT RLS: %.%',
                      r.schema_name, r.table_name;
        defect_count := defect_count + 1;
    END LOOP;

    IF defect_count > 0 THEN
        RAISE EXCEPTION 'RLS coverage check failed: % defect(s).', defect_count;
    ELSE
        RAISE NOTICE 'RLS coverage check passed.';
    END IF;
END $$;
