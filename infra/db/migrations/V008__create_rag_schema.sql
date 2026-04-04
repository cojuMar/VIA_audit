-- =============================================================================
-- V008__create_rag_schema.sql
-- Project Aegis 2026 – Sprint 4: RAG Audit Narrative Pipeline
-- =============================================================================
-- Purpose:
--   Creates the full RAG (Retrieval-Augmented Generation) layer required by the
--   rag-pipeline-service.  All DDL is fully idempotent – every CREATE TABLE,
--   CREATE INDEX, and INSERT uses IF NOT EXISTS / ON CONFLICT DO NOTHING so
--   this migration can be replayed safely without error.
--
-- Tables created:
--   1. evidence_embeddings    – vector embeddings of evidence records (pgvector)
--   2. audit_narratives       – AI-generated audit narrative documents
--   3. rag_citations          – evidence records cited in each narrative (M:M)
--   4. hitl_narrative_queue   – escalation queue for low-confidence narratives
--   5. embedding_jobs         – background job tracker for new embeddings
--
-- Row-Level Security:
--   Tables 1, 2, 3, 4 enforce tenant isolation via RLS (FORCE RLS).
--   Table 5 (embedding_jobs) has NO RLS – processed by background worker.
--
-- Extensions:
--   vector  – pgvector for ANN similarity search on evidence embeddings.
--
-- Author  : Aegis Platform Team
-- Sprint  : 4 (RAG Audit Narrative Pipeline)
-- Created : 2026-04-03
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSIONS
-- ---------------------------------------------------------------------------
-- pgvector provides the `vector` column type and IVFFLAT / HNSW index methods.
-- pgcrypto provides gen_random_uuid() used in all PK defaults.
-- Both CREATE EXTENSION IF NOT EXISTS calls are idempotent.
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- TABLE 1: evidence_embeddings
-- =============================================================================
-- Stores the vector embedding produced by the Voyage / OpenAI embedding model
-- for each evidence record.  One row per (evidence_record_id, model_version)
-- pair – enforced by a unique constraint so that re-embedding with a newer
-- model does not silently overwrite the prior representation.
--
-- embedding:
--   1536-dimensional dense float vector produced by voyage-law-2 or the
--   OpenAI text-embedding-3-small model.  The IVFFLAT index below enables
--   approximate nearest-neighbour search using cosine distance.
--
-- model_version:
--   Identifies the embedding model used.  Default is 'voyage-law-2'.
--   Stored so that embeddings produced by different model versions can
--   coexist in the table and be queried selectively.
-- =============================================================================
CREATE TABLE IF NOT EXISTS evidence_embeddings (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    evidence_embedding_id   UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Source evidence record – cascades deletes so orphan embeddings are
    -- automatically removed when an evidence record is deleted.
    -- -------------------------------------------------------------------------
    evidence_record_id      UUID        NOT NULL
                                        REFERENCES evidence_records(evidence_id)
                                        ON DELETE CASCADE,

    -- -------------------------------------------------------------------------
    -- Tenant isolation – every row belongs to exactly one tenant.
    -- -------------------------------------------------------------------------
    tenant_id               UUID        NOT NULL
                                        REFERENCES tenants(tenant_id),

    -- -------------------------------------------------------------------------
    -- The dense vector embedding (1536 dimensions).
    -- Populated by the embedding job worker after chunking the evidence text.
    -- -------------------------------------------------------------------------
    embedding               vector(1536),

    -- -------------------------------------------------------------------------
    -- Model version used to produce this embedding.
    -- Used to filter searches to a consistent embedding space.
    -- -------------------------------------------------------------------------
    model_version           TEXT        NOT NULL DEFAULT 'voyage-law-2',

    -- -------------------------------------------------------------------------
    -- Timestamps
    -- -------------------------------------------------------------------------
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT evidence_embeddings_pkey
        PRIMARY KEY (evidence_embedding_id),

    -- Prevent duplicate embeddings for the same record + model combination.
    -- Allows upserts via ON CONFLICT (evidence_record_id, model_version).
    CONSTRAINT evidence_embeddings_record_model_unique
        UNIQUE (evidence_record_id, model_version)
);

-- Row-Level Security: tenants may only see their own embeddings.
ALTER TABLE evidence_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_embeddings FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'evidence_embeddings'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON evidence_embeddings
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- IVFFLAT approximate nearest-neighbour index using cosine distance.
-- lists = 100 is appropriate for up to ~1 M vectors per tenant.
-- For production deployments with more than 10 M vectors, consider
-- increasing lists or migrating to an HNSW index.
CREATE INDEX IF NOT EXISTS idx_evidence_embeddings_vector
    ON evidence_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- =============================================================================
-- TABLE 2: audit_narratives
-- =============================================================================
-- Stores every AI-generated audit narrative document produced by the
-- rag-pipeline-service.  Each row represents one generation request for a
-- specific compliance framework, control, and audit period.
--
-- Deduplication:
--   prompt_hash (SHA-256 of the final prompt, including all retrieved chunks)
--   is stored so that identical generation requests can be short-circuited
--   without calling the LLM again.
--
-- Quality scoring:
--   faithfulness_score  – measures whether every claim in the narrative is
--                         supported by at least one retrieved evidence chunk
--                         (higher = better; computed by RAGAs / TruLens).
--   groundedness_score  – measures whether the narrative stays within the
--                         scope of the retrieved context without hallucinating
--                         facts (higher = better).
--   combined_score      – weighted average used for HITL threshold comparison.
--                         Narratives with combined_score < HALLUCINATION_THRESHOLD
--                         (default 0.45) are automatically escalated to the
--                         hitl_narrative_queue.
--
-- HITL workflow:
--   hitl_required       – set TRUE by the service when combined_score is below
--                         the configured threshold.
--   hitl_reviewed       – set TRUE after a human reviewer has actioned the row.
--   hitl_verdict        – 'approved' | 'rejected' | 'edited'.
--   revised_narrative   – populated when hitl_verdict = 'edited'.
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_narratives (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    narrative_id            UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Tenant isolation
    -- -------------------------------------------------------------------------
    tenant_id               UUID        NOT NULL
                                        REFERENCES tenants(tenant_id),

    -- -------------------------------------------------------------------------
    -- Compliance context
    -- -------------------------------------------------------------------------

    -- The compliance framework for which the narrative was generated.
    -- Common values: 'soc2', 'iso27001', 'pci_dss', 'custom'.
    framework               TEXT        NOT NULL,

    -- The specific control identifier within the framework, e.g. 'CC6.1' for
    -- SOC 2 or 'A.9.1.2' for ISO 27001.  NULL for framework-level narratives.
    control_id              TEXT,

    -- Audit period covered by this narrative.
    period_start            DATE        NOT NULL,
    period_end              DATE        NOT NULL,

    -- -------------------------------------------------------------------------
    -- Generation inputs and output
    -- -------------------------------------------------------------------------

    -- SHA-256 hash of the final prompt (serialised as \x hex BYTEA).
    -- Used for exact-match deduplication.
    prompt_hash             BYTEA       NOT NULL,

    -- The full text of the generated narrative returned by the LLM.
    raw_narrative           TEXT        NOT NULL,

    -- -------------------------------------------------------------------------
    -- Quality / hallucination scores (all in [0, 1])
    -- -------------------------------------------------------------------------
    faithfulness_score      NUMERIC(4,3)
                                CHECK (faithfulness_score BETWEEN 0 AND 1),

    groundedness_score      NUMERIC(4,3)
                                CHECK (groundedness_score BETWEEN 0 AND 1),

    combined_score          NUMERIC(4,3)
                                CHECK (combined_score BETWEEN 0 AND 1),

    -- -------------------------------------------------------------------------
    -- Human-in-the-Loop (HITL) workflow
    -- -------------------------------------------------------------------------
    hitl_required           BOOLEAN     NOT NULL DEFAULT FALSE,
    hitl_reviewed           BOOLEAN     NOT NULL DEFAULT FALSE,
    hitl_reviewer_id        UUID        REFERENCES users(user_id),
    hitl_reviewed_at        TIMESTAMPTZ,
    hitl_verdict            TEXT
                                CHECK (hitl_verdict IN ('approved', 'rejected', 'edited')),

    -- Populated by the reviewer when hitl_verdict = 'edited'.
    revised_narrative       TEXT,

    -- -------------------------------------------------------------------------
    -- Generation metadata
    -- -------------------------------------------------------------------------

    -- LLM used for generation (default: claude-opus-4-6).
    generation_model        TEXT        NOT NULL DEFAULT 'claude-opus-4-6',

    -- End-to-end generation latency in milliseconds (includes retrieval +
    -- reranking + LLM inference).
    generation_latency_ms   INTEGER,

    -- -------------------------------------------------------------------------
    -- Timestamps
    -- -------------------------------------------------------------------------
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT audit_narratives_pkey PRIMARY KEY (narrative_id)
);

-- Row-Level Security: tenants may only see their own narratives.
ALTER TABLE audit_narratives ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_narratives FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'audit_narratives'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON audit_narratives
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- Partial index: efficiently retrieve the HITL review backlog for a tenant,
-- ordered by creation time (oldest first = FIFO queue processing).
-- Only includes rows that still need review (hitl_reviewed = FALSE).
CREATE INDEX IF NOT EXISTS idx_narratives_hitl_pending
    ON audit_narratives (tenant_id, created_at DESC)
    WHERE hitl_required = TRUE AND hitl_reviewed = FALSE;

-- =============================================================================
-- TABLE 3: rag_citations
-- =============================================================================
-- Records the many-to-many relationship between a generated audit narrative
-- and the evidence records that were retrieved and cited during generation.
--
-- Each row captures the specific text chunk that was retrieved from the
-- evidence record (chunk_text), the cosine similarity score assigned by the
-- vector search (similarity_score), and the rank of this citation within the
-- narrative's context window (citation_rank = 1 is the most relevant chunk).
--
-- The UNIQUE constraint prevents the same evidence record from being cited
-- twice within a single narrative.
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_citations (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    citation_id             UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Parent narrative – cascade delete cleans up citations when a narrative
    -- is deleted (e.g. during a rejected HITL review workflow).
    -- -------------------------------------------------------------------------
    narrative_id            UUID        NOT NULL
                                        REFERENCES audit_narratives(narrative_id)
                                        ON DELETE CASCADE,

    -- -------------------------------------------------------------------------
    -- Source evidence record
    -- -------------------------------------------------------------------------
    evidence_record_id      UUID        NOT NULL
                                        REFERENCES evidence_records(evidence_id),

    -- -------------------------------------------------------------------------
    -- Tenant isolation
    -- -------------------------------------------------------------------------
    tenant_id               UUID        NOT NULL
                                        REFERENCES tenants(tenant_id),

    -- -------------------------------------------------------------------------
    -- Retrieval metadata
    -- -------------------------------------------------------------------------

    -- Cosine similarity score from the ANN search, in [0, 1].
    -- Higher = more semantically similar to the query.
    similarity_score        NUMERIC(5,4)
                                CHECK (similarity_score BETWEEN 0 AND 1),

    -- Rank of this chunk within the context window (1 = highest similarity).
    -- Useful for building attribution UIs and for debugging retrieval quality.
    citation_rank           SMALLINT    NOT NULL,

    -- The actual text chunk that was injected into the prompt context.
    -- Stored for full auditability and to enable faithfulness scoring
    -- without re-querying the evidence record.
    chunk_text              TEXT        NOT NULL,

    CONSTRAINT rag_citations_pkey
        PRIMARY KEY (citation_id),

    -- One citation row per (narrative, evidence record) pair.
    CONSTRAINT rag_citations_narrative_evidence_unique
        UNIQUE (narrative_id, evidence_record_id)
);

-- Row-Level Security: tenants may only see their own citation rows.
ALTER TABLE rag_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_citations FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'rag_citations'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON rag_citations
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- Lookup: fetch all citations belonging to a narrative (primary access pattern
-- for building the citation panel on the narrative review page).
CREATE INDEX IF NOT EXISTS idx_rag_citations_narrative
    ON rag_citations (narrative_id);

-- Lookup: find all narratives that cited a given evidence record (used on the
-- evidence detail page to display "cited in N narratives").
CREATE INDEX IF NOT EXISTS idx_rag_citations_evidence
    ON rag_citations (evidence_record_id);

-- =============================================================================
-- TABLE 4: hitl_narrative_queue
-- =============================================================================
-- Escalation queue populated automatically by the rag-pipeline-service for any
-- narrative whose combined_score falls below the configured HALLUCINATION_THRESHOLD
-- (default 0.45).  Reviewers work through the queue in priority + FIFO order.
--
-- flagged_claims:
--   JSONB array of objects identifying specific claims in the narrative that
--   are suspected of being hallucinated or insufficiently grounded.
--   Each element has the shape:
--     { "claim": "<text excerpt>", "issue": "<description>", "score": <float> }
--
-- priority:
--   'critical' – combined_score < 0.20 or framework = 'pci_dss'
--   'high'     – combined_score < 0.30
--   'normal'   – combined_score < 0.45 (default threshold)
--   'low'      – manually escalated by a service rule, not score-based
-- =============================================================================
CREATE TABLE IF NOT EXISTS hitl_narrative_queue (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    queue_id                UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Parent narrative – cascade delete removes the queue entry when the
    -- narrative is hard-deleted.
    -- -------------------------------------------------------------------------
    narrative_id            UUID        NOT NULL
                                        REFERENCES audit_narratives(narrative_id)
                                        ON DELETE CASCADE,

    -- -------------------------------------------------------------------------
    -- Tenant isolation
    -- -------------------------------------------------------------------------
    tenant_id               UUID        NOT NULL
                                        REFERENCES tenants(tenant_id),

    -- -------------------------------------------------------------------------
    -- Escalation details
    -- -------------------------------------------------------------------------

    -- Human-readable explanation of why this narrative was escalated, e.g.
    -- 'combined_score=0.32 < threshold=0.45'.
    escalation_reason       TEXT        NOT NULL,

    -- Structured list of specific claims identified as potentially problematic.
    flagged_claims          JSONB       NOT NULL DEFAULT '[]',

    -- -------------------------------------------------------------------------
    -- Assignment and workflow state
    -- -------------------------------------------------------------------------
    assigned_to             UUID        REFERENCES users(user_id),

    -- Queue item lifecycle state.
    status                  TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'in_review', 'resolved')),

    -- Priority band.  Used to sort the reviewer's queue.
    priority                TEXT        NOT NULL DEFAULT 'normal'
                                CHECK (priority IN ('low', 'normal', 'high', 'critical')),

    -- -------------------------------------------------------------------------
    -- Timestamps
    -- -------------------------------------------------------------------------
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ,

    CONSTRAINT hitl_narrative_queue_pkey PRIMARY KEY (queue_id)
);

-- Row-Level Security: tenants may only see their own queue items.
ALTER TABLE hitl_narrative_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl_narrative_queue FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'hitl_narrative_queue'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON hitl_narrative_queue
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- Partial index for the active queue (excludes resolved items which are only
-- accessed for audit history, not routine queue processing).
-- Sort order: most critical first, then highest priority, then oldest first
-- (FIFO within a priority band).
CREATE INDEX IF NOT EXISTS idx_hitl_queue_status
    ON hitl_narrative_queue (tenant_id, status, priority DESC, created_at ASC)
    WHERE status != 'resolved';

-- =============================================================================
-- TABLE 5: embedding_jobs
-- =============================================================================
-- Tracks the lifecycle of background embedding jobs submitted for new or
-- updated evidence records.  The rag-pipeline-service polls this table to
-- discover pending jobs and updates their status as work proceeds.
--
-- This table has NO RLS.  It is read and written exclusively by the background
-- embedding worker, which runs with a superuser-equivalent application role
-- (aegis_worker) that bypasses row-level security.  Tenant isolation is
-- enforced at the application layer via the tenant_id column.
--
-- The UNIQUE constraint on (tenant_id, evidence_record_id) ensures that at
-- most one active job exists per evidence record per tenant.  The worker
-- uses ON CONFLICT DO NOTHING when enqueuing to avoid duplicate submissions.
-- =============================================================================
CREATE TABLE IF NOT EXISTS embedding_jobs (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    job_id                  UUID        NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Tenant + evidence record identification
    -- -------------------------------------------------------------------------
    tenant_id               UUID        NOT NULL
                                        REFERENCES tenants(tenant_id),

    evidence_record_id      UUID        NOT NULL
                                        REFERENCES evidence_records(evidence_id),

    -- -------------------------------------------------------------------------
    -- Job lifecycle
    -- -------------------------------------------------------------------------

    -- Current processing state of the job.
    status                  TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending',
                                    'processing',
                                    'completed',
                                    'failed'
                                )),

    -- Number of processing attempts made.  Incremented by the worker on each
    -- attempt.  Jobs exceeding the configured MAX_ATTEMPTS are marked 'failed'.
    attempts                SMALLINT    NOT NULL DEFAULT 0,

    -- Error message from the most recent failed attempt.  NULL on success.
    last_error              TEXT,

    -- -------------------------------------------------------------------------
    -- Timestamps
    -- -------------------------------------------------------------------------
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,

    CONSTRAINT embedding_jobs_pkey PRIMARY KEY (job_id),

    -- Prevent duplicate job submissions for the same evidence record within
    -- the same tenant.  The worker enqueues with ON CONFLICT DO NOTHING.
    CONSTRAINT embedding_jobs_tenant_evidence_unique
        UNIQUE (tenant_id, evidence_record_id)
);

-- No RLS – processed by the background embedding worker with a service role
-- that bypasses row-level security.

-- =============================================================================
-- GRANTS
-- =============================================================================
-- Grant minimum necessary privileges to the aegis_app role used by all
-- application services connecting via PgBouncer.
--
-- embedding_jobs additionally receives DELETE so that the background worker
-- can clean up completed / failed job rows after processing.
-- =============================================================================

GRANT SELECT, INSERT, UPDATE
    ON audit_narratives
    TO aegis_app;

GRANT SELECT, INSERT, UPDATE
    ON rag_citations
    TO aegis_app;

GRANT SELECT, INSERT, UPDATE
    ON hitl_narrative_queue
    TO aegis_app;

GRANT SELECT, INSERT, UPDATE
    ON embedding_jobs
    TO aegis_app;

GRANT DELETE
    ON embedding_jobs
    TO aegis_app;

GRANT SELECT, INSERT, UPDATE
    ON evidence_embeddings
    TO aegis_app;

-- =============================================================================
-- END OF MIGRATION V008
-- =============================================================================
