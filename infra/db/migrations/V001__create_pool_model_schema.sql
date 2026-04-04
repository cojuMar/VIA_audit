-- =============================================================================
-- Project Aegis 2026 — Sprint 1
-- Migration : V001__create_pool_model_schema.sql
-- Purpose   : Base schema for the SMB Pool Model with Row-Level Security.
--             All SMB tenants share these tables; tenant isolation is enforced
--             exclusively via PostgreSQL RLS policies keyed on the
--             app.tenant_id session-level setting injected by the application
--             connection pool (e.g. PgBouncer / application startup hook).
--
-- Design notes
-- ────────────
--   • Pool model  → all tenants share public.* tables; RLS is the boundary.
--   • Enterprise  → separate schemas provisioned by V002; public.* tables are
--                   still populated for metadata but the actual evidence lives
--                   in the tenant schema.
--   • chain_hash / chain_sequence form a tamper-evident append-only log per
--     tenant (HMAC-SHA256 chain seeded from the previous record's hash).
--   • Post-quantum fields (dilithium_signature) are nullable during the
--     migration period while collectors are being upgraded.
--   • The vector(1536) column in evidence_chunks requires pgvector.  The
--     entire column is created inside a DO block that silently skips if the
--     extension is absent so the rest of the migration never fails.
--
-- Idempotency
-- ───────────
--   Every object is created with IF NOT EXISTS or CREATE OR REPLACE so this
--   file can be re-run safely against a database that was partially migrated.
--   The Flyway checksum will still prevent accidental re-runs in production;
--   idempotency is provided as an additional safety net.
--
-- Execution order
-- ───────────────
--   1. Extensions
--   2. Helper function  : get_tenant_id()
--   3. Core tables      : tenants, chain_sequence_counters
--   4. Evidence tables  : evidence_records, evidence_chunks
--   5. Risk table       : risk_scores
--   6. Trigger functions and triggers
--   7. RLS policies
--   8. Application role and grants
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. EXTENSIONS
--    uuid-ossp  : gen_random_uuid() fallback (also available via pgcrypto);
--                 required for UUID default values.
--    pgcrypto   : digest() for SHA-256 chain hashes, gen_random_uuid().
--    pg_trgm    : GIN trigram indexes for fast LIKE / similarity searches on
--                 text fields (source_system, display_name, etc.).
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "pgcrypto"   WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "pg_trgm"    WITH SCHEMA public;

-- ---------------------------------------------------------------------------
-- 2. HELPER FUNCTION : get_tenant_id()
--    Returns the current tenant UUID from the session-level GUC
--    app.tenant_id.  Used in all RLS policies to keep policy expressions
--    readable and to centralise the cast in one place.
--
--    The application MUST execute:
--        SET LOCAL app.tenant_id = '<uuid>';
--    inside every transaction before touching any RLS-protected table.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_tenant_id()
    RETURNS UUID
    LANGUAGE sql
    STABLE
    SECURITY DEFINER  -- runs as the function owner, not the calling role
    SET search_path = public
AS $$
    SELECT current_setting('app.tenant_id', true)::uuid;
$$;

COMMENT ON FUNCTION public.get_tenant_id() IS
    'Returns the UUID set in the session GUC app.tenant_id. '
    'All RLS policies reference this function so the cast logic is centralised. '
    'The application must SET LOCAL app.tenant_id = ''<uuid>'' before any DML '
    'on RLS-protected tables.';

-- ---------------------------------------------------------------------------
-- 3a. TENANTS TABLE
--     Master registry of all tenants regardless of pool/silo model.
--     tier = ''smb_pool''       → tenant data lives in public.* tables, RLS-isolated.
--     tier = ''enterprise_silo'' → tenant has its own schema (provisioned by V002).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenants (
    tenant_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
    -- Opaque identifier from the upstream identity provider (e.g. Auth0 org ID).
    external_id  TEXT        NOT NULL,
    display_name TEXT        NOT NULL,
    -- Pool model vs dedicated silo; drives routing logic in the application.
    tier         TEXT        NOT NULL CHECK (tier IN ('smb_pool', 'enterprise_silo')),
    -- AWS / GCP / Azure region slug, e.g. ''us-east-1''.  Used for data-residency
    -- enforcement; no cross-region queries are permitted.
    region       TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT tenants_pkey         PRIMARY KEY (tenant_id),
    CONSTRAINT tenants_external_id  UNIQUE      (external_id)
);

COMMENT ON TABLE  public.tenants IS
    'Master tenant registry. Populated at tenant on-boarding; never deleted '
    '(soft-delete via is_active). Drives RLS and schema-routing for all downstream tables.';
COMMENT ON COLUMN public.tenants.tier IS
    '''smb_pool'' → shared tables with RLS; '
    '''enterprise_silo'' → dedicated schema provisioned by provision_enterprise_tenant().';
COMMENT ON COLUMN public.tenants.external_id IS
    'Opaque identifier supplied by the upstream IdP (Auth0 org_id, Okta tenant, etc.).';

-- ---------------------------------------------------------------------------
-- 3b. CHAIN SEQUENCE COUNTERS (per-tenant)
--     Guarantees a strictly-monotonic, gap-free sequence number for each
--     tenant''s evidence chain.  The validate_chain_sequence() trigger on
--     evidence_records locks this row (FOR UPDATE) before each insert and
--     increments next_seq atomically, preventing any duplicate or out-of-order
--     sequence numbers even under concurrent load.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chain_sequence_counters (
    tenant_id UUID   NOT NULL,
    next_seq  BIGINT NOT NULL DEFAULT 1,

    CONSTRAINT chain_sequence_counters_pkey
        PRIMARY KEY (tenant_id),
    CONSTRAINT chain_sequence_counters_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT  -- never cascade-delete audit infrastructure
);

COMMENT ON TABLE  public.chain_sequence_counters IS
    'Per-tenant monotonic counter for evidence_records.chain_sequence. '
    'The validate_chain_sequence trigger locks and increments this row on every '
    'evidence insert, guaranteeing a gap-free, tamper-evident sequence.';
COMMENT ON COLUMN public.chain_sequence_counters.next_seq IS
    'The sequence number that the NEXT inserted evidence record must carry. '
    'Starts at 1. Incremented atomically by the trigger under a row-level lock.';

-- ---------------------------------------------------------------------------
-- 4a. EVIDENCE RECORDS TABLE
--     Core append-only audit log.  Each row represents one collected evidence
--     artifact from a source system.  The chain_hash / chain_sequence columns
--     form a per-tenant tamper-evident hash chain (HMAC-SHA256).
--     Rows should never be updated or deleted in production; the immutability
--     contract is enforced at the application layer and via grants (no UPDATE/
--     DELETE granted to aegis_app on this table in non-admin roles).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.evidence_records (
    -- Primary key — UUID v4 generated by pgcrypto.
    evidence_id         UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant owning this record.  RLS ensures cross-tenant reads are impossible.
    tenant_id           UUID        NOT NULL,

    -- Logical identifier for the upstream data source, e.g. ''aws_cloudtrail'',
    -- ''quickbooks'', ''stripe'', ''github_actions''.
    source_system       TEXT        NOT NULL,

    -- The UTC timestamp at which the collector observed or received this event.
    -- Distinct from created_at which records DB insertion time.
    collected_at_utc    TIMESTAMPTZ NOT NULL,

    -- SHA-256 digest of the raw (pre-canonicalisation) payload bytes.
    -- Stored as BYTEA (32 bytes) rather than hex TEXT to save space and allow
    -- direct binary comparison.
    payload_hash        BYTEA       NOT NULL,

    -- Canonicalised, normalised representation of the evidence payload stored
    -- as JSONB.  Allows GIN indexing and JSONPath queries without deserialisation.
    canonical_payload   JSONB       NOT NULL,

    -- Tamper-evident hash chain.  Each record''s chain_hash is computed as:
    --   HMAC-SHA256(key=<tenant_secret>, message=prev_chain_hash || payload_hash)
    -- The first record in a tenant''s chain uses a zero-filled prev_chain_hash.
    -- Verification is performed out-of-band by the integrity checker service.
    chain_hash          BYTEA       NOT NULL,

    -- Monotonically increasing per-tenant sequence.  Combined with chain_hash
    -- this makes any insertion, deletion, or reordering detectable.
    -- Enforced by the validate_chain_sequence trigger + chain_sequence_counters.
    chain_sequence      BIGINT      NOT NULL,

    -- Semantic version of the collector that produced this record, e.g. ''2.3.1''.
    -- Used for schema-migration auditing and replay capability.
    collector_version   TEXT        NOT NULL,

    -- FK to zk_proofs table added in a later migration (V00x__add_zk_proofs).
    -- Nullable during the initial rollout period.
    zk_proof_id         UUID        NULL,

    -- Post-quantum (CRYSTALS-Dilithium3) signature over (payload_hash || chain_hash).
    -- NULL during the migration period while collectors are being upgraded to
    -- post-quantum signing.  Presence is tracked via collector_version.
    dilithium_signature BYTEA       NULL,

    -- ML anomaly score produced by the real-time scoring service.
    -- NULL until the score is written back asynchronously; range [0.0, 1.0].
    anomaly_score       DOUBLE PRECISION NULL,

    -- Staleness flag maintained by the freshness-monitor background job.
    freshness_status    TEXT        NOT NULL DEFAULT 'fresh'
                            CHECK (freshness_status IN ('fresh', 'stale', 'error')),

    -- DB insertion timestamp (NOT the event time — use collected_at_utc for that).
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT evidence_records_pkey
        PRIMARY KEY (evidence_id),
    CONSTRAINT evidence_records_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT,
    -- Per-tenant sequence uniqueness guarantees no gaps or duplicates.
    CONSTRAINT evidence_records_tenant_seq_unique
        UNIQUE (tenant_id, chain_sequence)
);

COMMENT ON TABLE  public.evidence_records IS
    'Append-only audit evidence log. Rows represent individual evidence artifacts '
    'collected from upstream source systems. Tamper-evidence is provided via the '
    'chain_hash/chain_sequence mechanism enforced by the validate_chain_sequence trigger. '
    'RLS ensures strict tenant isolation in the SMB pool model.';
COMMENT ON COLUMN public.evidence_records.payload_hash IS
    'SHA-256 digest of the raw, pre-canonicalisation payload bytes (32 BYTEA). '
    'Used by the integrity-checker service for out-of-band verification.';
COMMENT ON COLUMN public.evidence_records.chain_hash IS
    'HMAC-SHA256 over (prev_chain_hash || payload_hash) using a tenant-specific '
    'secret.  Stored as 32-byte BYTEA.  Computed by the collector before insert.';
COMMENT ON COLUMN public.evidence_records.dilithium_signature IS
    'CRYSTALS-Dilithium3 post-quantum signature. NULL during migration period. '
    'Presence/absence is correlated with collector_version >= 3.0.0.';
COMMENT ON COLUMN public.evidence_records.zk_proof_id IS
    'FK to the zk_proofs table (added in a future migration). NULL until the '
    'ZK-proof pipeline is enabled for this tenant.';

-- ---------------------------------------------------------------------------
-- 4b. INDEXES ON EVIDENCE RECORDS
-- ---------------------------------------------------------------------------

-- Recent-evidence partial index: the most common query pattern is
-- "give me all evidence for tenant X collected in the last 90 days."
-- A partial index covering only the hot window drastically reduces its size.
-- NOTE: PostgreSQL evaluates the WHERE clause of a partial index at index-scan
-- time, so the planner will use this index when the query predicate is
-- compatible (collected_at_utc > NOW() - INTERVAL ''90 days'').
CREATE INDEX IF NOT EXISTS idx_evidence_tenant_recent
    ON public.evidence_records (tenant_id, collected_at_utc DESC)
    WHERE collected_at_utc > (NOW() - INTERVAL '90 days');

COMMENT ON INDEX public.idx_evidence_tenant_recent IS
    'Partial index covering only evidence collected in the last 90 days. '
    'Used by the dashboard and the real-time anomaly-scoring pipeline.';

-- Source system index: supports filtering/grouping by upstream system
-- (e.g. show all AWS CloudTrail evidence for a tenant).
CREATE INDEX IF NOT EXISTS idx_evidence_source_system
    ON public.evidence_records (tenant_id, source_system);

COMMENT ON INDEX public.idx_evidence_source_system IS
    'Supports per-tenant queries filtered by source_system.';

-- Chain sequence index: used by the integrity-checker service when walking
-- the chain in sequence order and by the chain trigger lookup.
CREATE INDEX IF NOT EXISTS idx_evidence_chain_seq
    ON public.evidence_records (tenant_id, chain_sequence);

COMMENT ON INDEX public.idx_evidence_chain_seq IS
    'Sequential chain walk by the integrity-checker service and trigger lookups.';

-- Anomaly score index: partial — only rows where a score has been assigned.
-- Used by the risk-scoring service to find high-risk evidence efficiently.
CREATE INDEX IF NOT EXISTS idx_evidence_anomaly
    ON public.evidence_records (anomaly_score DESC)
    WHERE anomaly_score IS NOT NULL;

COMMENT ON INDEX public.idx_evidence_anomaly IS
    'Partial index on anomaly_score for rows where a score has been assigned. '
    'Used by the risk dashboard to surface high-risk evidence quickly.';

-- ---------------------------------------------------------------------------
-- 4c. ROW-LEVEL SECURITY ON EVIDENCE RECORDS
-- ---------------------------------------------------------------------------
ALTER TABLE public.evidence_records ENABLE ROW LEVEL SECURITY;
-- FORCE ROW LEVEL SECURITY makes the policy apply even to the table owner,
-- preventing accidental cross-tenant reads from maintenance connections.
ALTER TABLE public.evidence_records FORCE ROW LEVEL SECURITY;

-- tenant_isolation: the single RLS policy that gates all access.
-- USING controls SELECT/UPDATE/DELETE; WITH CHECK controls INSERT/UPDATE.
-- Both expressions are identical: the session GUC must match the row''s tenant_id.
-- Superusers bypass RLS; all other roles (including aegis_app) are restricted.
DROP POLICY IF EXISTS tenant_isolation ON public.evidence_records;
CREATE POLICY tenant_isolation
    ON public.evidence_records
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

COMMENT ON TABLE public.evidence_records IS
    'RLS ENABLED + FORCED. Policy ''tenant_isolation'' restricts ALL roles to rows '
    'where tenant_id matches the session GUC app.tenant_id (via get_tenant_id()). '
    'Append-only audit evidence log for the SMB pool model.';

-- ---------------------------------------------------------------------------
-- 4d. EVIDENCE CHUNKS TABLE  (RAG / semantic-search support)
--     Stores chunked text segments of evidence records for vector similarity
--     search (pgvector) and full-text search (tsvector).
--     The vector(1536) column requires the pgvector extension.  The ALTER TABLE
--     to add it is wrapped in a DO block that silently skips if pgvector is
--     absent so the migration never fails in environments without it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.evidence_chunks (
    chunk_id     UUID    NOT NULL DEFAULT gen_random_uuid(),
    evidence_id  UUID    NOT NULL,
    tenant_id    UUID    NOT NULL,
    -- Zero-based index of this chunk within the parent evidence record.
    chunk_index  INT     NOT NULL,
    -- Raw text of this chunk (typically 256–512 tokens).
    chunk_text   TEXT    NOT NULL,
    -- Vector embedding (added conditionally below via pgvector).
    -- embedding vector(1536) NULL  ← see DO block below
    -- Pre-computed tsvector for BM25 / full-text search fallback.
    tsv_content  TSVECTOR NULL,
    -- Token count for this chunk; used by the context-window budget manager.
    token_count  INT     NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT evidence_chunks_pkey
        PRIMARY KEY (chunk_id),
    CONSTRAINT evidence_chunks_evidence_fk
        FOREIGN KEY (evidence_id) REFERENCES public.evidence_records (evidence_id)
        ON DELETE CASCADE,  -- chunks are derived; delete with parent evidence
    CONSTRAINT evidence_chunks_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE  public.evidence_chunks IS
    'Chunked text segments of evidence records for RAG (vector + BM25 hybrid search). '
    'The embedding column (vector(1536)) is added conditionally when pgvector is present. '
    'RLS mirrors evidence_records; tenant_id is denormalised here to avoid a JOIN in policies.';
COMMENT ON COLUMN public.evidence_chunks.tsv_content IS
    'Pre-computed tsvector populated by a background job or trigger. '
    'Used as a BM25 fallback when pgvector is unavailable or for re-ranking.';

-- Conditionally add the pgvector embedding column.
-- If pgvector is not installed the DO block catches the error and continues.
DO $$
BEGIN
    -- Attempt to create the pgvector extension.  This is a no-op if it already
    -- exists.  If the extension is not available in this PostgreSQL installation
    -- the EXCEPTION handler will swallow the error.
    CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

    -- Add the embedding column if pgvector is now available and the column does
    -- not already exist (idempotent).
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'evidence_chunks'
          AND column_name  = 'embedding'
    ) THEN
        ALTER TABLE public.evidence_chunks
            ADD COLUMN embedding public.vector(1536) NULL;

        -- IVFFlat index for approximate nearest-neighbour search.
        -- lists=100 is a reasonable default for datasets up to ~1M vectors;
        -- rebuild with REINDEX as the dataset grows.
        CREATE INDEX IF NOT EXISTS idx_evidence_chunks_embedding
            ON public.evidence_chunks
            USING ivfflat (embedding public.vector_cosine_ops)
            WITH (lists = 100);

        RAISE NOTICE 'pgvector available — embedding column and IVFFlat index created.';
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'pgvector extension not available (%). '
                      'evidence_chunks.embedding column will NOT be created. '
                      'Install pgvector and re-run this migration to enable '
                      'vector similarity search.', SQLERRM;
END;
$$;

-- GIN index on tsv_content for full-text search.
CREATE INDEX IF NOT EXISTS idx_evidence_chunks_tsv
    ON public.evidence_chunks USING GIN (tsv_content)
    WHERE tsv_content IS NOT NULL;

-- RLS on evidence_chunks — same pattern as evidence_records.
ALTER TABLE public.evidence_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence_chunks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.evidence_chunks;
CREATE POLICY tenant_isolation
    ON public.evidence_chunks
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 5. RISK SCORES TABLE
--    Aggregated risk indices per entity (user, account, IP, etc.) computed by
--    the risk-scoring microservice.  Rows are upserted on each scoring run;
--    historical scores are preserved in a separate risk_score_history table
--    (future migration).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.risk_scores (
    score_id     UUID             NOT NULL DEFAULT gen_random_uuid(),
    tenant_id    UUID             NOT NULL,
    -- The category of entity being scored: ''user'', ''account'', ''ip_address'', etc.
    entity_type  TEXT             NULL,
    -- Opaque entity identifier within the tenant''s namespace.
    entity_id    TEXT             NULL,
    -- Normalised risk index in [0.0, 1.0].  Higher = more risky.
    risk_index   DOUBLE PRECISION NOT NULL CHECK (risk_index BETWEEN 0 AND 1),
    -- Breakdown of sub-scores by risk factor, serialised as JSONB.
    -- Example: {"velocity": 0.8, "geo_anomaly": 0.3, "privilege_abuse": 0.6}
    components   JSONB            NULL,
    computed_at  TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- Compliance framework the score is anchored to.
    framework    TEXT             NOT NULL DEFAULT 'soc2',

    CONSTRAINT risk_scores_pkey
        PRIMARY KEY (score_id),
    CONSTRAINT risk_scores_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE  public.risk_scores IS
    'Current risk indices per entity, keyed by (tenant_id, entity_type, entity_id). '
    'The risk_scoring microservice upserts rows on each scoring cycle. '
    'RLS enforces tenant isolation. Historical scores tracked in risk_score_history (future migration).';
COMMENT ON COLUMN public.risk_scores.risk_index IS
    'Normalised composite risk score in [0.0, 1.0].  Weighted average of component '
    'sub-scores defined in the components JSONB column.';
COMMENT ON COLUMN public.risk_scores.framework IS
    'Compliance framework the scoring model is calibrated against, e.g. ''soc2'', '
    '''iso27001'', ''pci_dss''.  Defaults to ''soc2'' for the initial release.';

-- RLS on risk_scores.
ALTER TABLE public.risk_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_scores FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.risk_scores;
CREATE POLICY tenant_isolation
    ON public.risk_scores
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 6a. TRIGGER FUNCTION : update_updated_at()
--     Generic before-update trigger that stamps updated_at = NOW() on any
--     table that has such a column.  Applied to the tenants table below.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_updated_at()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = public
AS $$
BEGIN
    -- Stamp the current wall-clock time as the updated_at timestamp.
    -- This function is generic and can be attached to any table with an
    -- updated_at TIMESTAMPTZ column.
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.update_updated_at() IS
    'Generic BEFORE UPDATE trigger function. Sets updated_at = NOW() on the '
    'modified row. Attach to any table that has an updated_at column.';

-- Attach to tenants table (idempotent: DROP IF EXISTS before CREATE).
DROP TRIGGER IF EXISTS trg_tenants_updated_at ON public.tenants;
CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON public.tenants
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

-- ---------------------------------------------------------------------------
-- 6b. TRIGGER FUNCTION : validate_chain_sequence()
--     Enforces the tamper-evident monotonic chain sequence on evidence_records.
--
--     Algorithm (BEFORE INSERT on evidence_records):
--       1. Lock the chain_sequence_counters row for this tenant (SELECT FOR UPDATE).
--          This serialises concurrent inserts from multiple collectors.
--       2. Verify that NEW.chain_sequence == next_seq.
--          If not, raise EXCEPTION — the insert is aborted.
--       3. Increment next_seq by 1.
--
--     The caller (collector service) is responsible for reading the current
--     next_seq before assembling the hash chain so it can set chain_sequence
--     to the correct value.  A lost race results in a retryable exception.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.validate_chain_sequence()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = public
AS $$
DECLARE
    v_expected_seq BIGINT;
BEGIN
    -- ── Step 1 ──────────────────────────────────────────────────────────────
    -- Acquire a row-level lock on the counter row for this tenant.
    -- FOR UPDATE prevents concurrent inserts from racing past each other and
    -- producing duplicate or out-of-order sequence numbers.
    SELECT next_seq
      INTO v_expected_seq
      FROM public.chain_sequence_counters
     WHERE tenant_id = NEW.tenant_id
       FOR UPDATE;

    -- ── Step 2 ──────────────────────────────────────────────────────────────
    -- If no counter row exists the tenant was not properly initialised.
    IF v_expected_seq IS NULL THEN
        RAISE EXCEPTION
            'No chain_sequence_counters row found for tenant %. '
            'Ensure the tenant is registered before inserting evidence.',
            NEW.tenant_id;
    END IF;

    -- ── Step 3 ──────────────────────────────────────────────────────────────
    -- Verify the incoming sequence number matches the expected value.
    -- A mismatch indicates either a replay attack, a double-submit, a skipped
    -- sequence (deletion of a previous record), or a race condition that the
    -- collector should handle by retrying with the correct sequence.
    IF NEW.chain_sequence <> v_expected_seq THEN
        RAISE EXCEPTION
            'Chain sequence violation for tenant %: expected %, got %. '
            'This may indicate a tampered or out-of-order insert. '
            'Collector should re-read next_seq and retry.',
            NEW.tenant_id, v_expected_seq, NEW.chain_sequence;
    END IF;

    -- ── Step 4 ──────────────────────────────────────────────────────────────
    -- Advance the counter atomically under the lock acquired in Step 1.
    UPDATE public.chain_sequence_counters
       SET next_seq = next_seq + 1
     WHERE tenant_id = NEW.tenant_id;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.validate_chain_sequence() IS
    'BEFORE INSERT trigger on evidence_records. Locks chain_sequence_counters '
    'for the tenant, verifies that NEW.chain_sequence equals next_seq, then '
    'increments next_seq. Raises EXCEPTION on any sequence violation to prevent '
    'tampered, replayed, or out-of-order inserts.';

-- Attach to evidence_records (idempotent).
DROP TRIGGER IF EXISTS trg_evidence_chain_sequence ON public.evidence_records;
CREATE TRIGGER trg_evidence_chain_sequence
    BEFORE INSERT ON public.evidence_records
    FOR EACH ROW
    EXECUTE FUNCTION public.validate_chain_sequence();

-- ---------------------------------------------------------------------------
-- 7. APPLICATION ROLE AND GRANTS
--    aegis_app is the low-privilege role used by the application''s connection
--    pool.  It receives the minimum permissions required to operate; it does
--    NOT hold superuser, CREATEROLE, or CREATEDB privileges.
--
--    Superuser / DBA connections should NOT use aegis_app; they should use
--    a separate DBA role for schema management.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- Create the role only if it does not already exist.
    -- Trying to CREATE ROLE on an existing role raises a duplicate_object error.
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'aegis_app'
    ) THEN
        CREATE ROLE aegis_app
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            LOGIN
            CONNECTION LIMIT 200;   -- reasonable cap; adjust per deployment
        RAISE NOTICE 'Role aegis_app created.';
    ELSE
        RAISE NOTICE 'Role aegis_app already exists — skipping creation.';
    END IF;
END;
$$;

-- Allow aegis_app to use objects in the public schema.
GRANT USAGE ON SCHEMA public TO aegis_app;

-- Grant DML on all tenant-facing tables.
-- evidence_records is intentionally INSERT-only for aegis_app;
-- UPDATE and DELETE are withheld to enforce the append-only contract at the
-- DB layer in addition to the application layer.
GRANT SELECT, INSERT         ON public.evidence_records         TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.evidence_chunks          TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.risk_scores              TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.tenants                  TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.chain_sequence_counters  TO aegis_app;

-- Allow aegis_app to call the helper function used in RLS policies.
GRANT EXECUTE ON FUNCTION public.get_tenant_id() TO aegis_app;

-- ---------------------------------------------------------------------------
-- END OF MIGRATION V001
-- ---------------------------------------------------------------------------
