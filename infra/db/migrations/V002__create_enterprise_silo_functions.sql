-- =============================================================================
-- Project Aegis 2026 — Sprint 1
-- Migration : V002__create_enterprise_silo_functions.sql
-- Purpose   : PL/pgSQL functions for provisioning, deprovisioning, and
--             managing enterprise silo schemas.
--
-- Enterprise Silo Architecture
-- ────────────────────────────
-- Each enterprise tenant receives a dedicated PostgreSQL schema named:
--
--     tenant_<tenant_id with hyphens replaced by underscores>
--
-- e.g.  tenant_id = '550e8400-e29b-41d4-a716-446655440000'
--       schema    = 'tenant_550e8400_e29b_41d4_a716_446655440000'
--
-- Within that schema, the same table set as the pool model is created but
-- with NO RLS — isolation is structural (schema-level) rather than policy-
-- based.  The public.tenants / public.chain_sequence_counters rows are still
-- inserted as the master registry.
--
-- The firm bridge view allows a CPA firm tenant to query risk_scores across
-- all of its client tenants through a single unified view, respecting the
-- structural isolation.
--
-- Idempotency
-- ───────────
-- All functions use CREATE OR REPLACE and IF NOT EXISTS / IF EXISTS guards
-- so they can be re-applied safely.
--
-- Prerequisites
-- ─────────────
-- V001__create_pool_model_schema.sql must have been applied first.
--
-- Execution order
-- ───────────────
--   1. provision_enterprise_tenant()
--   2. deprovision_enterprise_tenant()
--   3. get_tenant_schema()
--   4. create_firm_bridge_view()
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. FUNCTION : provision_enterprise_tenant()
--    Creates a dedicated PostgreSQL schema and all required tables for a new
--    enterprise-tier tenant, then registers the tenant in the global registry.
--
--    Parameters
--    ──────────
--      p_tenant_id    : The UUID that will identify this tenant everywhere.
--                       Must be provided by the caller; the function validates
--                       it is not NULL.
--      p_display_name : Human-readable name, e.g. 'Acme Corp'.
--      p_region       : AWS/GCP/Azure region slug, e.g. 'us-east-1'.
--
--    Side-effects
--    ────────────
--      • Creates schema tenant_<id>.
--      • Creates evidence_records, evidence_chunks, risk_scores, and
--        chain_sequence_counters tables inside that schema with the same
--        column definitions as the pool model but WITHOUT RLS (isolation is
--        structural).
--      • Inserts into public.tenants with tier = 'enterprise_silo'.
--      • Inserts seed row into public.chain_sequence_counters.
--      • Grants all necessary privileges to aegis_app.
--      • Sets a descriptive COMMENT on the schema.
--
--    Idempotency
--    ───────────
--      Uses CREATE SCHEMA IF NOT EXISTS and INSERT ... ON CONFLICT DO NOTHING
--      so repeated calls for the same tenant_id are safe (no-ops).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.provision_enterprise_tenant(
    p_tenant_id    UUID,
    p_display_name TEXT,
    p_region       TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER          -- runs as the function owner (superuser / DBA role)
SET search_path = public  -- prevents search_path injection attacks
AS $$
DECLARE
    -- Derive the schema name by replacing UUID hyphens with underscores.
    v_schema_name TEXT := 'tenant_' || replace(p_tenant_id::text, '-', '_');
    -- Construct the fully-qualified table prefix for use in EXECUTE statements.
    v_schema_ident TEXT;
BEGIN
    -- ── Validation ───────────────────────────────────────────────────────────
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'provision_enterprise_tenant: p_tenant_id must not be NULL.';
    END IF;

    IF p_display_name IS NULL OR trim(p_display_name) = '' THEN
        RAISE EXCEPTION 'provision_enterprise_tenant: p_display_name must not be empty.';
    END IF;

    IF p_region IS NULL OR trim(p_region) = '' THEN
        RAISE EXCEPTION 'provision_enterprise_tenant: p_region must not be empty.';
    END IF;

    -- Quote the schema identifier once; reuse in all subsequent EXECUTE calls.
    v_schema_ident := quote_ident(v_schema_name);

    RAISE NOTICE 'Provisioning enterprise tenant % in schema %.', p_tenant_id, v_schema_name;

    -- ── Step 1 : Create the tenant schema ────────────────────────────────────
    -- IF NOT EXISTS makes this idempotent.
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema_name);

    -- Attach a human-readable comment for operational visibility.
    EXECUTE format(
        'COMMENT ON SCHEMA %I IS %L',
        v_schema_name,
        'Enterprise silo for tenant ' || p_tenant_id::text
    );

    -- ── Step 2 : Create evidence_records in the tenant schema ─────────────────
    -- Column definitions mirror public.evidence_records exactly.
    -- No RLS — isolation is structural (this schema belongs to one tenant).
    EXECUTE format($ddl$
        CREATE TABLE IF NOT EXISTS %I.evidence_records (
            evidence_id         UUID             NOT NULL DEFAULT gen_random_uuid(),
            tenant_id           UUID             NOT NULL DEFAULT %L,
            source_system       TEXT             NOT NULL,
            collected_at_utc    TIMESTAMPTZ      NOT NULL,
            payload_hash        BYTEA            NOT NULL,
            canonical_payload   JSONB            NOT NULL,
            chain_hash          BYTEA            NOT NULL,
            chain_sequence      BIGINT           NOT NULL,
            collector_version   TEXT             NOT NULL,
            zk_proof_id         UUID             NULL,
            dilithium_signature BYTEA            NULL,
            anomaly_score       DOUBLE PRECISION NULL,
            freshness_status    TEXT             NOT NULL DEFAULT 'fresh'
                                    CHECK (freshness_status IN ('fresh', 'stale', 'error')),
            created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

            CONSTRAINT evidence_records_pkey
                PRIMARY KEY (evidence_id),
            CONSTRAINT evidence_records_tenant_seq_unique
                UNIQUE (tenant_id, chain_sequence)
        )
        $ddl$,
        v_schema_name,
        p_tenant_id   -- baked-in default so every row has the correct tenant_id
    );

    -- Indexes on the silo evidence_records.
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_er_tenant_recent ON %I.evidence_records '
        '(tenant_id, collected_at_utc DESC) '
        'WHERE collected_at_utc > (NOW() - INTERVAL ''90 days'')',
        v_schema_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_er_source_system ON %I.evidence_records (source_system)',
        v_schema_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_er_chain_seq ON %I.evidence_records (chain_sequence)',
        v_schema_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_er_anomaly ON %I.evidence_records (anomaly_score DESC) '
        'WHERE anomaly_score IS NOT NULL',
        v_schema_name
    );

    -- ── Step 3 : Create evidence_chunks in the tenant schema ──────────────────
    EXECUTE format($ddl$
        CREATE TABLE IF NOT EXISTS %I.evidence_chunks (
            chunk_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
            evidence_id  UUID        NOT NULL,
            tenant_id    UUID        NOT NULL DEFAULT %L,
            chunk_index  INT         NOT NULL,
            chunk_text   TEXT        NOT NULL,
            tsv_content  TSVECTOR    NULL,
            token_count  INT         NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT evidence_chunks_pkey
                PRIMARY KEY (chunk_id),
            CONSTRAINT evidence_chunks_evidence_fk
                FOREIGN KEY (evidence_id)
                REFERENCES %I.evidence_records (evidence_id)
                ON DELETE CASCADE
        )
        $ddl$,
        v_schema_name,
        p_tenant_id,
        v_schema_name   -- FK references the silos own evidence_records
    );

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS idx_ec_tsv ON %I.evidence_chunks '
        'USING GIN (tsv_content) WHERE tsv_content IS NOT NULL',
        v_schema_name
    );

    -- ── Step 4 : Create risk_scores in the tenant schema ──────────────────────
    EXECUTE format($ddl$
        CREATE TABLE IF NOT EXISTS %I.risk_scores (
            score_id     UUID             NOT NULL DEFAULT gen_random_uuid(),
            tenant_id    UUID             NOT NULL DEFAULT %L,
            entity_type  TEXT             NULL,
            entity_id    TEXT             NULL,
            risk_index   DOUBLE PRECISION NOT NULL CHECK (risk_index BETWEEN 0 AND 1),
            components   JSONB            NULL,
            computed_at  TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
            framework    TEXT             NOT NULL DEFAULT 'soc2',

            CONSTRAINT risk_scores_pkey
                PRIMARY KEY (score_id)
        )
        $ddl$,
        v_schema_name,
        p_tenant_id
    );

    -- ── Step 5 : Per-silo chain_sequence_counters ─────────────────────────────
    -- Each enterprise silo maintains its own counter table inside the schema for
    -- consistency with the pool model; the public.chain_sequence_counters row is
    -- also inserted as the authoritative source used by the pool-model trigger.
    EXECUTE format($ddl$
        CREATE TABLE IF NOT EXISTS %I.chain_sequence_counters (
            tenant_id UUID   NOT NULL DEFAULT %L,
            next_seq  BIGINT NOT NULL DEFAULT 1,
            CONSTRAINT chain_seq_ctr_pkey PRIMARY KEY (tenant_id)
        )
        $ddl$,
        v_schema_name,
        p_tenant_id
    );

    -- Seed the counter if it doesn''t already exist.
    EXECUTE format(
        'INSERT INTO %I.chain_sequence_counters (tenant_id, next_seq) VALUES (%L, 1) '
        'ON CONFLICT DO NOTHING',
        v_schema_name,
        p_tenant_id
    );

    -- ── Step 6 : Register in public.tenants ───────────────────────────────────
    -- ON CONFLICT DO NOTHING makes this idempotent; a second call for the same
    -- tenant_id will not overwrite existing metadata.
    INSERT INTO public.tenants (
        tenant_id, display_name, tier, region, external_id
    )
    VALUES (
        p_tenant_id, p_display_name, 'enterprise_silo', p_region,
        -- Use tenant_id as external_id placeholder; the application should
        -- UPDATE this with the real IdP external identifier after provisioning.
        p_tenant_id::text
    )
    ON CONFLICT (tenant_id) DO NOTHING;

    -- ── Step 7 : Seed public.chain_sequence_counters ──────────────────────────
    -- The pool-model trigger references public.chain_sequence_counters; seed
    -- this even for silo tenants for uniformity.
    INSERT INTO public.chain_sequence_counters (tenant_id, next_seq)
    VALUES (p_tenant_id, 1)
    ON CONFLICT DO NOTHING;

    -- ── Step 8 : Grant privileges to aegis_app ────────────────────────────────
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO aegis_app', v_schema_name);
    EXECUTE format('GRANT SELECT, INSERT ON %I.evidence_records TO aegis_app', v_schema_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I.evidence_chunks TO aegis_app', v_schema_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I.risk_scores TO aegis_app', v_schema_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I.chain_sequence_counters TO aegis_app', v_schema_name);

    RAISE NOTICE 'Enterprise tenant % provisioned successfully in schema %.', p_tenant_id, v_schema_name;
END;
$$;

COMMENT ON FUNCTION public.provision_enterprise_tenant(UUID, TEXT, TEXT) IS
    'Provisions a dedicated PostgreSQL schema and all required tables for a new '
    'enterprise-silo tenant. Inserts into public.tenants and public.chain_sequence_counters. '
    'Grants all required privileges to aegis_app. Idempotent via ON CONFLICT DO NOTHING '
    'and CREATE ... IF NOT EXISTS guards.';

-- ---------------------------------------------------------------------------
-- 2. FUNCTION : deprovision_enterprise_tenant()
--    Soft-deactivates a tenant by:
--      a) Setting is_active = FALSE in public.tenants.
--      b) Renaming the tenant schema to archived_tenant_<id>_<YYYYMMDD>.
--    Data is NEVER dropped.  The archived schema can be restored by a DBA if
--    needed.  A permanent deletion workflow (with legal hold checks) is out of
--    scope for this migration and handled by the operations runbook.
--
--    Parameters
--    ──────────
--      p_tenant_id : UUID of the tenant to decommission.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.deprovision_enterprise_tenant(
    p_tenant_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_schema  TEXT := 'tenant_' || replace(p_tenant_id::text, '-', '_');
    v_archived_schema TEXT := 'archived_tenant_'
                                || replace(p_tenant_id::text, '-', '_')
                                || '_'
                                || to_char(NOW() AT TIME ZONE 'UTC', 'YYYYMMDD');
    v_tenant_tier     TEXT;
BEGIN
    -- ── Validation ───────────────────────────────────────────────────────────
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'deprovision_enterprise_tenant: p_tenant_id must not be NULL.';
    END IF;

    -- Verify the tenant exists and is an enterprise silo.
    SELECT tier INTO v_tenant_tier
      FROM public.tenants
     WHERE tenant_id = p_tenant_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'deprovision_enterprise_tenant: tenant % not found.', p_tenant_id;
    END IF;

    IF v_tenant_tier <> 'enterprise_silo' THEN
        RAISE EXCEPTION
            'deprovision_enterprise_tenant: tenant % has tier ''%'', expected ''enterprise_silo''. '
            'Pool model tenants are deprovisioned differently (RLS rows are simply soft-deleted).',
            p_tenant_id, v_tenant_tier;
    END IF;

    -- Verify the source schema actually exists before attempting the rename.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata
         WHERE schema_name = v_current_schema
    ) THEN
        RAISE WARNING
            'deprovision_enterprise_tenant: schema % does not exist. '
            'Marking tenant inactive in public.tenants but skipping schema rename.',
            v_current_schema;
    ELSE
        -- ── Step 1 : Rename schema to archived_tenant_<id>_<YYYYMMDD> ──────────
        -- If a schema with the target name already exists (e.g. same-day re-run)
        -- append an epoch suffix to avoid collision.
        IF EXISTS (
            SELECT 1 FROM information_schema.schemata
             WHERE schema_name = v_archived_schema
        ) THEN
            v_archived_schema := v_archived_schema || '_' || extract(epoch FROM NOW())::bigint;
            RAISE WARNING
                'Target archive schema name already exists; using unique name: %.',
                v_archived_schema;
        END IF;

        EXECUTE format('ALTER SCHEMA %I RENAME TO %I', v_current_schema, v_archived_schema);

        RAISE NOTICE 'Schema % renamed to %.', v_current_schema, v_archived_schema;
    END IF;

    -- ── Step 2 : Mark tenant inactive in public.tenants ─────────────────────
    UPDATE public.tenants
       SET is_active   = FALSE,
           updated_at  = NOW()
     WHERE tenant_id = p_tenant_id;

    RAISE NOTICE
        'Tenant % marked inactive. Archived schema: %. Data preserved.',
        p_tenant_id, v_archived_schema;
END;
$$;

COMMENT ON FUNCTION public.deprovision_enterprise_tenant(UUID) IS
    'Soft-decommissions an enterprise silo tenant. Sets is_active = FALSE in '
    'public.tenants and renames the tenant schema to archived_tenant_<id>_<YYYYMMDD>. '
    'Data is NEVER dropped. The archived schema can be restored by a DBA. '
    'Permanent deletion requires a separate, audited runbook process.';

-- ---------------------------------------------------------------------------
-- 3. FUNCTION : get_tenant_schema()
--    Returns the PostgreSQL schema name that holds the given tenant''s tables.
--    For enterprise silo tenants this is the dedicated schema; for pool model
--    tenants this is ''public''.  Used by the application''s query router to
--    build schema-qualified SQL at runtime without hardcoding schema names.
--
--    Parameters
--    ──────────
--      p_tenant_id : UUID of the tenant to look up.
--
--    Returns
--    ───────
--      TEXT — schema name, e.g. 'public' or 'tenant_550e8400_e29b_...'.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tenant_schema(
    p_tenant_id UUID
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_tier TEXT;
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'get_tenant_schema: p_tenant_id must not be NULL.';
    END IF;

    SELECT tier INTO v_tier
      FROM public.tenants
     WHERE tenant_id = p_tenant_id
       AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'get_tenant_schema: no active tenant found with id %.', p_tenant_id;
    END IF;

    CASE v_tier
        WHEN 'enterprise_silo' THEN
            -- Return the derived schema name.
            RETURN 'tenant_' || replace(p_tenant_id::text, '-', '_');
        WHEN 'smb_pool' THEN
            -- Pool model tenants share the public schema.
            RETURN 'public';
        ELSE
            RAISE EXCEPTION
                'get_tenant_schema: unknown tier ''%'' for tenant %.', v_tier, p_tenant_id;
    END CASE;
END;
$$;

COMMENT ON FUNCTION public.get_tenant_schema(UUID) IS
    'Returns the PostgreSQL schema that holds the given tenant''s data. '
    'Returns ''public'' for smb_pool tenants and the dedicated schema name for '
    'enterprise_silo tenants. Used by the application query router. '
    'Raises EXCEPTION if the tenant does not exist or is inactive.';

-- ---------------------------------------------------------------------------
-- 4. FUNCTION : create_firm_bridge_view()
--    Creates a unified risk_summary view in a firm-specific schema that
--    UNIONs risk_scores from all of the firm''s client tenant schemas.
--    This allows a CPA firm''s dashboard to query risk across all clients
--    through a single view while each client''s data remains structurally
--    isolated in its own schema.
--
--    Parameters
--    ──────────
--      p_firm_tenant_id   : UUID of the firm tenant (must be enterprise_silo).
--      p_client_tenant_ids: Array of client tenant UUIDs whose risk_scores
--                           should be included in the bridge view.
--
--    Side-effects
--    ────────────
--      • Creates schema firm_<firm_id> if it does not already exist.
--      • Creates or replaces view firm_<firm_id>.risk_summary that UNIONs
--        risk_scores from each client''s schema with the literal client
--        tenant_id baked into each UNION branch.
--      • Grants SELECT on the view to aegis_app.
--
--    Security note
--    ─────────────
--    The dynamic UNION accesses client schemas directly.  Access control is
--    enforced at the schema level (aegis_app must have USAGE on each client
--    schema) rather than RLS.  The firm dashboard service must validate that
--    p_client_tenant_ids genuinely belong to the firm before calling this
--    function to prevent cross-firm data leakage.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_firm_bridge_view(
    p_firm_tenant_id    UUID,
    p_client_tenant_ids UUID[]
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_firm_schema  TEXT := 'firm_' || replace(p_firm_tenant_id::text, '-', '_');
    v_client_id    UUID;
    v_client_schema TEXT;
    v_union_parts  TEXT[] := ARRAY[]::TEXT[];
    v_union_sql    TEXT;
    v_view_sql     TEXT;
BEGIN
    -- ── Validation ───────────────────────────────────────────────────────────
    IF p_firm_tenant_id IS NULL THEN
        RAISE EXCEPTION 'create_firm_bridge_view: p_firm_tenant_id must not be NULL.';
    END IF;

    IF p_client_tenant_ids IS NULL OR array_length(p_client_tenant_ids, 1) = 0 THEN
        RAISE EXCEPTION
            'create_firm_bridge_view: p_client_tenant_ids must contain at least one UUID.';
    END IF;

    -- Verify the firm tenant exists.
    IF NOT EXISTS (
        SELECT 1 FROM public.tenants
         WHERE tenant_id = p_firm_tenant_id AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION
            'create_firm_bridge_view: firm tenant % not found or inactive.', p_firm_tenant_id;
    END IF;

    -- ── Step 1 : Create firm schema ───────────────────────────────────────────
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_firm_schema);
    EXECUTE format(
        'COMMENT ON SCHEMA %I IS %L',
        v_firm_schema,
        'Bridge schema for firm tenant ' || p_firm_tenant_id::text
            || '. Contains unified views across client tenant schemas.'
    );
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO aegis_app', v_firm_schema);

    -- ── Step 2 : Build per-client UNION branches ──────────────────────────────
    -- Each branch selects from the client''s schema with the literal client
    -- tenant_id embedded so the consuming query knows which client each row
    -- belongs to.
    FOREACH v_client_id IN ARRAY p_client_tenant_ids LOOP
        -- Verify client tenant exists and is active.
        IF NOT EXISTS (
            SELECT 1 FROM public.tenants
             WHERE tenant_id = v_client_id AND is_active = TRUE
        ) THEN
            RAISE WARNING
                'create_firm_bridge_view: client tenant % not found or inactive — skipping.',
                v_client_id;
            CONTINUE;
        END IF;

        v_client_schema := public.get_tenant_schema(v_client_id);

        -- Build one SELECT branch.
        -- The literal client_tenant_id is included so the view consumer can
        -- filter or group by client without relying on the stored tenant_id
        -- column (which is also the same value, but being explicit is safer).
        v_union_parts := v_union_parts || format(
            $branch$
            SELECT
                score_id,
                %L::uuid     AS client_tenant_id,
                entity_type,
                entity_id,
                risk_index,
                components,
                computed_at,
                framework
            FROM %I.risk_scores
            WHERE tenant_id = %L::uuid
            $branch$,
            v_client_id,   -- literal client_tenant_id in SELECT
            v_client_schema,
            v_client_id    -- WHERE filter
        );
    END LOOP;

    -- Bail out if all clients were skipped.
    IF array_length(v_union_parts, 1) IS NULL OR array_length(v_union_parts, 1) = 0 THEN
        RAISE EXCEPTION
            'create_firm_bridge_view: no valid client tenants found. View not created.';
    END IF;

    -- ── Step 3 : Assemble and execute the CREATE OR REPLACE VIEW statement ────
    v_union_sql := array_to_string(v_union_parts, E'\nUNION ALL\n');

    v_view_sql := format(
        'CREATE OR REPLACE VIEW %I.risk_summary AS %s',
        v_firm_schema,
        v_union_sql
    );

    EXECUTE v_view_sql;

    -- ── Step 4 : Grant SELECT to aegis_app ────────────────────────────────────
    EXECUTE format('GRANT SELECT ON %I.risk_summary TO aegis_app', v_firm_schema);

    RAISE NOTICE
        'Firm bridge view %.risk_summary created with % client tenant(s).',
        v_firm_schema, array_length(v_union_parts, 1);
END;
$$;

COMMENT ON FUNCTION public.create_firm_bridge_view(UUID, UUID[]) IS
    'Creates a unified risk_summary view in the firm-specific schema that UNIONs '
    'risk_scores from all specified client tenant schemas. Enables the CPA firm '
    'dashboard to query risk across clients through a single view while maintaining '
    'structural isolation. '
    'SECURITY: the caller is responsible for validating that p_client_tenant_ids '
    'genuinely belong to the firm before invoking this function.';

-- ---------------------------------------------------------------------------
-- GRANTS : allow aegis_app to call these provisioning functions.
-- In production, these functions should be callable only by the platform
-- admin service role, not by the regular application pool.  Adjust grants
-- according to your role hierarchy.
-- ---------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION public.provision_enterprise_tenant(UUID, TEXT, TEXT)  TO aegis_app;
GRANT EXECUTE ON FUNCTION public.deprovision_enterprise_tenant(UUID)             TO aegis_app;
GRANT EXECUTE ON FUNCTION public.get_tenant_schema(UUID)                         TO aegis_app;
GRANT EXECUTE ON FUNCTION public.create_firm_bridge_view(UUID, UUID[])           TO aegis_app;

-- ---------------------------------------------------------------------------
-- END OF MIGRATION V002
-- ---------------------------------------------------------------------------
