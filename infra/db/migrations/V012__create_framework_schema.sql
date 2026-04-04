-- =============================================================================
-- V012__create_framework_schema.sql
-- Project: Aegis 2026 – Sprint 8 – Compliance Framework Engine
--
-- Purpose:
--   Creates the Compliance Framework Engine schema: platform-level framework
--   and control definitions, cross-framework control crosswalk, and per-tenant
--   activation, evidence mapping, scoring, calendar, and gap-assessment tables.
--
-- Design:
--   * Fully idempotent — safe to run multiple times (CREATE ... IF NOT EXISTS,
--     DO $$ ... $$ guards on RLS policies checking pg_policies).
--   * Platform-level tables (compliance_frameworks, framework_controls,
--     control_crosswalk) carry no RLS — they are shared definitions readable
--     by all tenants.
--   * Per-tenant tables (tenant_frameworks, tenant_control_evidence,
--     compliance_scores, compliance_calendar_events, framework_gap_items)
--     enforce RLS via current_setting('app.tenant_id', TRUE)::UUID.
--   * compliance_scores is append-only: aegis_app receives INSERT, SELECT
--     only — no UPDATE or DELETE — to preserve immutable score snapshots.
--
-- Tables:
--   compliance_frameworks        – platform-level shared framework catalogue
--   framework_controls           – platform-level control definitions per framework
--   control_crosswalk            – platform-level cross-framework control mapping
--   tenant_frameworks            – per-tenant framework activation records
--   tenant_control_evidence      – per-tenant evidence-to-control mapping
--   compliance_scores            – per-tenant immutable compliance score snapshots
--   compliance_calendar_events   – per-tenant filing and review calendar
--   framework_gap_items          – per-tenant gap assessment results
--
-- Roles assumed to exist: aegis_app
-- Seed: 20 compliance frameworks inserted with ON CONFLICT DO NOTHING
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. compliance_frameworks
--    Platform-level catalogue of all supported compliance frameworks.
--    No RLS — shared definitions visible to all tenants.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_frameworks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,          -- e.g. 'soc2-type2', 'iso27001-2022'
    name            TEXT NOT NULL,                 -- e.g. 'SOC 2 Type II'
    version         TEXT NOT NULL,                 -- e.g. '2017', '2022'
    category        TEXT NOT NULL CHECK (category IN ('security','privacy','financial','operational','sustainability','ai','sector-specific')),
    description     TEXT NOT NULL,
    issuing_body    TEXT NOT NULL,                 -- e.g. 'AICPA', 'ISO', 'NIST', 'SEC'
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB NOT NULL DEFAULT '{}',   -- renewal_period_days, filing_required, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  compliance_frameworks              IS 'Platform-level catalogue of all supported compliance frameworks; shared across all tenants.';
COMMENT ON COLUMN compliance_frameworks.slug         IS 'URL-safe unique identifier, e.g. soc2-type2, iso27001-2022.';
COMMENT ON COLUMN compliance_frameworks.version      IS 'Published version or edition year of the framework.';
COMMENT ON COLUMN compliance_frameworks.category     IS 'High-level classification: security, privacy, financial, operational, sustainability, ai, or sector-specific.';
COMMENT ON COLUMN compliance_frameworks.issuing_body IS 'Organisation that publishes the framework, e.g. AICPA, ISO, NIST, SEC.';
COMMENT ON COLUMN compliance_frameworks.metadata     IS 'Flexible JSONB bag: renewal_period_days, filing_required, typical_audit_window_days, cost_tier, geographic_scope, mandatory_for, etc.';

GRANT SELECT ON compliance_frameworks TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_compliance_frameworks_category_active
    ON compliance_frameworks (category, is_active);

-- ---------------------------------------------------------------------------
-- 2. framework_controls
--    Platform-level control definitions for each framework.
--    No RLS — shared definitions visible to all tenants.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS framework_controls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id    UUID NOT NULL REFERENCES compliance_frameworks(id) ON DELETE CASCADE,
    control_id      TEXT NOT NULL,                 -- e.g. 'CC6.1', 'A.9.1.1', 'AC-2'
    domain          TEXT NOT NULL,                 -- e.g. 'Access Control', 'Cryptography'
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    guidance        TEXT,                          -- implementation guidance
    evidence_types  TEXT[] NOT NULL DEFAULT '{}', -- e.g. ['policy','screenshot','log_export']
    testing_frequency TEXT NOT NULL DEFAULT 'annual' CHECK (testing_frequency IN ('continuous','daily','weekly','monthly','quarterly','annual','on_change')),
    is_key_control  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (framework_id, control_id)
);

COMMENT ON TABLE  framework_controls                    IS 'Platform-level control definitions per framework; shared across all tenants.';
COMMENT ON COLUMN framework_controls.control_id         IS 'Published control identifier as specified by the issuing body, e.g. CC6.1, A.9.1.1, AC-2.';
COMMENT ON COLUMN framework_controls.domain             IS 'Control domain or family within the framework, e.g. Access Control, Cryptography.';
COMMENT ON COLUMN framework_controls.evidence_types     IS 'Array of evidence type identifiers expected to satisfy the control.';
COMMENT ON COLUMN framework_controls.testing_frequency  IS 'How often the control must be tested: continuous, daily, weekly, monthly, quarterly, annual, or on_change.';
COMMENT ON COLUMN framework_controls.is_key_control     IS 'True for controls that are high-priority / key controls in the framework.';

GRANT SELECT ON framework_controls TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_framework_controls_framework_domain
    ON framework_controls (framework_id, domain);

CREATE INDEX IF NOT EXISTS idx_framework_controls_key
    ON framework_controls (framework_id, is_key_control)
    WHERE is_key_control = TRUE;

-- ---------------------------------------------------------------------------
-- 3. control_crosswalk
--    Platform-level mapping of equivalent controls across frameworks.
--    No RLS — shared definitions visible to all tenants.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS control_crosswalk (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_control_id   UUID NOT NULL REFERENCES framework_controls(id) ON DELETE CASCADE,
    target_control_id   UUID NOT NULL REFERENCES framework_controls(id) ON DELETE CASCADE,
    equivalence_type    TEXT NOT NULL CHECK (equivalence_type IN ('full','partial','related')),
    notes               TEXT,
    UNIQUE (source_control_id, target_control_id)
);

COMMENT ON TABLE  control_crosswalk                    IS 'Cross-framework control equivalence mapping; platform-level shared reference.';
COMMENT ON COLUMN control_crosswalk.equivalence_type   IS 'Degree of equivalence: full (completely equivalent), partial (overlapping), related (thematically related).';

GRANT SELECT ON control_crosswalk TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_control_crosswalk_source
    ON control_crosswalk (source_control_id);

CREATE INDEX IF NOT EXISTS idx_control_crosswalk_target
    ON control_crosswalk (target_control_id);

-- ---------------------------------------------------------------------------
-- 4. tenant_frameworks
--    Per-tenant record of which compliance frameworks have been activated.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_frameworks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    framework_id     UUID NOT NULL REFERENCES compliance_frameworks(id),
    activated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target_cert_date TIMESTAMPTZ,
    scope_notes      TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (tenant_id, framework_id)
);

COMMENT ON TABLE  tenant_frameworks                    IS 'Per-tenant framework activation records; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN tenant_frameworks.target_cert_date   IS 'Desired certification or audit completion date for planning purposes.';
COMMENT ON COLUMN tenant_frameworks.scope_notes        IS 'Free-text description of the scope boundaries for this framework activation.';

ALTER TABLE tenant_frameworks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_frameworks FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'tenant_frameworks'
          AND policyname = 'tenant_frameworks_tenant_isolation'
    ) THEN
        CREATE POLICY tenant_frameworks_tenant_isolation
            ON tenant_frameworks
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON tenant_frameworks TO aegis_app;

-- ---------------------------------------------------------------------------
-- 5. tenant_control_evidence
--    Per-tenant mapping of evidence records to framework controls, with
--    current pass/fail status and review scheduling.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_control_evidence (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    framework_control_id UUID NOT NULL REFERENCES framework_controls(id),
    evidence_record_id   UUID,                      -- FK to evidence_records (soft reference)
    status               TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','passing','failing','not_applicable','exception')),
    last_tested_at       TIMESTAMPTZ,
    next_review_at       TIMESTAMPTZ,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  tenant_control_evidence                    IS 'Per-tenant evidence-to-control mapping with current status; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN tenant_control_evidence.evidence_record_id IS 'Soft foreign key into evidence_records; NULL until evidence is linked.';
COMMENT ON COLUMN tenant_control_evidence.status             IS 'Control status: not_started, in_progress, passing, failing, not_applicable, or exception.';
COMMENT ON COLUMN tenant_control_evidence.next_review_at     IS 'Scheduled date for the next evidence review or test.';

ALTER TABLE tenant_control_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_control_evidence FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'tenant_control_evidence'
          AND policyname = 'tenant_control_evidence_tenant_isolation'
    ) THEN
        CREATE POLICY tenant_control_evidence_tenant_isolation
            ON tenant_control_evidence
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON tenant_control_evidence TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_tenant_control_evidence_tenant_control
    ON tenant_control_evidence (tenant_id, framework_control_id);

CREATE INDEX IF NOT EXISTS idx_tenant_control_evidence_tenant_status
    ON tenant_control_evidence (tenant_id, status);

-- ---------------------------------------------------------------------------
-- 6. compliance_scores
--    Per-tenant immutable compliance score snapshots.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_scores (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    framework_id         UUID NOT NULL REFERENCES compliance_frameworks(id),
    score_pct            NUMERIC(5,2) NOT NULL,         -- 0.00 to 100.00
    passing_controls     INTEGER NOT NULL,
    failing_controls     INTEGER NOT NULL,
    not_started_controls INTEGER NOT NULL,
    total_controls       INTEGER NOT NULL,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  compliance_scores                       IS 'Immutable per-tenant compliance score snapshots; INSERT and SELECT only — no UPDATE or DELETE.';
COMMENT ON COLUMN compliance_scores.score_pct             IS 'Overall compliance percentage in [0.00, 100.00].';
COMMENT ON COLUMN compliance_scores.passing_controls      IS 'Count of controls in passing status at snapshot time.';
COMMENT ON COLUMN compliance_scores.failing_controls      IS 'Count of controls in failing status at snapshot time.';
COMMENT ON COLUMN compliance_scores.not_started_controls  IS 'Count of controls not yet addressed at snapshot time.';
COMMENT ON COLUMN compliance_scores.total_controls        IS 'Total number of controls in scope for this framework activation.';

ALTER TABLE compliance_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_scores FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'compliance_scores'
          AND policyname = 'compliance_scores_tenant_isolation'
    ) THEN
        CREATE POLICY compliance_scores_tenant_isolation
            ON compliance_scores
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable score snapshots.
GRANT SELECT, INSERT ON compliance_scores TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_compliance_scores_tenant_framework_time
    ON compliance_scores (tenant_id, framework_id, computed_at DESC);

-- ---------------------------------------------------------------------------
-- 7. compliance_calendar_events
--    Per-tenant compliance calendar: filing deadlines, cert renewals,
--    periodic control reviews, and audit windows.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_calendar_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    framework_id UUID NOT NULL REFERENCES compliance_frameworks(id),
    event_type   TEXT NOT NULL CHECK (event_type IN ('filing_deadline','cert_renewal','control_review','periodic_activity','audit_window')),
    title        TEXT NOT NULL,
    due_date     DATE NOT NULL,
    description  TEXT,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  compliance_calendar_events             IS 'Per-tenant compliance calendar events; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN compliance_calendar_events.event_type  IS 'Event category: filing_deadline, cert_renewal, control_review, periodic_activity, or audit_window.';
COMMENT ON COLUMN compliance_calendar_events.due_date    IS 'Wall-clock date by which the event must be completed.';

ALTER TABLE compliance_calendar_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_calendar_events FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'compliance_calendar_events'
          AND policyname = 'compliance_calendar_events_tenant_isolation'
    ) THEN
        CREATE POLICY compliance_calendar_events_tenant_isolation
            ON compliance_calendar_events
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON compliance_calendar_events TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_compliance_calendar_events_tenant_due
    ON compliance_calendar_events (tenant_id, due_date);

-- Partial index covering only open events — the dominant query pattern.
CREATE INDEX IF NOT EXISTS idx_compliance_calendar_events_tenant_open
    ON compliance_calendar_events (tenant_id, due_date)
    WHERE is_completed = FALSE;

-- ---------------------------------------------------------------------------
-- 8. framework_gap_items
--    Per-tenant gap assessment results identifying control deficiencies
--    and remediation actions.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS framework_gap_items (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    framework_id         UUID NOT NULL REFERENCES compliance_frameworks(id),
    framework_control_id UUID NOT NULL REFERENCES framework_controls(id),
    gap_severity         TEXT NOT NULL CHECK (gap_severity IN ('critical','high','medium','low')),
    gap_description      TEXT NOT NULL,
    remediation_steps    TEXT,
    identified_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at          TIMESTAMPTZ
);

COMMENT ON TABLE  framework_gap_items                     IS 'Per-tenant gap assessment results; RLS enforced by app.tenant_id.';
COMMENT ON COLUMN framework_gap_items.gap_severity        IS 'Severity of the identified gap: critical, high, medium, or low.';
COMMENT ON COLUMN framework_gap_items.remediation_steps   IS 'Free-text description of recommended remediation actions.';
COMMENT ON COLUMN framework_gap_items.resolved_at         IS 'Timestamp when the gap was closed; NULL while still open.';

ALTER TABLE framework_gap_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE framework_gap_items FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'framework_gap_items'
          AND policyname = 'framework_gap_items_tenant_isolation'
    ) THEN
        CREATE POLICY framework_gap_items_tenant_isolation
            ON framework_gap_items
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON framework_gap_items TO aegis_app;

-- ---------------------------------------------------------------------------
-- 9. Seed: 20 compliance frameworks
--    ON CONFLICT DO NOTHING ensures idempotency.
-- ---------------------------------------------------------------------------
INSERT INTO compliance_frameworks (slug, name, version, category, issuing_body, description, metadata) VALUES

('soc2-type2',
 'SOC 2 Type II',
 '2017',
 'security',
 'AICPA',
 'Service Organization Control 2 Type II — Trust Services Criteria evaluation over a defined period',
 '{"renewal_period_days": 365, "filing_required": false, "typical_audit_window_days": 180, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}'),

('soc2-type1',
 'SOC 2 Type I',
 '2017',
 'security',
 'AICPA',
 'Service Organization Control 2 Type I — Trust Services Criteria evaluation at a point in time',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 0, "cost_tier": "medium", "geographic_scope": "global", "mandatory_for": []}'),

('iso27001-2022',
 'ISO/IEC 27001:2022',
 '2022',
 'security',
 'ISO',
 'Information security management systems — Requirements (2022 revision)',
 '{"renewal_period_days": 1095, "filing_required": false, "typical_audit_window_days": 30, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}'),

('hipaa',
 'HIPAA Security Rule',
 '2013',
 'sector-specific',
 'HHS',
 'Health Insurance Portability and Accountability Act Security Rule — safeguards for electronic protected health information',
 '{"renewal_period_days": 365, "filing_required": false, "typical_audit_window_days": 90, "cost_tier": "medium", "geographic_scope": "us", "mandatory_for": ["covered_entity", "business_associate"]}'),

('pci-dss-4',
 'PCI DSS v4.0',
 '4.0',
 'sector-specific',
 'PCI SSC',
 'Payment Card Industry Data Security Standard version 4.0 — requirements for entities that store, process, or transmit cardholder data',
 '{"renewal_period_days": 365, "filing_required": true, "typical_audit_window_days": 60, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": ["merchant", "service_provider"]}'),

('gdpr',
 'GDPR',
 '2018',
 'privacy',
 'European Parliament',
 'General Data Protection Regulation — EU regulation on data protection and privacy for individuals within the European Union',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 90, "cost_tier": "high", "geographic_scope": "eu", "mandatory_for": ["eu_data_processor", "eu_data_controller"]}'),

('ccpa',
 'CCPA/CPRA',
 '2023',
 'privacy',
 'State of California',
 'California Consumer Privacy Act and California Privacy Rights Act — consumer privacy rights for California residents',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 60, "cost_tier": "medium", "geographic_scope": "us_california", "mandatory_for": ["qualifying_business"]}'),

('nist-csf-2',
 'NIST Cybersecurity Framework 2.0',
 '2.0',
 'security',
 'NIST',
 'NIST Cybersecurity Framework version 2.0 — voluntary guidance for managing cybersecurity risk across six functions: Govern, Identify, Protect, Detect, Respond, Recover',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 60, "cost_tier": "low", "geographic_scope": "global", "mandatory_for": []}'),

('nist-800-53-r5',
 'NIST SP 800-53 Rev 5',
 'Rev 5',
 'security',
 'NIST',
 'Security and Privacy Controls for Information Systems and Organizations — comprehensive control catalogue for federal and non-federal systems',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 90, "cost_tier": "medium", "geographic_scope": "global", "mandatory_for": ["us_federal_agency"]}'),

('fedramp-moderate',
 'FedRAMP Moderate',
 '2024',
 'security',
 'GSA',
 'Federal Risk and Authorization Management Program at Moderate impact level — standardised security assessment for cloud services used by US federal agencies',
 '{"renewal_period_days": 365, "filing_required": true, "typical_audit_window_days": 180, "cost_tier": "high", "geographic_scope": "us", "mandatory_for": ["federal_cloud_service_provider"]}'),

('cis-controls-v8',
 'CIS Controls v8',
 '8.0',
 'security',
 'CIS',
 'Center for Internet Security Critical Security Controls version 8 — prioritised set of actions to protect against the most prevalent cyber attacks',
 '{"renewal_period_days": null, "filing_required": false, "typical_audit_window_days": 60, "cost_tier": "low", "geographic_scope": "global", "mandatory_for": []}'),

('cmmc-2',
 'CMMC Level 2',
 '2.0',
 'security',
 'DoD',
 'Cybersecurity Maturity Model Certification Level 2 — advanced cyber hygiene practices for defence contractors handling Controlled Unclassified Information',
 '{"renewal_period_days": 1095, "filing_required": true, "typical_audit_window_days": 90, "cost_tier": "high", "geographic_scope": "us", "mandatory_for": ["dod_contractor_cui"]}'),

('sox-itgc',
 'SOX IT General Controls',
 '2024',
 'financial',
 'PCAOB',
 'Sarbanes-Oxley Act IT General Controls — change management, logical access, computer operations, and financial reporting controls for public companies',
 '{"renewal_period_days": 365, "filing_required": true, "typical_audit_window_days": 90, "cost_tier": "high", "geographic_scope": "us", "mandatory_for": ["public_company_sec_filer"]}'),

('dora',
 'DORA',
 '2025',
 'operational',
 'European Parliament',
 'Digital Operational Resilience Act — ICT risk management, incident reporting, resilience testing, and third-party risk requirements for EU financial entities',
 '{"renewal_period_days": 365, "filing_required": false, "typical_audit_window_days": 90, "cost_tier": "high", "geographic_scope": "eu", "mandatory_for": ["eu_financial_entity", "ict_third_party_provider"]}'),

('swift-csp',
 'SWIFT Customer Security Programme',
 'v2024',
 'sector-specific',
 'SWIFT',
 'SWIFT Customer Security Controls Framework v2024 — mandatory and advisory security controls for all SWIFT users',
 '{"renewal_period_days": 365, "filing_required": true, "typical_audit_window_days": 60, "cost_tier": "medium", "geographic_scope": "global", "mandatory_for": ["swift_member"]}'),

('iso27701',
 'ISO/IEC 27701:2019',
 '2019',
 'privacy',
 'ISO',
 'Extension to ISO/IEC 27001 and 27002 for privacy information management — PIMS requirements and guidance',
 '{"renewal_period_days": 1095, "filing_required": false, "typical_audit_window_days": 30, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}'),

('iso42001-ai',
 'ISO/IEC 42001:2023',
 '2023',
 'ai',
 'ISO',
 'Artificial Intelligence Management System — requirements and guidance for establishing, implementing, and continually improving an AI management system',
 '{"renewal_period_days": 1095, "filing_required": false, "typical_audit_window_days": 30, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}'),

('nis2',
 'NIS2 Directive',
 '2022',
 'security',
 'European Parliament',
 'Network and Information Security Directive 2 — cybersecurity obligations for essential and important entities in the EU, including incident reporting and supply chain security',
 '{"renewal_period_days": 365, "filing_required": false, "typical_audit_window_days": 60, "cost_tier": "medium", "geographic_scope": "eu", "mandatory_for": ["eu_essential_entity", "eu_important_entity"]}'),

('hitrust-csf',
 'HITRUST CSF v11',
 '11.0',
 'sector-specific',
 'HITRUST Alliance',
 'Health Information Trust Alliance Common Security Framework version 11 — comprehensive risk-based framework for healthcare organisations',
 '{"renewal_period_days": 730, "filing_required": false, "typical_audit_window_days": 90, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}'),

('ssae18',
 'SSAE 18 / SOC 1',
 '2017',
 'financial',
 'AICPA',
 'Statement on Standards for Attestation Engagements No. 18 — AT-C Section 320 reporting on controls at a service organisation relevant to user entities internal control over financial reporting',
 '{"renewal_period_days": 365, "filing_required": false, "typical_audit_window_days": 180, "cost_tier": "high", "geographic_scope": "global", "mandatory_for": []}')

ON CONFLICT (slug) DO NOTHING;
