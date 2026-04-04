-- =============================================================================
-- V011__create_maestro_schema.sql
-- Project: Aegis 2026 – Sprint 7 – MAESTRO Security Hardening
--
-- Purpose:
--   Creates the MAESTRO security schema: prompt injection logging, rate-limit
--   event tracking, post-quantum public key storage, and an immutable security
--   audit log.
--
-- Design:
--   * Fully idempotent — safe to run multiple times (CREATE ... IF NOT EXISTS,
--     DO $$ ... $$ guards on RLS policies checking pg_policies).
--   * RLS enforced on all tables using current_setting('app.tenant_id').
--   * security_audit_log is append-only: aegis_app receives INSERT, SELECT
--     only — no UPDATE or DELETE — to preserve an immutable audit trail.
--
-- Tables:
--   prompt_injection_logs  – per-tenant, INSERT-heavy injection detection log
--   rate_limit_events      – per-tenant, high-write rate-limit event records
--   pq_public_keys         – per-tenant post-quantum public key store
--   security_audit_log     – per-tenant immutable security event audit trail
--
-- Roles assumed to exist: aegis_app
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. prompt_injection_logs
--    Records every evaluated request alongside its injection score and the
--    action taken.  Raw query text is never stored; only the SHA-256 hash.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompt_injection_logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    user_id         UUID,
    query_hash      BYTEA       NOT NULL,         -- SHA-256 of original query (never store raw query)
    injection_score NUMERIC(4,3) NOT NULL,         -- 0.000 to 1.000
    pattern_hits    TEXT[]      NOT NULL DEFAULT '{}',  -- which patterns matched
    action_taken    TEXT        NOT NULL CHECK (action_taken IN ('allowed', 'blocked', 'flagged')),
    service         TEXT        NOT NULL,          -- which service detected it (e.g. 'rag-pipeline')
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  prompt_injection_logs                IS 'Per-request prompt injection evaluation log; raw query text is never persisted.';
COMMENT ON COLUMN prompt_injection_logs.query_hash     IS 'Raw 32-byte SHA-256 digest of the original query string.';
COMMENT ON COLUMN prompt_injection_logs.injection_score IS 'Model confidence score in [0.000, 1.000] that the input is a prompt injection attempt.';
COMMENT ON COLUMN prompt_injection_logs.pattern_hits   IS 'Array of pattern identifiers that matched during evaluation.';
COMMENT ON COLUMN prompt_injection_logs.action_taken   IS 'Disposition applied: allowed, blocked, or flagged for review.';
COMMENT ON COLUMN prompt_injection_logs.service        IS 'Identifier of the service that performed detection, e.g. rag-pipeline.';

-- Enable RLS.
ALTER TABLE prompt_injection_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_injection_logs FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'prompt_injection_logs'
          AND policyname = 'prompt_injection_logs_tenant_isolation'
    ) THEN
        CREATE POLICY prompt_injection_logs_tenant_isolation
            ON prompt_injection_logs
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT INSERT, SELECT ON prompt_injection_logs TO aegis_app;

-- Primary access pattern: recent events per tenant.
CREATE INDEX IF NOT EXISTS idx_prompt_injection_logs_tenant_created
    ON prompt_injection_logs (tenant_id, created_at DESC);

-- Partial index for blocked-event analysis (most actionable subset).
CREATE INDEX IF NOT EXISTS idx_prompt_injection_logs_blocked_score
    ON prompt_injection_logs (tenant_id, injection_score)
    WHERE action_taken = 'blocked';

-- ---------------------------------------------------------------------------
-- 2. rate_limit_events
--    Records every rate-limit threshold breach.  High insert volume expected;
--    intentionally narrow — no large TEXT or JSONB columns.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    endpoint        TEXT        NOT NULL,
    limit_type      TEXT        NOT NULL CHECK (limit_type IN ('per_tenant', 'per_user', 'global')),
    window_start    TIMESTAMPTZ NOT NULL,
    request_count   INTEGER     NOT NULL,
    limit_value     INTEGER     NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  rate_limit_events              IS 'Rate-limit breach events; one row per window evaluation that exceeded the configured limit.';
COMMENT ON COLUMN rate_limit_events.endpoint     IS 'API endpoint path that was rate-limited.';
COMMENT ON COLUMN rate_limit_events.limit_type   IS 'Scope of the limit: per_tenant, per_user, or global.';
COMMENT ON COLUMN rate_limit_events.window_start IS 'Start of the counting window for this event.';
COMMENT ON COLUMN rate_limit_events.request_count IS 'Observed request count within the window.';
COMMENT ON COLUMN rate_limit_events.limit_value  IS 'Configured limit threshold that was breached.';

-- Enable RLS.
ALTER TABLE rate_limit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE rate_limit_events FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'rate_limit_events'
          AND policyname = 'rate_limit_events_tenant_isolation'
    ) THEN
        CREATE POLICY rate_limit_events_tenant_isolation
            ON rate_limit_events
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT INSERT, SELECT ON rate_limit_events TO aegis_app;

-- Covers endpoint-level window queries.
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_tenant_endpoint_window
    ON rate_limit_events (tenant_id, endpoint, window_start DESC);

-- ---------------------------------------------------------------------------
-- 3. pq_public_keys
--    Stores post-quantum public keys (Kyber and Dilithium) per tenant.
--    Supports key rotation via is_active flag and expires_at timestamp.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pq_public_keys (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL,
    key_id           TEXT        NOT NULL,         -- human-readable key identifier
    algorithm        TEXT        NOT NULL CHECK (algorithm IN ('Kyber768', 'Dilithium3', 'Kyber1024', 'Dilithium5')),
    public_key_bytes BYTEA       NOT NULL,
    fingerprint      BYTEA       NOT NULL,          -- SHA-256 of public_key_bytes
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ,

    UNIQUE (tenant_id, key_id, algorithm)
);

COMMENT ON TABLE  pq_public_keys                  IS 'Post-quantum public keys (Kyber / Dilithium) stored per tenant; supports rotation via is_active.';
COMMENT ON COLUMN pq_public_keys.key_id           IS 'Human-readable key identifier, unique within (tenant_id, algorithm).';
COMMENT ON COLUMN pq_public_keys.algorithm        IS 'PQ algorithm: Kyber768, Kyber1024 (KEM), Dilithium3, Dilithium5 (signature).';
COMMENT ON COLUMN pq_public_keys.public_key_bytes IS 'Raw public key bytes in the algorithm-native encoding.';
COMMENT ON COLUMN pq_public_keys.fingerprint      IS 'Raw 32-byte SHA-256 digest of public_key_bytes for quick equality checks.';
COMMENT ON COLUMN pq_public_keys.is_active        IS 'False once the key has been rotated out; superseded keys are retained for verification.';
COMMENT ON COLUMN pq_public_keys.expires_at       IS 'Optional wall-clock expiry; NULL means the key has no hard expiry.';

-- Enable RLS.
ALTER TABLE pq_public_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE pq_public_keys FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'pq_public_keys'
          AND policyname = 'pq_public_keys_tenant_isolation'
    ) THEN
        CREATE POLICY pq_public_keys_tenant_isolation
            ON pq_public_keys
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON pq_public_keys TO aegis_app;

-- Partial index: only active keys are queried on the hot path.
CREATE INDEX IF NOT EXISTS idx_pq_public_keys_active
    ON pq_public_keys (tenant_id, algorithm)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- 4. security_audit_log
--    Immutable, append-only audit trail of security-relevant events.
--    aegis_app is granted INSERT and SELECT only — no UPDATE or DELETE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS security_audit_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL,
    event_type  TEXT        NOT NULL CHECK (event_type IN (
                    'prompt_injection_blocked',
                    'rate_limit_exceeded',
                    'cross_tenant_attempt',
                    'pq_key_rotation',
                    'fido2_ceremony_failed',
                    'fido2_ceremony_success',
                    'suspicious_access_pattern'
                )),
    severity    TEXT        NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    actor_id    UUID,
    details     JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  security_audit_log            IS 'Immutable security event audit trail; INSERT and SELECT only — no UPDATE or DELETE permitted.';
COMMENT ON COLUMN security_audit_log.event_type IS 'Enumerated security event category.';
COMMENT ON COLUMN security_audit_log.severity   IS 'Event severity: info, warning, or critical.';
COMMENT ON COLUMN security_audit_log.actor_id   IS 'UUID of the user or service principal that triggered the event; NULL for system-originated events.';
COMMENT ON COLUMN security_audit_log.details    IS 'Structured JSON payload with event-specific context (IPs, endpoints, key IDs, etc.).';

-- Enable RLS.
ALTER TABLE security_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_audit_log FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'security_audit_log'
          AND policyname = 'security_audit_log_tenant_isolation'
    ) THEN
        CREATE POLICY security_audit_log_tenant_isolation
            ON security_audit_log
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable audit trail.
GRANT INSERT, SELECT ON security_audit_log TO aegis_app;

-- Covers per-tenant event-type queries (e.g. "all injection blocks this week").
CREATE INDEX IF NOT EXISTS idx_security_audit_log_tenant_event_created
    ON security_audit_log (tenant_id, event_type, created_at DESC);

-- Partial index for rapid critical-severity alerting queries.
CREATE INDEX IF NOT EXISTS idx_security_audit_log_critical
    ON security_audit_log (tenant_id, created_at DESC)
    WHERE severity = 'critical';

-- ---------------------------------------------------------------------------
-- Grants summary
-- Re-grant read access on xbrl_taxonomies after any potential ownership change.
-- ---------------------------------------------------------------------------
GRANT SELECT ON xbrl_taxonomies TO aegis_app;
