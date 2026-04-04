-- =============================================================================
-- V010__create_reporting_schema.sql
-- Project: Aegis 2026 – Sprint 6 – Immutable Output & Reporting
--
-- Purpose:
--   Creates the reporting schema: XBRL taxonomy registry, per-tenant report
--   templates, generated export records, and PAdES digital signature records.
--
-- Design:
--   * Fully idempotent — safe to run multiple times (CREATE ... IF NOT EXISTS,
--     DO $$ ... $$ guards on RLS policies, INSERT ... ON CONFLICT DO NOTHING).
--   * RLS enforced on all tenant-scoped tables using the JWT claim approach
--     already established in prior migrations (current_setting('app.tenant_id')).
--   * xbrl_taxonomies is platform-level (no tenant column, no RLS).
--
-- Tables:
--   xbrl_taxonomies     – registered XBRL taxonomy references (platform-level)
--   report_templates    – per-tenant custom report templates
--   report_exports      – generated report export records
--   digital_signatures  – PAdES digital signatures applied to PDF/A exports
--
-- Roles assumed to exist: aegis_app
-- Tables assumed to exist: tenants(tenant_id UUID), users(user_id UUID)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. xbrl_taxonomies
--    Platform-level registry of known XBRL taxonomy namespaces.
--    No tenant scoping; no RLS.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS xbrl_taxonomies (
    taxonomy_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    taxonomy_name    TEXT        NOT NULL,
    taxonomy_version TEXT        NOT NULL,
    namespace_uri    TEXT        NOT NULL UNIQUE,
    schema_url       TEXT        NOT NULL,
    description      TEXT,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  xbrl_taxonomies                  IS 'Platform-level registry of XBRL taxonomy namespace definitions.';
COMMENT ON COLUMN xbrl_taxonomies.taxonomy_name    IS 'Short human-readable name, e.g. us-gaap-2023.';
COMMENT ON COLUMN xbrl_taxonomies.namespace_uri    IS 'Canonical XML namespace URI — globally unique.';
COMMENT ON COLUMN xbrl_taxonomies.schema_url       IS 'URL to the taxonomy XSD entry-point document.';

-- Seed well-known taxonomies (idempotent on namespace_uri UNIQUE constraint).
INSERT INTO xbrl_taxonomies
    (taxonomy_name, taxonomy_version, namespace_uri, schema_url, description)
VALUES
    (
        'us-gaap-2023',
        '2023',
        'http://fasb.org/us-gaap/2023',
        'https://xbrl.fasb.org/us-gaap/2023/elts/us-gaap-2023.xsd',
        'US GAAP 2023 taxonomy'
    ),
    (
        'ifrs-full-2023',
        '2023',
        'http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full',
        'https://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full-cor_2023-03-23.xsd',
        'IFRS full 2023 taxonomy'
    ),
    (
        'gl-plt-2016',
        '2016',
        'http://www.xbrl.org/taxonomy/int/gl/plt/2016-12-01',
        'https://taxonomies.xbrl.org/int/gl/plt/2016-12-01/gl-plt-entire-2016-12-01.xsd',
        'XBRL GL Platform 2016'
    ),
    (
        'xbrli-2003',
        '2003',
        'http://www.xbrl.org/2003/instance',
        'https://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd',
        'XBRL 2.1 instance schema'
    )
ON CONFLICT (namespace_uri) DO NOTHING;

-- Grants: read-only for the application role; no writes needed at runtime.
GRANT SELECT ON xbrl_taxonomies TO aegis_app;

-- ---------------------------------------------------------------------------
-- 2. report_templates
--    Per-tenant custom report template configuration.
--    RLS: tenants may only see and modify their own templates.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_templates (
    template_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL REFERENCES tenants(tenant_id),
    template_name   TEXT        NOT NULL,
    format          TEXT        NOT NULL
                                CHECK (format IN ('xbrl','ixbrl','saft','gifi','pdf_a')),
    framework       TEXT        NOT NULL,  -- 'soc2', 'iso27001', 'pci_dss', 'tax', 'custom'
    template_config JSONB       NOT NULL DEFAULT '{}',
    is_default      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, template_name)
);

COMMENT ON TABLE  report_templates                  IS 'Per-tenant named report template definitions with format-specific configuration.';
COMMENT ON COLUMN report_templates.format           IS 'Output format: xbrl, ixbrl, saft, gifi, or pdf_a.';
COMMENT ON COLUMN report_templates.framework        IS 'Compliance framework this template targets, e.g. soc2, iso27001, pci_dss, tax, custom.';
COMMENT ON COLUMN report_templates.template_config  IS 'Format-specific configuration blob (taxonomy references, stylesheet paths, etc.).';
COMMENT ON COLUMN report_templates.is_default       IS 'When true, this template is automatically selected for new export requests of the same format/framework.';

-- Enable RLS.
ALTER TABLE report_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_templates FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'report_templates'
          AND policyname = 'report_templates_tenant_isolation'
    ) THEN
        CREATE POLICY report_templates_tenant_isolation
            ON report_templates
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON report_templates TO aegis_app;

-- ---------------------------------------------------------------------------
-- 3. report_exports
--    One row per generated report export.  Tracks generation lifecycle
--    (pending → generating → completed | failed), MinIO storage path,
--    SHA-256 integrity checksum, and linkage to source narratives/evidence.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_exports (
    export_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL REFERENCES tenants(tenant_id),
    template_id       UUID        REFERENCES report_templates(template_id),
    format            TEXT        NOT NULL
                                  CHECK (format IN ('xbrl','ixbrl','saft','gifi','pdf_a')),
    framework         TEXT        NOT NULL,
    period_start      DATE        NOT NULL,
    period_end        DATE        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','generating','completed','failed')),
    storage_path      TEXT,                    -- MinIO object path; set when status = 'completed'
    file_size_bytes   BIGINT,
    checksum_sha256   BYTEA,                   -- SHA-256 digest of the generated file
    generation_log    TEXT,                    -- error / progress messages
    narrative_ids     UUID[],                  -- audit narrative UUIDs included in this report
    evidence_count    INTEGER     NOT NULL DEFAULT 0,
    generated_by      UUID        REFERENCES users(user_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

COMMENT ON TABLE  report_exports                   IS 'Generated report export records; one row per export job lifecycle.';
COMMENT ON COLUMN report_exports.storage_path      IS 'MinIO object path within the aegis-reports bucket; populated on completion.';
COMMENT ON COLUMN report_exports.checksum_sha256   IS 'Raw 32-byte SHA-256 digest of the generated file for integrity verification.';
COMMENT ON COLUMN report_exports.narrative_ids     IS 'Array of audit narrative UUIDs whose content is embedded in this report.';
COMMENT ON COLUMN report_exports.evidence_count    IS 'Count of distinct evidence items referenced during report generation.';
COMMENT ON COLUMN report_exports.generation_log    IS 'Free-text progress and error log produced by the reporting service worker.';

-- Enable RLS.
ALTER TABLE report_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_exports FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'report_exports'
          AND policyname = 'report_exports_tenant_isolation'
    ) THEN
        CREATE POLICY report_exports_tenant_isolation
            ON report_exports
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON report_exports TO aegis_app;

-- Indexes for common query patterns.
CREATE INDEX IF NOT EXISTS idx_report_exports_status
    ON report_exports (tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_report_exports_period
    ON report_exports (tenant_id, framework, period_start, period_end);

-- ---------------------------------------------------------------------------
-- 4. digital_signatures
--    PAdES digital signatures applied to completed PDF/A report exports.
--    Stores the DER-encoded CMS signature blob, signer certificate
--    fingerprint, optional OCSP staple, and RFC 3161 timestamp authority info.
--    Cascades on export deletion to avoid orphaned signature records.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS digital_signatures (
    signature_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    export_id          UUID        NOT NULL REFERENCES report_exports(export_id) ON DELETE CASCADE,
    tenant_id          UUID        NOT NULL REFERENCES tenants(tenant_id),
    signer_cert_sha256 BYTEA       NOT NULL,   -- SHA-256 of the signing certificate (DER)
    signer_dn          TEXT        NOT NULL,   -- X.500 Distinguished Name of the signer
    signing_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signature_type     TEXT        NOT NULL DEFAULT 'PAdES-B-LTA'
                                   CHECK (signature_type IN
                                          ('PAdES-B-B','PAdES-B-T','PAdES-B-LT','PAdES-B-LTA')),
    tsa_url            TEXT,                   -- RFC 3161 timestamp authority URL used
    signature_bytes    BYTEA       NOT NULL,   -- DER-encoded CMS SignedData structure
    ocsp_response      BYTEA,                  -- Stapled DER-encoded OCSP response
    validation_status  TEXT        NOT NULL DEFAULT 'valid'
                                   CHECK (validation_status IN
                                          ('valid','invalid','revoked','unknown'))
);

COMMENT ON TABLE  digital_signatures                      IS 'PAdES digital signatures applied to PDF/A report exports; one row per signature event.';
COMMENT ON COLUMN digital_signatures.signer_cert_sha256   IS 'Raw 32-byte SHA-256 fingerprint of the signing certificate (DER-encoded).';
COMMENT ON COLUMN digital_signatures.signer_dn            IS 'Full X.500 Distinguished Name string of the certificate subject.';
COMMENT ON COLUMN digital_signatures.signature_type       IS 'PAdES conformance level: B-B (baseline), B-T (with timestamp), B-LT (with revocation data), B-LTA (long-term archival).';
COMMENT ON COLUMN digital_signatures.tsa_url              IS 'RFC 3161 compliant timestamp authority URL used when embedding the signature timestamp token.';
COMMENT ON COLUMN digital_signatures.signature_bytes      IS 'Complete DER-encoded CMS SignedData structure as written into the PDF ByteRange.';
COMMENT ON COLUMN digital_signatures.ocsp_response        IS 'Stapled DER-encoded OCSP response for the signing certificate, embedded for B-LT/B-LTA validation.';
COMMENT ON COLUMN digital_signatures.validation_status    IS 'Current validity state of the signature; updated by the periodic re-validation job.';

-- Enable RLS.
ALTER TABLE digital_signatures ENABLE ROW LEVEL SECURITY;
ALTER TABLE digital_signatures FORCE ROW LEVEL SECURITY;

-- Idempotent policy guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'digital_signatures'
          AND policyname = 'digital_signatures_tenant_isolation'
    ) THEN
        CREATE POLICY digital_signatures_tenant_isolation
            ON digital_signatures
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- INSERT only (no UPDATE) — signatures are immutable once written.
GRANT SELECT, INSERT ON digital_signatures TO aegis_app;
