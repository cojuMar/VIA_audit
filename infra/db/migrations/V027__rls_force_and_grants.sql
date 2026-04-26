-- ============================================================================
--  V027 — Sprint 22: Make Row-Level Security actually enforce isolation.
-- ============================================================================
--
--  Pre-Sprint-22 state: many services connected as `aegis_admin` (table owner),
--  who bypasses RLS unless `FORCE ROW LEVEL SECURITY` is set. It wasn't, so
--  RLS was effectively a no-op for those services.
--
--  This migration:
--    1. Backfills missing GRANTs to `aegis_app` for tables created in V005,
--       V006, and V007 that were skipped by their original migrations.
--    2. Sets ALTER DEFAULT PRIVILEGES so future tables created by aegis_admin
--       automatically grant CRUD to aegis_app.
--    3. Enables FORCE ROW LEVEL SECURITY on every table that has RLS enabled,
--       so even the table owner is subject to the tenant_isolation policy.
--
--  After this lands, every service must connect as `aegis_app` (Sprint 22
--  also updates docker-compose.yml). `aegis_admin` is reserved for migrations.
-- ============================================================================

-- ── 1. Catch-up GRANTs ──────────────────────────────────────────────────────

-- V005 tables (ingestion)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.connector_registry    TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingestion_runs        TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingestion_watermarks  TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.connector_schemas     TO aegis_app;

-- V006 tables (zk-proofs)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.zk_proofs             TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.zk_circuit_registry   TO aegis_app;

-- V007 tables (ml)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.anomaly_scores            TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.benford_entity_stats      TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_model_registry         TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.jurisdiction_risk_scores  TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.vendor_profiles           TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dri_framework_weights     TO aegis_app;

-- Sequences used by these tables (gen_random_uuid is the default; explicit
-- sequences only need granting if SERIAL columns exist).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aegis_app;

-- ── 2. Default privileges for any future table owned by aegis_admin ─────────

ALTER DEFAULT PRIVILEGES FOR ROLE aegis_admin IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;

ALTER DEFAULT PRIVILEGES FOR ROLE aegis_admin IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aegis_app;

ALTER DEFAULT PRIVILEGES FOR ROLE aegis_admin IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO aegis_app;

-- ── 3. Backfill RLS + tenant_isolation policy on stragglers ────────────────
-- Two tables carry a tenant_id column but never had RLS turned on:
--   • public.chain_sequence_counters (V001) — per-tenant sequence state
--   • public.access_requests (V004)         — PAM approval queue

ALTER TABLE public.chain_sequence_counters ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'chain_sequence_counters'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON public.chain_sequence_counters
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    END IF;
END $$;

ALTER TABLE public.access_requests ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'access_requests'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON public.access_requests
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    END IF;
END $$;

-- ── 4. FORCE RLS on every table that has RLS enabled ────────────────────────
--
-- This is the critical fix: without FORCE, table owners (aegis_admin and
-- anyone migration-impersonating it) bypass RLS entirely, which made every
-- service running as aegis_admin equivalent to "no tenant isolation."
--
-- We discover the set of RLS-enabled tables dynamically rather than listing
-- ~90 names; this means new tables created with `ENABLE ROW LEVEL SECURITY`
-- in later migrations will need their own FORCE statement (or a re-run of
-- this block in a follow-up migration).

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT n.nspname AS schema_name, c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = true
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',
            r.schema_name, r.table_name
        );
    END LOOP;
END $$;
