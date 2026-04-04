-- =============================================================================
-- V013__create_tprm_schema.sql
-- Project: Aegis 2026 – Sprint 9 – Vendor & Third-Party Risk Management (TPRM)
--
-- Purpose:
--   Creates the TPRM schema: per-tenant vendor registry, questionnaire
--   management, document storage, risk scoring, contract tracking, continuous
--   monitoring events, and fourth-party (sub-processor) relationship mapping.
--
-- Design:
--   * Fully idempotent — safe to run multiple times (CREATE ... IF NOT EXISTS,
--     DO $$ ... $$ guards on RLS policies checking pg_policies).
--   * All tables are per-tenant and enforce RLS via
--     current_setting('app.tenant_id', TRUE)::UUID.
--   * vendor_risk_scores and vendor_monitoring_events are append-only:
--     aegis_app receives INSERT and SELECT only — no UPDATE or DELETE — to
--     preserve immutable audit trails.
--   * fourth_party_relationships captures vendor → sub-processor mappings
--     discovered via questionnaire responses or automated trust-centre pulls.
--
-- Tables:
--   vendors                       – per-tenant vendor registry
--   vendor_questionnaires         – per-tenant questionnaire lifecycle
--   vendor_documents              – per-tenant compliance document store
--   vendor_risk_scores            – per-tenant immutable risk score snapshots
--   vendor_contracts              – per-tenant contract and SLA tracking
--   vendor_monitoring_events      – per-tenant append-only monitoring feed
--   fourth_party_relationships    – per-tenant sub-processor relationship map
--
-- Roles assumed to exist: aegis_app
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. vendors
--    Per-tenant registry of all third-party vendors.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendors (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL,
    name                  TEXT NOT NULL,
    website               TEXT,
    description           TEXT,
    vendor_type           TEXT NOT NULL CHECK (vendor_type IN (
                              'saas','infrastructure','professional_services',
                              'data_processor','financial','hardware','other')),
    risk_tier             TEXT NOT NULL DEFAULT 'unrated' CHECK (risk_tier IN (
                              'critical','high','medium','low','unrated')),
    status                TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                              'active','inactive','under_review','offboarded')),
    primary_contact_name  TEXT,
    primary_contact_email TEXT,
    data_types_processed  TEXT[] NOT NULL DEFAULT '{}',
    integrations_depth    TEXT NOT NULL DEFAULT 'none' CHECK (integrations_depth IN (
                              'none','read_only','read_write','admin','core_infrastructure')),
    processes_pii         BOOLEAN NOT NULL DEFAULT FALSE,
    processes_phi         BOOLEAN NOT NULL DEFAULT FALSE,
    processes_pci         BOOLEAN NOT NULL DEFAULT FALSE,
    uses_ai               BOOLEAN NOT NULL DEFAULT FALSE,
    sub_processors        TEXT[] NOT NULL DEFAULT '{}',
    inherent_risk_score   NUMERIC(4,2),         -- 0.00 to 10.00 (auto-computed by rubric)
    residual_risk_score   NUMERIC(4,2),
    last_reviewed_at      TIMESTAMPTZ,
    next_review_at        TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendors                       IS 'Per-tenant registry of all third-party vendors; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN vendors.vendor_type           IS 'Classification of the vendor: saas, infrastructure, professional_services, data_processor, financial, hardware, or other.';
COMMENT ON COLUMN vendors.risk_tier             IS 'Assessed risk tier: critical, high, medium, low, or unrated (default until first assessment).';
COMMENT ON COLUMN vendors.integrations_depth    IS 'Depth of system integration: none, read_only, read_write, admin, or core_infrastructure.';
COMMENT ON COLUMN vendors.data_types_processed  IS 'Array of data classification labels the vendor processes on behalf of the tenant.';
COMMENT ON COLUMN vendors.inherent_risk_score   IS 'Inherent risk score in [0.00, 10.00] auto-computed by the TPRM scoring rubric before controls are applied.';
COMMENT ON COLUMN vendors.residual_risk_score   IS 'Residual risk score in [0.00, 10.00] after factoring in vendor-evidenced controls.';
COMMENT ON COLUMN vendors.next_review_at        IS 'Scheduled date of the next vendor risk review; drives calendar alerts.';

ALTER TABLE vendors ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendors FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendors'
          AND policyname = 'vendors_tenant_isolation'
    ) THEN
        CREATE POLICY vendors_tenant_isolation
            ON vendors
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON vendors TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendors_tenant_risk_tier
    ON vendors (tenant_id, risk_tier);

CREATE INDEX IF NOT EXISTS idx_vendors_tenant_status
    ON vendors (tenant_id, status);

-- Partial index covering only active vendors that have a scheduled review —
-- the dominant query pattern for dashboard due-date alerting.
CREATE INDEX IF NOT EXISTS idx_vendors_tenant_next_review_active
    ON vendors (tenant_id, next_review_at)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 2. vendor_questionnaires
--    Per-tenant questionnaire lifecycle: tracks template, status, responses,
--    and AI-computed risk score for each questionnaire sent to a vendor.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_questionnaires (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    vendor_id        UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    template_slug    TEXT NOT NULL,                -- 'sig-lite', 'caiq-v4', 'custom'
    template_version TEXT NOT NULL DEFAULT '1.0',
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                         'draft','sent','in_progress','completed','expired')),
    sent_at          TIMESTAMPTZ,
    due_date         TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    responses        JSONB NOT NULL DEFAULT '{}',  -- {question_id: answer}
    ai_score         NUMERIC(4,2),                 -- AI-computed risk score from responses
    ai_summary       TEXT,                         -- AI-generated summary of findings
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_questionnaires              IS 'Per-tenant questionnaire lifecycle records; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN vendor_questionnaires.template_slug IS 'Identifier of the questionnaire template used, e.g. sig-lite, caiq-v4, custom.';
COMMENT ON COLUMN vendor_questionnaires.responses    IS 'JSONB map of question_id to vendor-provided answer; keyed by the question id field in the template.';
COMMENT ON COLUMN vendor_questionnaires.ai_score     IS 'AI-computed risk score in [0.00, 10.00] derived from analysis of the vendor responses.';
COMMENT ON COLUMN vendor_questionnaires.ai_summary   IS 'AI-generated narrative summary of key findings and risk indicators from the responses.';

ALTER TABLE vendor_questionnaires ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_questionnaires FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendor_questionnaires'
          AND policyname = 'vendor_questionnaires_tenant_isolation'
    ) THEN
        CREATE POLICY vendor_questionnaires_tenant_isolation
            ON vendor_questionnaires
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON vendor_questionnaires TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendor_questionnaires_tenant_vendor
    ON vendor_questionnaires (tenant_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_vendor_questionnaires_tenant_status
    ON vendor_questionnaires (tenant_id, status);

-- ---------------------------------------------------------------------------
-- 3. vendor_documents
--    Per-tenant store of vendor-provided compliance documents (SOC 2,
--    ISO certificates, DPAs, BAAs, pentest reports, etc.).
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    vendor_id       UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    document_type   TEXT NOT NULL CHECK (document_type IN (
                        'soc2_type1','soc2_type2','iso27001_cert','pci_aoc',
                        'hipaa_baa','pentest_report','privacy_policy','dpa',
                        'insurance_cert','other')),
    filename        TEXT NOT NULL,
    minio_path      TEXT,                          -- storage path in MinIO
    file_size_bytes BIGINT,
    upload_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expiry_date     DATE,                          -- cert/report expiry
    ai_analysis     JSONB,                         -- AI-extracted findings {gaps:[], score:float, summary:str}
    analysis_status TEXT NOT NULL DEFAULT 'pending' CHECK (analysis_status IN (
                        'pending','analyzing','completed','failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_documents                 IS 'Per-tenant store of vendor-provided compliance documents; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN vendor_documents.document_type   IS 'Classification of the document: soc2_type1/type2, iso27001_cert, pci_aoc, hipaa_baa, pentest_report, privacy_policy, dpa, insurance_cert, or other.';
COMMENT ON COLUMN vendor_documents.minio_path      IS 'Object storage path within the aegis-vendor-docs MinIO bucket.';
COMMENT ON COLUMN vendor_documents.expiry_date     IS 'Wall-clock date on which the certificate or report expires; used for renewal alerting.';
COMMENT ON COLUMN vendor_documents.ai_analysis     IS 'AI-extracted findings JSONB: {gaps: string[], score: float, summary: string}.';
COMMENT ON COLUMN vendor_documents.analysis_status IS 'Processing state of AI analysis: pending, analyzing, completed, or failed.';

ALTER TABLE vendor_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_documents FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendor_documents'
          AND policyname = 'vendor_documents_tenant_isolation'
    ) THEN
        CREATE POLICY vendor_documents_tenant_isolation
            ON vendor_documents
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON vendor_documents TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendor_documents_tenant_vendor_type
    ON vendor_documents (tenant_id, vendor_id, document_type);

-- Partial index covering only documents with an expiry — used for renewal alerts.
CREATE INDEX IF NOT EXISTS idx_vendor_documents_tenant_expiry
    ON vendor_documents (tenant_id, expiry_date)
    WHERE expiry_date IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. vendor_risk_scores
--    Per-tenant immutable risk score snapshots computed by the TPRM engine.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE — to
--    preserve the scoring audit trail.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_risk_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    vendor_id       UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    inherent_score  NUMERIC(4,2) NOT NULL,
    residual_score  NUMERIC(4,2),
    score_factors   JSONB NOT NULL DEFAULT '{}',   -- breakdown of scoring factors
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_risk_scores               IS 'Immutable per-tenant vendor risk score snapshots; INSERT and SELECT only — no UPDATE or DELETE.';
COMMENT ON COLUMN vendor_risk_scores.inherent_score IS 'Inherent risk score in [0.00, 10.00] before vendor-evidenced controls are applied.';
COMMENT ON COLUMN vendor_risk_scores.residual_score IS 'Residual risk score in [0.00, 10.00] after factoring in vendor-evidenced controls; NULL until controls are evaluated.';
COMMENT ON COLUMN vendor_risk_scores.score_factors  IS 'JSONB breakdown of individual scoring factors and their weighted contributions.';

ALTER TABLE vendor_risk_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_risk_scores FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendor_risk_scores'
          AND policyname = 'vendor_risk_scores_tenant_isolation'
    ) THEN
        CREATE POLICY vendor_risk_scores_tenant_isolation
            ON vendor_risk_scores
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable risk score snapshots.
GRANT SELECT, INSERT ON vendor_risk_scores TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendor_risk_scores_tenant_vendor_time
    ON vendor_risk_scores (tenant_id, vendor_id, computed_at DESC);

-- ---------------------------------------------------------------------------
-- 5. vendor_contracts
--    Per-tenant contract and SLA tracking: MSAs, DPAs, NDAs, BAAs,
--    order forms, and amendments with renewal alerting support.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_contracts (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    vendor_id            UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    contract_type        TEXT NOT NULL CHECK (contract_type IN (
                             'msa','dpa','nda','sla','baa','order_form',
                             'amendment','other')),
    title                TEXT NOT NULL,
    effective_date       DATE,
    expiry_date          DATE,
    auto_renews          BOOLEAN NOT NULL DEFAULT FALSE,
    renewal_notice_days  INTEGER DEFAULT 90,
    contract_value       NUMERIC(15,2),
    currency             CHAR(3) DEFAULT 'USD',
    minio_path           TEXT,
    sla_commitments      JSONB NOT NULL DEFAULT '{}',  -- {uptime_pct: 99.9, response_time_hours: 4}
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_contracts                    IS 'Per-tenant vendor contract and SLA records; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN vendor_contracts.contract_type      IS 'Contract classification: msa, dpa, nda, sla, baa, order_form, amendment, or other.';
COMMENT ON COLUMN vendor_contracts.renewal_notice_days IS 'Number of days before expiry_date at which a renewal alert should be triggered.';
COMMENT ON COLUMN vendor_contracts.sla_commitments    IS 'JSONB map of SLA commitments, e.g. {uptime_pct: 99.9, response_time_hours: 4}.';
COMMENT ON COLUMN vendor_contracts.minio_path         IS 'Object storage path within the aegis-vendor-docs MinIO bucket for the signed contract file.';

ALTER TABLE vendor_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_contracts FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendor_contracts'
          AND policyname = 'vendor_contracts_tenant_isolation'
    ) THEN
        CREATE POLICY vendor_contracts_tenant_isolation
            ON vendor_contracts
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON vendor_contracts TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendor_contracts_tenant_vendor
    ON vendor_contracts (tenant_id, vendor_id);

-- Partial index covering only contracts with an expiry — used for renewal alerts.
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_tenant_expiry
    ON vendor_contracts (tenant_id, expiry_date)
    WHERE expiry_date IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 6. vendor_monitoring_events
--    Per-tenant append-only feed of continuous monitoring events sourced from
--    SecurityScorecard, BitSight, CVE feeds, news feeds, and manual inputs.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_monitoring_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    vendor_id    UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    event_source TEXT NOT NULL CHECK (event_source IN (
                     'securityscorecard','bitsight','news_feed','cve_feed',
                     'manual','trust_center_pull')),
    event_type   TEXT NOT NULL CHECK (event_type IN (
                     'score_change','breach_disclosed','cve_published',
                     'financial_distress','cert_change','news_alert','manual_note')),
    severity     TEXT NOT NULL CHECK (severity IN (
                     'critical','high','medium','low','info')),
    title        TEXT NOT NULL,
    description  TEXT,
    source_url   TEXT,
    raw_data     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_monitoring_events             IS 'Append-only per-tenant continuous monitoring event feed; INSERT and SELECT only — no UPDATE or DELETE.';
COMMENT ON COLUMN vendor_monitoring_events.event_source IS 'Origin of the monitoring signal: securityscorecard, bitsight, news_feed, cve_feed, manual, or trust_center_pull.';
COMMENT ON COLUMN vendor_monitoring_events.event_type   IS 'Classification of the event: score_change, breach_disclosed, cve_published, financial_distress, cert_change, news_alert, or manual_note.';
COMMENT ON COLUMN vendor_monitoring_events.severity     IS 'Severity level: critical, high, medium, low, or info.';
COMMENT ON COLUMN vendor_monitoring_events.raw_data     IS 'Original payload from the event source, preserved for audit and reprocessing.';

ALTER TABLE vendor_monitoring_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_monitoring_events FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'vendor_monitoring_events'
          AND policyname = 'vendor_monitoring_events_tenant_isolation'
    ) THEN
        CREATE POLICY vendor_monitoring_events_tenant_isolation
            ON vendor_monitoring_events
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable monitoring event log.
GRANT SELECT, INSERT ON vendor_monitoring_events TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_vendor_monitoring_events_tenant_vendor_time
    ON vendor_monitoring_events (tenant_id, vendor_id, created_at DESC);

-- Partial index covering only high-severity events — the dominant alert query.
CREATE INDEX IF NOT EXISTS idx_vendor_monitoring_events_tenant_high_severity
    ON vendor_monitoring_events (tenant_id, severity, created_at DESC)
    WHERE severity IN ('critical','high');

-- ---------------------------------------------------------------------------
-- 7. fourth_party_relationships
--    Per-tenant map of vendor → sub-processor relationships discovered via
--    questionnaire responses or automated trust-centre pulls.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fourth_party_relationships (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    parent_vendor_id    UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    sub_processor_name  TEXT NOT NULL,
    sub_processor_url   TEXT,
    relationship_type   TEXT NOT NULL DEFAULT 'sub_processor',
    risk_tier           TEXT CHECK (risk_tier IN ('critical','high','medium','low','unrated')),
    data_types_shared   TEXT[] NOT NULL DEFAULT '{}',
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    identified_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  fourth_party_relationships                  IS 'Per-tenant vendor sub-processor relationship map; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN fourth_party_relationships.parent_vendor_id IS 'The direct (third-party) vendor that uses this sub-processor.';
COMMENT ON COLUMN fourth_party_relationships.sub_processor_name IS 'Name of the downstream sub-processor as disclosed by the parent vendor.';
COMMENT ON COLUMN fourth_party_relationships.relationship_type  IS 'Nature of the relationship, e.g. sub_processor, hosting_provider, cdn, analytics.';
COMMENT ON COLUMN fourth_party_relationships.is_verified       IS 'TRUE once the sub-processor has been independently confirmed (e.g. via trust-centre pull or DPA review).';
COMMENT ON COLUMN fourth_party_relationships.data_types_shared IS 'Data classification labels shared with this sub-processor by the parent vendor.';

ALTER TABLE fourth_party_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE fourth_party_relationships FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'fourth_party_relationships'
          AND policyname = 'fourth_party_relationships_tenant_isolation'
    ) THEN
        CREATE POLICY fourth_party_relationships_tenant_isolation
            ON fourth_party_relationships
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON fourth_party_relationships TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_fourth_party_relationships_tenant_parent
    ON fourth_party_relationships (tenant_id, parent_vendor_id);

-- ---------------------------------------------------------------------------
-- 8. Cross-schema grants
--    Ensure aegis_app can still read platform-level framework tables
--    introduced in V012 — required for TPRM-to-framework control linkage.
-- ---------------------------------------------------------------------------
GRANT SELECT ON compliance_frameworks TO aegis_app;
GRANT SELECT ON framework_controls TO aegis_app;
