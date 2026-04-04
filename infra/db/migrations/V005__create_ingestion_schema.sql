-- =============================================================================
-- Migration: V005__create_ingestion_schema.sql
-- Project:   Aegis 2026 – Sprint 2 – Zero-Touch Evidence Engine
-- Purpose:   Ingestion layer schema: connector registry, run audit trail,
--            watermark cursors, and canonical field-mapping catalog.
--
-- Design notes:
--   * All tenant-scoped tables use Row-Level Security (RLS) with FORCE RLS so
--     that even superuser-owned service roles must pass the policy unless they
--     explicitly SET LOCAL role = aegis_admin.
--   * Connector credentials are NEVER stored in plaintext.  The
--     config_encrypted column holds AES-256-GCM ciphertext encrypted with the
--     tenant's data-encryption key (managed by Vault's Transit engine).
--     The credential_vault_path column holds the Vault path for live OAuth
--     tokens / API keys.
--   * Circuit-breaker state is colocated on the connector row so that the
--     polling scheduler can make scheduling decisions in a single index scan.
--   * Watermarks are stored in a dedicated table (not in the run row) so that
--     a failed or partially-completed run cannot accidentally advance the
--     cursor past unconfirmed data.
--   * connector_schemas is platform-level metadata (no RLS) and is seeded at
--     migration time for the four initial connector types.
--
-- Idempotency: every DDL statement uses IF NOT EXISTS / CREATE OR REPLACE.
--              Safe to re-run; will not error on an already-applied migration.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Helper: update_updated_at()
-- Generic trigger function that stamps updated_at = NOW() on any row update.
-- Used by connector_registry and ingestion_watermarks.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


-- =============================================================================
-- TABLE: connector_registry
-- Catalog of all configured data-source integrations, one row per (tenant,
-- connector type, display name) tuple.  The scheduler reads this table to
-- decide which connectors to poll and at what interval.
-- =============================================================================
CREATE TABLE IF NOT EXISTS connector_registry (

    -- Primary key – randomly generated so that connector IDs are not
    -- enumerable and do not leak ordering information across tenants.
    connector_id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Owning tenant.  Hard FK to the central tenants table; cascading deletes
    -- are intentionally NOT configured – connector rows must be explicitly
    -- deprovisioned to preserve audit trails.
    tenant_id                   UUID        NOT NULL
                                            REFERENCES tenants(tenant_id),

    -- Machine-readable connector type used by the ingestion engine to select
    -- the correct connector implementation class.
    -- Allowed values (enforced by application layer, extensible without DDL):
    --   'aws_cloudtrail'             AWS CloudTrail management & data events
    --   'google_workspace_admin'     Google Workspace Admin SDK activity logs
    --   'plaid_transactions'         Plaid Transactions API (banking feeds)
    --   'quickbooks_ledger'          QuickBooks Online General Ledger
    connector_type              TEXT        NOT NULL,

    -- Human-readable label shown in the UI.  Allows a tenant to configure
    -- multiple instances of the same connector type (e.g. two AWS accounts).
    display_name                TEXT        NOT NULL,

    -- AES-256-GCM ciphertext of the connector configuration JSON.
    -- Encrypted with the tenant's Transit key via Vault:
    --   POST /v1/transit/encrypt/<tenant_id>
    -- The application layer decrypts at runtime; plaintext MUST NOT be logged.
    config_encrypted            BYTEA       NOT NULL,

    -- Vault KV-v2 path for live OAuth access tokens / API keys, e.g.:
    --   secret/data/tenants/<tenant_id>/connectors/<connector_id>/oauth_token
    -- NULL when credentials are fully encoded in config_encrypted.
    credential_vault_path       TEXT,

    -- Whether the connector is enabled for scheduled polling.
    -- Set to FALSE to pause ingestion without deleting the configuration.
    is_active                   BOOLEAN     NOT NULL DEFAULT TRUE,

    -- Nominal polling interval in seconds (default 3600 = 1 hour).
    -- The scheduler adds polling_jitter_seconds to avoid thundering-herd
    -- across connectors that share the same interval.
    polling_interval_seconds    INT         NOT NULL DEFAULT 3600,

    -- Jitter offset (seconds) added to polling_interval_seconds per run.
    -- Set at connector creation time to a deterministic hash-derived value
    -- (e.g. hashtext(connector_id::text) % 300) so jitter is stable across
    -- restarts but varies across connectors.
    polling_jitter_seconds      INT         NOT NULL DEFAULT 0,

    -- Timestamps of the last successful poll and any most-recent error.
    -- Used by the health-check dashboard and circuit-breaker logic.
    last_successful_poll_at     TIMESTAMPTZ,
    last_error                  TEXT,
    last_error_at               TIMESTAMPTZ,

    -- Circuit-breaker state machine:
    --   closed     – normal operation, polls proceed
    --   half_open  – one trial probe allowed; resets to closed on success
    --   open       – connector is suppressed; no polls attempted
    -- The scheduler transitions states based on consecutive failure counts
    -- and a configurable threshold per connector type.
    circuit_breaker_state       TEXT        NOT NULL DEFAULT 'closed'
                                            CHECK (circuit_breaker_state IN ('closed','half_open','open')),

    -- Consecutive failure count since the last successful poll.
    -- Reset to 0 on any successful run.
    circuit_breaker_failures    INT         NOT NULL DEFAULT 0,

    -- Timestamp when the circuit breaker last opened (for cooldown logic).
    circuit_breaker_opened_at   TIMESTAMPTZ,

    -- Audit timestamps.
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- A tenant cannot have two connectors with the same type+name.
    -- Different display_names allow multiple instances of the same type.
    CONSTRAINT uq_connector_registry_tenant_type_name
        UNIQUE (tenant_id, connector_type, display_name)
);

-- ---------------------------------------------------------------------------
-- Row-Level Security: connector_registry
-- The policy exposes only rows belonging to the tenant identified by the
-- current session-level setting `app.current_tenant_id`.
-- Service roles set this via: SET LOCAL app.current_tenant_id = '<uuid>';
-- ---------------------------------------------------------------------------
ALTER TABLE connector_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE connector_registry FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'connector_registry'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON connector_registry
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Trigger: keep updated_at current on connector_registry
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_connector_registry_updated_at'
    ) THEN
        CREATE TRIGGER trg_connector_registry_updated_at
            BEFORE UPDATE ON connector_registry
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Indexes: connector_registry
-- ---------------------------------------------------------------------------

-- Primary scheduling query: "give me all active, non-open connectors for
-- this tenant that are due for their next poll."
CREATE INDEX IF NOT EXISTS idx_connector_registry_tenant_active_cb
    ON connector_registry (tenant_id, is_active, circuit_breaker_state);

-- Connector-type lookup: used by the health dashboard and schema resolution.
CREATE INDEX IF NOT EXISTS idx_connector_registry_tenant_type
    ON connector_registry (tenant_id, connector_type);


-- =============================================================================
-- TABLE: ingestion_runs
-- Immutable audit trail of every poll execution.  One row is inserted when a
-- run starts and updated in-place as it progresses.  Rows are never deleted
-- (the table is effectively append-only after a run completes).
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingestion_runs (

    run_id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Parent connector.
    connector_id            UUID        NOT NULL
                                        REFERENCES connector_registry(connector_id),

    -- Denormalised for RLS without a join cost.
    tenant_id               UUID        NOT NULL,

    -- Wall-clock times.  completed_at is NULL while the run is in progress.
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,

    -- Run lifecycle state.
    --   running       – in progress
    --   success       – completed normally; records_stored reflects actual count
    --   failed        – terminated with an error; see error_message
    --   skipped       – scheduler skipped this poll (e.g. prior run still in flight)
    --   circuit_open  – poll suppressed by open circuit breaker
    status                  TEXT        NOT NULL DEFAULT 'running'
                                        CHECK (status IN (
                                            'running','success','failed',
                                            'skipped','circuit_open'
                                        )),

    -- Volume counters (updated at end of run).
    records_fetched         INT         NOT NULL DEFAULT 0,
    records_stored          INT         NOT NULL DEFAULT 0,
    bytes_ingested          BIGINT      NOT NULL DEFAULT 0,

    -- Error detail retained for alerting and postmortems.
    -- error_traceback holds the full Python/Go stack trace (truncated to 64 KB).
    error_message           TEXT,
    error_traceback         TEXT,

    -- Incremental fetch window.
    -- watermark_from  – earliest event timestamp fetched in this run
    -- watermark_to    – latest  event timestamp fetched in this run
    -- next_watermark  – the cursor value written to ingestion_watermarks on
    --                   successful completion; NULL until run succeeds
    watermark_from          TIMESTAMPTZ,
    watermark_to            TIMESTAMPTZ,
    next_watermark          TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Row-Level Security: ingestion_runs
-- ---------------------------------------------------------------------------
ALTER TABLE ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_runs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'ingestion_runs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON ingestion_runs
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Indexes: ingestion_runs
-- ---------------------------------------------------------------------------

-- Per-connector run history ordered most-recent-first (primary operational query).
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_connector_started
    ON ingestion_runs (connector_id, started_at DESC);

-- Cross-connector status dashboard query.
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_tenant_status_started
    ON ingestion_runs (tenant_id, status, started_at DESC);

-- Partial index: fast lookup of the most recent successful run per connector
-- (used to compute next_watermark without scanning failed rows).
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_connector_success
    ON ingestion_runs (connector_id, completed_at DESC)
    WHERE status = 'success';


-- =============================================================================
-- TABLE: ingestion_watermarks
-- Persistent cursor state, one row per connector.  Survives process/pod
-- restarts.  The watermark is only advanced after a run fully succeeds and
-- all records are durably stored (two-phase commit pattern: write records
-- first, then UPDATE this table, then commit).
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingestion_watermarks (

    watermark_id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- One watermark row per connector (enforced by the UNIQUE constraint).
    connector_id            UUID        NOT NULL UNIQUE
                                        REFERENCES connector_registry(connector_id),

    -- Denormalised for RLS.
    tenant_id               UUID        NOT NULL,

    -- Wall-clock timestamp of the most-recently ingested event.
    -- The next poll fetches events with timestamp > last_ingested_at.
    last_ingested_at        TIMESTAMPTZ NOT NULL,

    -- Connector-specific opaque cursor (JSONB for flexibility).
    -- Examples:
    --   AWS CloudTrail:     { "nextToken": "AQICAH...", "region": "us-east-1" }
    --   QuickBooks Online:  { "position": 1042 }
    --   Plaid:              { "cursor": "CAESIGx..." }
    -- NULL for connectors that use pure timestamp-based pagination.
    last_ingested_cursor    JSONB,

    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Row-Level Security: ingestion_watermarks
-- ---------------------------------------------------------------------------
ALTER TABLE ingestion_watermarks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_watermarks FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'ingestion_watermarks'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON ingestion_watermarks
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Trigger: keep updated_at current on ingestion_watermarks
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ingestion_watermarks_updated_at'
    ) THEN
        CREATE TRIGGER trg_ingestion_watermarks_updated_at
            BEFORE UPDATE ON ingestion_watermarks
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Indexes: ingestion_watermarks
-- The UNIQUE constraint on connector_id already creates a B-tree index that
-- covers the primary lookup (fetch watermark for a connector).  We add a
-- separate index on tenant_id for bulk-reset operations.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ingestion_watermarks_tenant
    ON ingestion_watermarks (tenant_id);


-- =============================================================================
-- TABLE: connector_schemas
-- Registry of canonical field mappings per connector type.  Platform-level
-- metadata (not tenant-scoped) — no RLS required.
--
-- field_mappings schema (JSONB):
-- {
--   "version": "1.0.0",
--   "mappings": [
--     {
--       "source_field":    "eventTime",          -- raw API field name
--       "canonical_field": "occurred_at",         -- aegis canonical field
--       "type":            "timestamptz",
--       "required":        true,
--       "transform":       "iso8601_to_timestamptz"
--     },
--     ...
--   ]
-- }
-- =============================================================================
CREATE TABLE IF NOT EXISTS connector_schemas (

    schema_id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- One schema per connector type (enforced; multiple versions tracked via
    -- the version column – when a connector's API changes, insert a new row
    -- with a bumped version and update the connector_registry rows).
    connector_type          TEXT        NOT NULL UNIQUE,

    -- Semantic version of this schema definition.
    version                 TEXT        NOT NULL DEFAULT '1.0.0',

    -- Full field-mapping specification (see structure above).
    field_mappings          JSONB       NOT NULL,

    -- Optional: a redacted/anonymised sample payload from the real API.
    -- Used by the ingestion engine's self-test harness to validate the mapping
    -- without making a live API call.
    sample_payload          JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for lookup by connector type (the UNIQUE constraint covers equality;
-- this explicit index documents intent and enables covering scans).
CREATE INDEX IF NOT EXISTS idx_connector_schemas_type
    ON connector_schemas (connector_type);


-- =============================================================================
-- SEED DATA: connector_schemas
-- Canonical field mappings for the four initial connector types.
-- ON CONFLICT DO NOTHING makes these statements idempotent.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- aws_cloudtrail
-- ---------------------------------------------------------------------------
INSERT INTO connector_schemas (connector_type, version, field_mappings, sample_payload)
VALUES (
    'aws_cloudtrail',
    '1.0.0',
    '{
        "version": "1.0.0",
        "mappings": [
            {
                "source_field":    "eventTime",
                "canonical_field": "occurred_at",
                "type":            "timestamptz",
                "required":        true,
                "transform":       "iso8601_to_timestamptz"
            },
            {
                "source_field":    "eventID",
                "canonical_field": "source_event_id",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "eventName",
                "canonical_field": "action",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "eventSource",
                "canonical_field": "service",
                "type":            "text",
                "required":        true,
                "transform":       "strip_amazonaws_suffix"
            },
            {
                "source_field":    "awsRegion",
                "canonical_field": "region",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "userIdentity.arn",
                "canonical_field": "actor_id",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "userIdentity.accountId",
                "canonical_field": "account_id",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "sourceIPAddress",
                "canonical_field": "source_ip",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "requestParameters",
                "canonical_field": "request_payload",
                "type":            "jsonb",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "responseElements",
                "canonical_field": "response_payload",
                "type":            "jsonb",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "errorCode",
                "canonical_field": "error_code",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            }
        ]
    }'::JSONB,
    '{
        "eventVersion":  "1.09",
        "userIdentity":  { "type": "IAMUser", "accountId": "123456789012", "arn": "arn:aws:iam::123456789012:user/alice" },
        "eventTime":     "2026-03-01T10:23:45Z",
        "eventSource":   "s3.amazonaws.com",
        "eventName":     "GetObject",
        "awsRegion":     "us-east-1",
        "sourceIPAddress":"203.0.113.1",
        "requestParameters": { "bucketName": "my-bucket", "key": "sensitive/report.pdf" },
        "responseElements": null,
        "eventID":       "550e8400-e29b-41d4-a716-446655440000"
    }'::JSONB
)
ON CONFLICT (connector_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- google_workspace_admin
-- ---------------------------------------------------------------------------
INSERT INTO connector_schemas (connector_type, version, field_mappings, sample_payload)
VALUES (
    'google_workspace_admin',
    '1.0.0',
    '{
        "version": "1.0.0",
        "mappings": [
            {
                "source_field":    "id.time",
                "canonical_field": "occurred_at",
                "type":            "timestamptz",
                "required":        true,
                "transform":       "iso8601_to_timestamptz"
            },
            {
                "source_field":    "id.uniqueQualifier",
                "canonical_field": "source_event_id",
                "type":            "text",
                "required":        true,
                "transform":       "int64_to_text"
            },
            {
                "source_field":    "events[0].name",
                "canonical_field": "action",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "id.applicationName",
                "canonical_field": "service",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "actor.email",
                "canonical_field": "actor_id",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "ipAddress",
                "canonical_field": "source_ip",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "events[0].parameters",
                "canonical_field": "request_payload",
                "type":            "jsonb",
                "required":        false,
                "transform":       "gws_params_to_jsonb"
            }
        ]
    }'::JSONB,
    '{
        "kind":    "admin#reports#activity",
        "id":      { "time": "2026-03-01T10:23:45.000Z", "uniqueQualifier": "7654321098765432101", "applicationName": "login" },
        "actor":   { "email": "alice@example.com", "profileId": "123456789" },
        "ipAddress":"203.0.113.2",
        "events":  [{ "type": "login", "name": "login_success", "parameters": [] }]
    }'::JSONB
)
ON CONFLICT (connector_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- plaid_transactions
-- ---------------------------------------------------------------------------
INSERT INTO connector_schemas (connector_type, version, field_mappings, sample_payload)
VALUES (
    'plaid_transactions',
    '1.0.0',
    '{
        "version": "1.0.0",
        "mappings": [
            {
                "source_field":    "date",
                "canonical_field": "occurred_at",
                "type":            "timestamptz",
                "required":        true,
                "transform":       "date_to_timestamptz_utc"
            },
            {
                "source_field":    "transaction_id",
                "canonical_field": "source_event_id",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "transaction_type",
                "canonical_field": "action",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "account_id",
                "canonical_field": "account_id",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "amount",
                "canonical_field": "amount_cents",
                "type":            "bigint",
                "required":        true,
                "transform":       "dollars_to_cents"
            },
            {
                "source_field":    "iso_currency_code",
                "canonical_field": "currency_code",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "name",
                "canonical_field": "description",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "merchant_name",
                "canonical_field": "merchant_name",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "category",
                "canonical_field": "category_tags",
                "type":            "jsonb",
                "required":        false,
                "transform":       "array_to_jsonb"
            },
            {
                "source_field":    "pending",
                "canonical_field": "is_pending",
                "type":            "boolean",
                "required":        true,
                "transform":       "identity"
            }
        ]
    }'::JSONB,
    '{
        "transaction_id":   "lPNjeW1nR6CDn5okmGQ6hEpMo4lLNoSrzqDje",
        "account_id":       "BxBXxLj1m4HMXBm9WZZmCWVbPjX16EHwv99vp",
        "amount":           28.50,
        "iso_currency_code":"USD",
        "date":             "2026-03-01",
        "name":             "AMAZON.COM",
        "merchant_name":    "Amazon",
        "transaction_type": "place",
        "pending":          false,
        "category":         ["Shops", "Online Marketplaces"]
    }'::JSONB
)
ON CONFLICT (connector_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- quickbooks_ledger
-- ---------------------------------------------------------------------------
INSERT INTO connector_schemas (connector_type, version, field_mappings, sample_payload)
VALUES (
    'quickbooks_ledger',
    '1.0.0',
    '{
        "version": "1.0.0",
        "mappings": [
            {
                "source_field":    "MetaData.CreateTime",
                "canonical_field": "occurred_at",
                "type":            "timestamptz",
                "required":        true,
                "transform":       "iso8601_to_timestamptz"
            },
            {
                "source_field":    "Id",
                "canonical_field": "source_event_id",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "TxnDate",
                "canonical_field": "transaction_date",
                "type":            "date",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "DocNumber",
                "canonical_field": "document_number",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "TotalAmt",
                "canonical_field": "amount_cents",
                "type":            "bigint",
                "required":        true,
                "transform":       "dollars_to_cents"
            },
            {
                "source_field":    "CurrencyRef.value",
                "canonical_field": "currency_code",
                "type":            "text",
                "required":        true,
                "transform":       "identity"
            },
            {
                "source_field":    "Line",
                "canonical_field": "line_items",
                "type":            "jsonb",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "PrivateNote",
                "canonical_field": "memo",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            },
            {
                "source_field":    "CustomerRef.name",
                "canonical_field": "counterparty_name",
                "type":            "text",
                "required":        false,
                "transform":       "identity"
            }
        ]
    }'::JSONB,
    '{
        "Id":         "123",
        "TxnDate":    "2026-03-01",
        "DocNumber":  "INV-0042",
        "TotalAmt":   1500.00,
        "CurrencyRef":{ "value": "USD", "name": "United States Dollar" },
        "CustomerRef":{ "value": "87", "name": "Acme Corp" },
        "MetaData":   { "CreateTime": "2026-03-01T14:00:00-08:00", "LastUpdatedTime": "2026-03-01T14:00:00-08:00" },
        "Line":       [{ "Amount": 1500.00, "DetailType": "SalesItemLineDetail" }],
        "PrivateNote":"Q1 consulting retainer"
    }'::JSONB
)
ON CONFLICT (connector_type) DO NOTHING;

-- =============================================================================
-- END V005__create_ingestion_schema.sql
-- =============================================================================
