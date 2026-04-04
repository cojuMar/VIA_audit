-- =============================================================================
-- Project Aegis 2026 — Sprint 1
-- Migration : V004__create_pam_audit_tables.sql
-- Purpose   : Privileged Access Management (PAM) broker tables and the
--             immutable audit trail infrastructure.
--
-- Design notes
-- ────────────
--   • access_requests      — JIT access request lifecycle (pending → approved/
--                            denied → expired/revoked).  No RLS; the PAM
--                            broker service owns access control here because
--                            the approver and the requestor may be in different
--                            tenants (platform-level cross-tenant workflow).
--
--   • pam_audit_log        — Immutable, append-only log of every PAM action
--                            (credential issued, query executed, session ended,
--                            etc.).  Immutability is enforced by a trigger that
--                            raises EXCEPTION on UPDATE or DELETE.  Shares the
--                            chain_hash / chain_sequence tamper-evident pattern
--                            from evidence_records, but uses a global (not per-
--                            tenant) sequence counter because PAM is platform-
--                            level.
--
--   • chain_sequence_counters_pam — Singleton global counter for pam_audit_log
--                            sequences.  Uses a single row (id = 1).
--
--   • hitl_queue           — Human-In-The-Loop review queue for AI-generated
--                            audit findings that fall below the faithfulness/
--                            groundedness threshold.  Findings awaiting review
--                            are held here until a qualified reviewer approves,
--                            edits, or rejects them.  RLS + FORCE RLS to
--                            prevent cross-tenant leakage.
--
-- Idempotency
-- ───────────
--   CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS,
--   DROP POLICY IF EXISTS / CREATE POLICY, DROP TRIGGER IF EXISTS / CREATE TRIGGER.
--
-- Prerequisites
-- ─────────────
--   V001 (tenants, get_tenant_id, aegis_app role)
--   V003 (users table for FK references)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. ACCESS REQUESTS TABLE
--    Tracks the full lifecycle of a JIT privileged-access request:
--      PENDING  → requestor submits justification
--      APPROVED → approver (human or auto-policy) grants access; Vault lease
--                 is created; credential path is recorded
--      DENIED   → approver rejects
--      EXPIRED  → approved but never used within the approved window
--      REVOKED  → access was granted but then explicitly revoked (incident
--                 response, session anomaly, etc.)
--
--    No RLS — the PAM broker service is a privileged platform component that
--    operates across tenant boundaries (e.g. a platform admin approving a
--    request from an SMB tenant).  Application-level AuthZ in the broker
--    service enforces access control on this table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.access_requests (
    request_id               UUID        NOT NULL DEFAULT gen_random_uuid(),
    requesting_user_id       UUID        NOT NULL,
    tenant_id                UUID        NOT NULL,
    -- Category of privileged resource being requested.
    -- database_readonly : read replica credential
    -- database_infra    : full infra credential (DBA-level)
    -- api_readonly      : read-only API token for an upstream service
    -- break_glass       : emergency full-access override; highest scrutiny
    resource_type            TEXT        NOT NULL
                                CHECK (resource_type IN (
                                    'database_readonly',
                                    'database_infra',
                                    'api_readonly',
                                    'break_glass'
                                )),
    -- Free-text justification required for all access types.
    -- Minimum length enforced at the application layer.
    justification            TEXT        NOT NULL,
    -- Optional link to an ITSM ticket (Jira, ServiceNow, etc.).
    itsm_ticket_id           TEXT        NULL,
    -- Requested access window in seconds.  Capped by policy per resource_type.
    requested_duration_seconds INT       NOT NULL,
    -- Actual approved duration may be shorter than requested (policy cap).
    -- NULL until a decision is made.
    approved_duration_seconds INT        NULL,
    -- Lifecycle status.
    status                   TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending',
                                    'approved',
                                    'denied',
                                    'expired',
                                    'revoked'
                                )),
    requested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at               TIMESTAMPTZ NULL,   -- NULL while pending
    -- Computed as decided_at + approved_duration_seconds * INTERVAL '1 second'.
    expires_at               TIMESTAMPTZ NULL,
    revoked_at               TIMESTAMPTZ NULL,
    -- Approver identity; NULL for policy-based auto-approvals.
    approver_user_id         UUID        NULL,
    -- FIDO2 assertion ID from the approver''s MFA challenge.
    -- Required for break_glass resource_type; optional for others.
    approver_fido2_assertion_id TEXT     NULL,
    -- HashiCorp Vault lease ID for the dynamic credential that was issued.
    vault_lease_id           TEXT        NULL,
    -- Vault secret path where the credential was written.
    vault_credential_path    TEXT        NULL,
    -- JSONB blob with geolocation context: {country, city, lat, lon, isp}.
    -- Populated from the IP reputation / GeoIP service at request time.
    geo_context              JSONB       NULL,
    -- Source IP of the requestor.
    ip_address               INET        NULL,

    CONSTRAINT access_requests_pkey
        PRIMARY KEY (request_id),
    CONSTRAINT access_requests_user_fk
        FOREIGN KEY (requesting_user_id) REFERENCES public.users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT access_requests_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT access_requests_approver_fk
        FOREIGN KEY (approver_user_id) REFERENCES public.users (user_id)
        ON DELETE SET NULL
);

COMMENT ON TABLE  public.access_requests IS
    'JIT privileged-access request lifecycle table. No RLS — the PAM broker '
    'service manages access control directly because approval workflows cross '
    'tenant boundaries. Tracks request → approval/denial → expiry/revocation.';
COMMENT ON COLUMN public.access_requests.resource_type IS
    'database_readonly | database_infra | api_readonly | break_glass. '
    'break_glass requires mandatory FIDO2 MFA from the approver and creates '
    'a pam_audit_log entry for every query executed.';
COMMENT ON COLUMN public.access_requests.vault_lease_id IS
    'HashiCorp Vault dynamic secret lease ID. Used by the broker to revoke '
    'the credential when the session expires or is revoked.';
COMMENT ON COLUMN public.access_requests.geo_context IS
    'GeoIP context at request time: {country, city, lat, lon, asn, isp}. '
    'Used by the anomaly detector to flag unusual access locations.';

-- ---------------------------------------------------------------------------
-- 2. PAM AUDIT LOG — CHAIN SEQUENCE COUNTER (singleton / global)
--    Unlike evidence_records (per-tenant sequences), the pam_audit_log uses a
--    single global sequence.  This means any gap in the global sequence is
--    detectable regardless of which tenant''s activity is being audited.
--    id is a fixed integer PK (always 1); the UNIQUE constraint plus
--    DEFAULT 1 ensures only one row can ever exist.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chain_sequence_counters_pam (
    -- Singleton row sentinel.  id is always 1.
    id        INT    NOT NULL DEFAULT 1,
    next_seq  BIGINT NOT NULL DEFAULT 1,

    CONSTRAINT chain_seq_ctr_pam_pkey
        PRIMARY KEY (id),
    -- Belt-and-suspenders: the UNIQUE constraint on id prevents a second row.
    CONSTRAINT chain_seq_ctr_pam_singleton
        UNIQUE (id),
    -- Ensure the sentinel value is never changed.
    CONSTRAINT chain_seq_ctr_pam_id_check
        CHECK (id = 1)
);

-- Seed the singleton row.  ON CONFLICT DO NOTHING is idempotent.
INSERT INTO public.chain_sequence_counters_pam (id, next_seq)
VALUES (1, 1)
ON CONFLICT DO NOTHING;

COMMENT ON TABLE  public.chain_sequence_counters_pam IS
    'Global singleton counter for pam_audit_log.chain_sequence. '
    'Always contains exactly one row (id = 1). The prevent_pam_log_modification '
    'trigger on pam_audit_log locks this row before each insert and increments '
    'next_seq atomically. A gap in chain_sequence indicates tampering.';

-- ---------------------------------------------------------------------------
-- 3. PAM AUDIT LOG TABLE — APPEND-ONLY, IMMUTABLE
--    Records every PAM broker action: access granted, query executed, session
--    terminated, break-glass triggered, etc.  The chain_hash / chain_sequence
--    columns provide tamper evidence (same algorithm as evidence_records but
--    using the global PAM counter).
--
--    IMMUTABILITY is enforced by the prevent_pam_log_modification trigger
--    defined in section 4 below.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pam_audit_log (
    log_id                UUID        NOT NULL DEFAULT gen_random_uuid(),
    -- Links back to the access_request that authorised this action.
    -- NULL for system-generated entries (e.g. automatic session expiry).
    request_id            UUID        NULL,
    -- The user who performed the action (may differ from the requestor,
    -- e.g. a platform admin acting on behalf of a tenant).
    actor_user_id         UUID        NULL,
    -- Snapshot of the actor''s role at the time of the action.
    -- Stored as a text snapshot rather than a FK because roles can change
    -- and the audit trail must reflect the historical state.
    actor_role            TEXT        NULL,
    -- Short action verb, e.g. 'credential_issued', 'query_executed',
    -- 'session_terminated', 'break_glass_activated', 'access_denied'.
    action                TEXT        NOT NULL,
    -- The specific resource acted upon, e.g. 'db:prod-replica:us-east-1'.
    resource              TEXT        NULL,
    -- For database actions: the full SQL query text.  May be NULL for
    -- non-query actions.  Truncated to 10 000 chars by the broker if longer.
    query_text            TEXT        NULL,
    -- Execution duration for query actions.
    duration_ms           INT         NULL,
    -- HTTP or DB status code, e.g. 200, 403, 500, 0 (for non-HTTP actions).
    status_code           INT         NULL,
    -- Source IP at the time of the action.
    ip_address            INET        NULL,
    logged_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Tamper-evident chain hash (HMAC-SHA256 over prev_hash || log fields).
    -- Computed by the broker before insert; verified by integrity-checker.
    chain_hash            BYTEA       NOT NULL,
    -- Global monotonic sequence (from chain_sequence_counters_pam).
    chain_sequence        BIGINT      NOT NULL,
    -- URI of the session recording in object storage (S3 / GCS), if captured.
    -- Format: s3://aegis-recordings/<tenant_id>/<request_id>/<timestamp>.cast
    session_recording_uri TEXT        NULL,

    CONSTRAINT pam_audit_log_pkey
        PRIMARY KEY (log_id),
    CONSTRAINT pam_audit_log_request_fk
        FOREIGN KEY (request_id) REFERENCES public.access_requests (request_id)
        ON DELETE RESTRICT   -- never cascade-delete audit entries
);

COMMENT ON TABLE  public.pam_audit_log IS
    'Immutable, append-only PAM audit trail. UPDATE and DELETE are blocked by '
    'the prevent_pam_log_modification trigger. chain_hash / chain_sequence provide '
    'tamper evidence using a global sequence (chain_sequence_counters_pam). '
    'session_recording_uri links to the terminal session recording in object storage.';
COMMENT ON COLUMN public.pam_audit_log.query_text IS
    'Full SQL or command text for database/API actions. Truncated to 10 000 chars '
    'by the broker. May contain PII — access is restricted to security-auditor role.';
COMMENT ON COLUMN public.pam_audit_log.chain_hash IS
    'HMAC-SHA256 over (prev_chain_hash || log fields). Computed by the PAM broker '
    'before insert. Verified hourly by the integrity-checker service.';

-- ---------------------------------------------------------------------------
-- 4. TRIGGER : prevent_pam_log_modification (IMMUTABILITY ENFORCEMENT)
--    Raises EXCEPTION on any UPDATE or DELETE attempt against pam_audit_log.
--    This is the last line of defence; the application should never attempt
--    to modify audit log rows, but the trigger prevents any accidental or
--    malicious modification even by privileged DB roles (short of superuser).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.prevent_pam_log_modification()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SET search_path = public
AS $$
BEGIN
    -- This trigger fires BEFORE UPDATE or BEFORE DELETE.
    -- Raising an exception unconditionally aborts the statement.
    RAISE EXCEPTION
        'pam_audit_log is immutable. UPDATE and DELETE are prohibited. '
        'Attempted operation: %. '
        'If you believe this is an error, contact the security team.',
        TG_OP;
    -- RETURN NULL is never reached but is required for plpgsql syntax.
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.prevent_pam_log_modification() IS
    'BEFORE UPDATE OR DELETE trigger function on pam_audit_log. '
    'Raises EXCEPTION unconditionally to enforce the append-only immutability '
    'contract of the PAM audit trail.';

-- Attach the immutability trigger to pam_audit_log (idempotent).
DROP TRIGGER IF EXISTS prevent_pam_log_modification ON public.pam_audit_log;
CREATE TRIGGER prevent_pam_log_modification
    BEFORE UPDATE OR DELETE ON public.pam_audit_log
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_pam_log_modification();

-- ---------------------------------------------------------------------------
-- 5. HITL QUEUE TABLE
--    Human-In-The-Loop review queue for AI-generated audit findings.
--    The RAG pipeline produces findings and evaluates them against
--    faithfulness and groundedness thresholds.  Findings that fall below the
--    combined threshold are inserted here for human review before being
--    published to the compliance report.
--
--    Workflow states:
--      PENDING_REVIEW → reviewer examines the finding and retrieved context
--      APPROVED       → finding is published as-is
--      EDITED         → reviewer corrected the finding before publishing
--      REJECTED       → finding is discarded (hallucination or irrelevant)
--
--    RLS + FORCE RLS — findings contain tenant-specific evidence; cross-
--    tenant leakage must be prevented even for internal reviewers.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hitl_queue (
    hitl_id                  UUID             NOT NULL DEFAULT gen_random_uuid(),
    tenant_id                UUID             NOT NULL,
    -- The original question or finding request sent to the RAG pipeline.
    finding_request          TEXT             NOT NULL,
    -- The AI-generated finding text to be reviewed.
    generated_finding        TEXT             NOT NULL,
    -- JSONB array of retrieved evidence chunks used as context.
    -- Structure: [{chunk_id, evidence_id, chunk_text, similarity_score}, ...].
    retrieved_context        JSONB            NOT NULL,
    -- Faithfulness score from the evaluation LLM: does the finding accurately
    -- reflect the retrieved context?  Range [0.0, 1.0].
    faithfulness_score       DOUBLE PRECISION NOT NULL,
    -- Groundedness score: is every claim in the finding supported by at least
    -- one retrieved chunk?  Range [0.0, 1.0].
    groundedness_score       DOUBLE PRECISION NOT NULL,
    -- Weighted combination of faithfulness_score and groundedness_score.
    -- Findings with combined_score < threshold_used are queued here.
    combined_score           DOUBLE PRECISION NOT NULL,
    -- The threshold value at the time this finding was evaluated.  Stored to
    -- allow retrospective analysis if the threshold is later adjusted.
    threshold_used           DOUBLE PRECISION NOT NULL,
    -- Review lifecycle status.
    status                   TEXT             NOT NULL DEFAULT 'PENDING_REVIEW'
                                CHECK (status IN (
                                    'PENDING_REVIEW',
                                    'APPROVED',
                                    'EDITED',
                                    'REJECTED'
                                )),
    -- Reviewer identity; NULL while PENDING_REVIEW.
    reviewer_user_id         UUID             NULL,
    -- FIDO2 assertion ID proving the reviewer authenticated before submitting
    -- their decision (non-repudiation requirement for SOC 2 Type II).
    reviewer_fido2_assertion_id TEXT          NULL,
    -- Free-text justification required when status = REJECTED or EDITED.
    reviewer_justification   TEXT             NULL,
    reviewed_at              TIMESTAMPTZ      NULL,
    created_at               TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- Array of evidence_record UUIDs that were used to generate this finding.
    -- Denormalised here for quick lookup; the canonical source is
    -- retrieved_context.
    evidence_record_ids      UUID[]           NULL,

    CONSTRAINT hitl_queue_pkey
        PRIMARY KEY (hitl_id),
    CONSTRAINT hitl_queue_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT hitl_queue_reviewer_fk
        FOREIGN KEY (reviewer_user_id) REFERENCES public.users (user_id)
        ON DELETE SET NULL,
    -- Scores must be in [0, 1].
    CONSTRAINT hitl_faithfulness_range
        CHECK (faithfulness_score BETWEEN 0 AND 1),
    CONSTRAINT hitl_groundedness_range
        CHECK (groundedness_score BETWEEN 0 AND 1),
    CONSTRAINT hitl_combined_range
        CHECK (combined_score BETWEEN 0 AND 1)
);

COMMENT ON TABLE  public.hitl_queue IS
    'Human-In-The-Loop review queue for AI-generated audit findings. '
    'Findings whose combined faithfulness/groundedness score falls below '
    'threshold_used are held here until a qualified reviewer approves, edits, '
    'or rejects them. reviewer_fido2_assertion_id provides non-repudiation. '
    'RLS enforces tenant isolation.';
COMMENT ON COLUMN public.hitl_queue.faithfulness_score IS
    'Evaluation LLM score: does the generated finding accurately reflect the '
    'retrieved context chunks?  Range [0.0, 1.0].';
COMMENT ON COLUMN public.hitl_queue.groundedness_score IS
    'Evaluation LLM score: is every claim grounded in at least one retrieved '
    'context chunk?  Range [0.0, 1.0].';
COMMENT ON COLUMN public.hitl_queue.retrieved_context IS
    'JSONB array of retrieved context chunks: '
    '[{chunk_id, evidence_id, chunk_text, similarity_score}, ...]. '
    'Displayed to the reviewer so they can assess finding quality.';
COMMENT ON COLUMN public.hitl_queue.evidence_record_ids IS
    'Denormalised array of evidence_record UUIDs contributing to this finding. '
    'Canonical source is the retrieved_context JSONB.';

-- RLS on hitl_queue.
ALTER TABLE public.hitl_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hitl_queue FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.hitl_queue;
CREATE POLICY tenant_isolation
    ON public.hitl_queue
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 6. INDEXES
-- ---------------------------------------------------------------------------

-- access_requests: list a user''s own requests by status (e.g. "my pending
-- requests").
CREATE INDEX IF NOT EXISTS idx_access_requests_user_status
    ON public.access_requests (requesting_user_id, status);

COMMENT ON INDEX public.idx_access_requests_user_status IS
    'List a user''s access requests filtered by status. Used by the PAM dashboard.';

-- access_requests: partial index for approved requests — the broker polls
-- this to find sessions that should be expired.
CREATE INDEX IF NOT EXISTS idx_access_requests_expires
    ON public.access_requests (expires_at)
    WHERE status = 'approved';

COMMENT ON INDEX public.idx_access_requests_expires IS
    'Partial index over approved access requests. Used by the session-expiry '
    'background job to find and expire overdue sessions efficiently.';

-- pam_audit_log: look up all log entries for a specific access request
-- (e.g. "show me everything that happened during this break-glass session").
CREATE INDEX IF NOT EXISTS idx_pam_log_request_id
    ON public.pam_audit_log (request_id);

COMMENT ON INDEX public.idx_pam_log_request_id IS
    'Retrieve all audit entries for a specific access_request. '
    'Used by the PAM session detail view.';

-- pam_audit_log: time-ordered view for the security operations dashboard.
-- DESC ordering matches the most common query pattern (recent events first).
CREATE INDEX IF NOT EXISTS idx_pam_log_logged_at
    ON public.pam_audit_log (logged_at DESC);

COMMENT ON INDEX public.idx_pam_log_logged_at IS
    'Time-ordered PAM audit log access for the security operations dashboard. '
    'DESC matches the ''most recent first'' query pattern.';

-- hitl_queue: primary dashboard query — tenant''s pending review items.
CREATE INDEX IF NOT EXISTS idx_hitl_tenant_status
    ON public.hitl_queue (tenant_id, status);

COMMENT ON INDEX public.idx_hitl_tenant_status IS
    'Primary HITL queue dashboard query: pending reviews per tenant. '
    'Combined with the tenant_isolation RLS policy for efficient lookups.';

-- ---------------------------------------------------------------------------
-- 7. GRANTS TO aegis_app
-- ---------------------------------------------------------------------------

-- access_requests: the PAM broker needs full DML access.
GRANT SELECT, INSERT, UPDATE ON public.access_requests TO aegis_app;

-- pam_audit_log: INSERT only — the immutability trigger prevents UPDATE/DELETE,
-- but withholding the grants is an additional explicit safeguard.
GRANT SELECT, INSERT ON public.pam_audit_log TO aegis_app;

-- chain_sequence_counters_pam: the PAM broker''s insert path needs to
-- SELECT FOR UPDATE and UPDATE this singleton row.
GRANT SELECT, UPDATE ON public.chain_sequence_counters_pam TO aegis_app;

-- hitl_queue: full DML for the review workflow service.
GRANT SELECT, INSERT, UPDATE ON public.hitl_queue TO aegis_app;

-- ---------------------------------------------------------------------------
-- END OF MIGRATION V004
-- ---------------------------------------------------------------------------
