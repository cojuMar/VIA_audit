-- =============================================================================
-- Migration: V006__create_zk_proofs_table.sql
-- Project:   Aegis 2026 – Sprint 2 – Zero-Touch Evidence Engine
-- Purpose:   ZK-proof storage layer: proof metadata + blob references,
--            circuit registry, and FK linkage from evidence_records.
--
-- Design notes:
--   * Proof blobs are stored externally on WORM-locked S3 / MinIO; this table
--     stores metadata and the URI to locate each blob, plus a SHA-256 hash
--     so the verifier can detect tampering before running the costly
--     on-chain / cryptographic verification step.
--   * The partial unique index on (tenant_id, circuit_type, proof_hash)
--     WHERE status = 'verified' prevents double-storage of identical proofs
--     while still allowing multiple pending/generating rows with the same
--     inputs during retry scenarios.
--   * evidence_record_ids is a UUID[] array; the GIN index enables efficient
--     "find all proofs that cover this evidence record" queries.
--   * zk_circuit_registry is platform-level (no RLS) – all tenants share
--     the same deployed circuit versions.
--   * The ALTER TABLE on evidence_records is idempotent via IF NOT EXISTS.
--
-- Idempotency: all DDL uses IF NOT EXISTS / DO $$ … $$ guards.
--              Safe to re-run on an already-migrated database.
-- =============================================================================


-- =============================================================================
-- TABLE: zk_proofs
-- One row per ZK proof generation request.  Tracks the full lifecycle from
-- initial request through generation, optional batching, and final
-- verification.  The proof blob itself lives in WORM object storage; this
-- table holds the metadata needed to retrieve, integrity-check, and verify it.
-- =============================================================================
CREATE TABLE IF NOT EXISTS zk_proofs (

    -- Primary key.
    proof_id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Owning tenant.  References the central tenants table; not cascaded —
    -- proofs must be explicitly purged through the data-retention pipeline.
    tenant_id                   UUID        NOT NULL
                                            REFERENCES tenants(tenant_id),

    -- The ZK circuit used to generate this proof.
    -- Matches zk_circuit_registry.circuit_type.
    -- Examples: 'sum_threshold', 'access_log_membership', 'policy_compliance'
    circuit_type                TEXT        NOT NULL,

    -- The exact circuit version used (must match a row in zk_circuit_registry).
    -- Stored denormalised so historical proofs remain interpretable even after
    -- a circuit is deprecated.
    circuit_version             TEXT        NOT NULL DEFAULT '1.0.0',

    -- The public inputs to the ZK proof — the verifiable claims that an
    -- auditor can inspect without learning the private witness.
    -- Example for sum_threshold:
    --   { "sum_exceeds_threshold": true, "threshold": 100000, "currency": "USD" }
    -- Example for access_log_membership:
    --   { "user_ids_in_set": true, "set_commitment": "0xabc...", "count": 47 }
    public_inputs               JSONB       NOT NULL,

    -- URI of the proof blob in WORM object storage.
    -- Format: s3://aegis-evidence-{region}/proofs/{tenant_id}/{proof_id}.bin
    -- The blob is readable by the verifier worker using the MinIO/S3 SDK.
    proof_blob_uri              TEXT        NOT NULL,

    -- SHA-256 hash of the proof blob content (32 bytes, stored as BYTEA).
    -- The verifier MUST recompute this hash before running verification to
    -- detect storage-layer tampering or corruption.
    proof_hash                  BYTEA       NOT NULL,

    -- Blob size in bytes (informational; used for storage accounting).
    proof_size_bytes            BIGINT,

    -- Generation lifecycle timestamps.
    generation_started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation_completed_at     TIMESTAMPTZ,

    -- Wall-clock generation time in milliseconds (for performance monitoring
    -- and capacity planning; large batches can take minutes on CPU-only nodes).
    generation_duration_ms      INT,

    -- Identity of the worker (Kubernetes pod name or bare-metal hostname)
    -- that generated this proof.  Used for debugging performance outliers.
    generation_worker_id        TEXT,

    -- Verification timestamps and result.
    -- verified_at is NULL until the verifier worker processes this proof.
    -- verifier_output = TRUE  → proof is cryptographically valid
    -- verifier_output = FALSE → proof is INVALID (potential fraud signal)
    verified_at                 TIMESTAMPTZ,
    verifier_output             BOOLEAN,
    verifier_worker_id          TEXT,

    -- Full proof lifecycle state:
    --   pending      – request queued, worker not yet assigned
    --   generating   – proof computation in progress
    --   generated    – blob written to object storage, awaiting verification
    --   verified     – verifier confirmed the proof is valid
    --   failed       – generation or verification raised an unrecoverable error
    --   invalid      – verifier ran successfully but the proof did NOT verify
    status                      TEXT        NOT NULL DEFAULT 'pending'
                                            CHECK (status IN (
                                                'pending','generating','generated',
                                                'verified','failed','invalid'
                                            )),

    -- Error detail (populated on status = 'failed').
    error_message               TEXT,

    -- The set of evidence_records.evidence_id values that this proof covers.
    -- A GIN index on this column enables "which proofs cover record X?" queries.
    evidence_record_ids         UUID[]      NOT NULL,

    -- Number of sub-batches used during generation (for memory-constrained
    -- multi-pass proof generation on large evidence sets).
    -- 1 = single-pass (normal case); >1 = batched recursive proof.
    batch_count                 INT         NOT NULL DEFAULT 1,

    -- Row creation timestamp.
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Partial unique index: prevents duplicate verified proofs for the same
-- (tenant, circuit, proof content).  Using a partial index (WHERE
-- status='verified') allows concurrent pending/generating rows for retry
-- logic without violating uniqueness.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_zk_proofs_verified
    ON zk_proofs (tenant_id, circuit_type, proof_hash)
    WHERE status = 'verified';

-- ---------------------------------------------------------------------------
-- Row-Level Security: zk_proofs
-- ---------------------------------------------------------------------------
ALTER TABLE zk_proofs ENABLE ROW LEVEL SECURITY;
ALTER TABLE zk_proofs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'zk_proofs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON zk_proofs
            USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Indexes: zk_proofs
-- ---------------------------------------------------------------------------

-- Operational dashboard: "show me all proofs for this tenant, newest first."
CREATE INDEX IF NOT EXISTS idx_zk_proofs_tenant_status_created
    ON zk_proofs (tenant_id, status, created_at DESC);

-- Circuit-level analytics: "how many proofs per circuit per tenant?"
CREATE INDEX IF NOT EXISTS idx_zk_proofs_tenant_circuit_status
    ON zk_proofs (tenant_id, circuit_type, status);

-- GIN index for array containment: "find all proofs that contain evidence
-- record X" — uses the @> operator:
--   SELECT * FROM zk_proofs WHERE evidence_record_ids @> ARRAY['<uuid>'::UUID];
CREATE INDEX IF NOT EXISTS idx_zk_proofs_evidence_record_ids
    ON zk_proofs USING GIN (evidence_record_ids);

-- Partial index: pending/generating proofs for queue-depth monitoring and
-- worker pickup queries (avoids scanning the bulk of completed rows).
CREATE INDEX IF NOT EXISTS idx_zk_proofs_pending_generation
    ON zk_proofs (generation_started_at)
    WHERE status IN ('pending', 'generating');


-- =============================================================================
-- TABLE: zk_circuit_registry
-- Catalog of deployed ZK circuits.  Platform-level metadata; no RLS.
-- Each (circuit_type, version) pair is unique.  Circuits are never hard-
-- deleted — set deprecated_at to retire a circuit version.
-- =============================================================================
CREATE TABLE IF NOT EXISTS zk_circuit_registry (

    circuit_id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Machine-readable circuit identifier, e.g. 'sum_threshold'.
    -- Must match circuit_type values used in zk_proofs.
    circuit_type            TEXT        NOT NULL,

    -- Semantic version, e.g. '1.0.0'.
    version                 TEXT        NOT NULL,

    -- Human-readable description shown in the audit report and UI.
    description             TEXT        NOT NULL,

    -- Number of arithmetic gates in the compiled circuit.
    -- Used for capacity planning and as a sanity-check after recompilation.
    -- NULL until the circuit has been compiled and profiled.
    constraint_count        INT,

    -- Maximum evidence records per proof invocation.
    -- Default 65536 (2^16) is safe for a 16 GB RAM worker with current
    -- Halo2/Plonky2 backends.  Larger batches require recursive composition.
    max_batch_size          INT         NOT NULL DEFAULT 65536,

    -- SHA-256 hash of the verification key file.
    -- The verifier worker checks this at startup; a mismatch means the vk
    -- was tampered with or the circuit was recompiled without bumping the
    -- version — both conditions must trigger an alert.
    verification_key_hash   BYTEA,

    -- Whether this circuit version is available for new proof requests.
    is_active               BOOLEAN     NOT NULL DEFAULT TRUE,

    -- Timestamp when this circuit version was first deployed to production.
    deployed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Set when a circuit version is superseded; workers reject new requests
    -- for deprecated circuits but can still verify existing proofs.
    deprecated_at           TIMESTAMPTZ,

    -- Reference to the external security audit report for this circuit.
    -- Format: '<auditor>-<year>-<sequence>', e.g. 'trailofbits-2026-001'.
    -- NULL if the circuit has not yet been externally audited (dev/staging only).
    security_audit_ref      TEXT,

    -- Composite unique key: one active row per (type, version) pair.
    CONSTRAINT uq_circuit_registry_type_version
        UNIQUE (circuit_type, version)
);

-- Index for active-circuit lookups by type.
CREATE INDEX IF NOT EXISTS idx_zk_circuit_registry_type_active
    ON zk_circuit_registry (circuit_type, is_active);


-- =============================================================================
-- ALTER: evidence_records
-- Add zk_proof_id FK column to link an evidence record back to its covering
-- proof.  IF NOT EXISTS makes this idempotent.
-- NULL = not yet proved (common during ingestion before the proof worker runs).
-- =============================================================================
ALTER TABLE evidence_records
    ADD COLUMN IF NOT EXISTS zk_proof_id UUID REFERENCES zk_proofs(proof_id);

-- Supporting index for "find all evidence records covered by proof X."
CREATE INDEX IF NOT EXISTS idx_evidence_records_zk_proof_id
    ON evidence_records (zk_proof_id)
    WHERE zk_proof_id IS NOT NULL;


-- =============================================================================
-- SEED DATA: zk_circuit_registry
-- Initial set of circuits deployed with Sprint 2.
-- ON CONFLICT DO NOTHING makes these idempotent.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Circuit: sum_threshold  v1.0.0
-- Proves that the sum of a set of financial values exceeds (or does not
-- exceed) a given threshold, without revealing individual transaction amounts.
-- Use case: demonstrate solvency, large-payment compliance, AML thresholds.
-- ---------------------------------------------------------------------------
INSERT INTO zk_circuit_registry (
    circuit_type,
    version,
    description,
    constraint_count,
    max_batch_size,
    is_active,
    security_audit_ref
)
VALUES (
    'sum_threshold',
    '1.0.0',
    'Proves that the private sum of a set of financial amounts satisfies a '
    'public threshold predicate (sum >= threshold or sum < threshold) without '
    'revealing individual values.  Supports multi-currency normalisation via '
    'a public FX rate commitment.',
    2097152,   -- ~2M gates (Halo2 backend, 16-col wide circuit)
    65536,     -- 65536 transactions per single-pass proof (16 GB RAM safe)
    TRUE,
    'trailofbits-2026-001'
)
ON CONFLICT (circuit_type, version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Circuit: access_log_membership  v1.0.0
-- Proves that a set of user IDs observed in access logs is a subset of (or
-- equal to) a committed authorised-user set, without revealing the user IDs.
-- Use case: SOC 2 access review, least-privilege attestation.
-- ---------------------------------------------------------------------------
INSERT INTO zk_circuit_registry (
    circuit_type,
    version,
    description,
    constraint_count,
    max_batch_size,
    is_active,
    security_audit_ref
)
VALUES (
    'access_log_membership',
    '1.0.0',
    'Proves that every user identity present in a set of access-log records '
    'belongs to a committed set of authorised principals, using a Merkle-tree '
    'membership argument.  Public inputs: set Merkle root, record count, '
    'and the Boolean result (all_authorised).',
    4194304,   -- ~4M gates (Merkle depth 20, 65536 members max)
    65536,
    TRUE,
    'trailofbits-2026-001'
)
ON CONFLICT (circuit_type, version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Circuit: policy_compliance  v1.0.0
-- Proves that a set of configuration snapshots satisfies a compiled policy
-- ruleset, without revealing the raw configuration values.
-- Use case: CIS Benchmark attestation, PCI-DSS control evidence, SOX ITGCs.
-- ---------------------------------------------------------------------------
INSERT INTO zk_circuit_registry (
    circuit_type,
    version,
    description,
    constraint_count,
    max_batch_size,
    is_active,
    security_audit_ref
)
VALUES (
    'policy_compliance',
    '1.0.0',
    'Proves that a private set of system configuration values satisfies every '
    'rule in a public compiled policy (expressed as an arithmetic circuit '
    'predicate).  Public inputs: policy commitment hash, snapshot count, '
    'compliance result (passed / failed / partial), and failing rule bitmask.',
    8388608,   -- ~8M gates (policy ruleset of up to 256 rules × 32768 snapshots)
    32768,     -- smaller batch due to higher per-record gate count
    TRUE,
    'trailofbits-2026-001'
)
ON CONFLICT (circuit_type, version) DO NOTHING;

-- =============================================================================
-- END V006__create_zk_proofs_table.sql
-- =============================================================================
