-- =============================================================================
-- V023__create_mobile_field_audit_schema.sql
-- Sprint 19: Mobile Field Audit & Offline Sync
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. field_audit_template_types  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_template_types (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_key     TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description  TEXT,
    icon         TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO field_audit_template_types
    (type_key, display_name, description, icon)
VALUES
    ('safety_inspection', 'Safety Inspection',    'Physical safety and compliance walkthrough',              'shield'),
    ('it_asset_audit',    'IT Asset Audit',        'Hardware/software inventory and compliance check',        'server'),
    ('access_control',    'Access Control Review', 'Physical and logical access verification',                'lock'),
    ('data_center',       'Data Center Walkthrough','Environmental controls and physical security',           'database'),
    ('vendor_site_visit', 'Vendor Site Visit',     'On-site vendor assessment and verification',             'truck'),
    ('branch_audit',      'Branch/Location Audit', 'General operational audit at physical location',         'map-pin')
ON CONFLICT (type_key) DO NOTHING;

GRANT SELECT ON field_audit_template_types TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. field_audit_templates  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_templates (
    id                         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    template_type_id           UUID    REFERENCES field_audit_template_types(id),
    template_key               TEXT    NOT NULL UNIQUE,
    display_name               TEXT    NOT NULL,
    description                TEXT,
    version                    TEXT    DEFAULT '1.0',
    estimated_duration_minutes INTEGER DEFAULT 60,
    requires_photo_evidence    BOOLEAN DEFAULT FALSE,
    requires_signature         BOOLEAN DEFAULT FALSE,
    requires_gps               BOOLEAN DEFAULT FALSE,
    section_count              INTEGER DEFAULT 0,
    question_count             INTEGER DEFAULT 0,
    is_active                  BOOLEAN DEFAULT TRUE,
    created_at                 TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO field_audit_templates
    (template_key, display_name, description, estimated_duration_minutes, requires_photo_evidence, requires_signature, requires_gps)
VALUES
    ('safety-walkthrough-v1',    'Safety Walkthrough Checklist',    'Standard facility safety inspection',              60, TRUE,  TRUE,  TRUE),
    ('it-asset-inventory-v1',    'IT Asset Inventory Check',        'Physical IT asset verification and tagging',       45, TRUE,  FALSE, TRUE),
    ('access-control-review-v1', 'Access Control Review',           'Physical and logical access point verification',   30, TRUE,  TRUE,  FALSE)
ON CONFLICT (template_key) DO NOTHING;

GRANT SELECT ON field_audit_templates TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. field_audit_template_questions  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_template_questions (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id          UUID    NOT NULL REFERENCES field_audit_templates(id),
    section_name         TEXT    NOT NULL,
    sequence_number      INTEGER NOT NULL,
    question_text        TEXT    NOT NULL,
    question_type        TEXT    NOT NULL DEFAULT 'yes_no'
                                 CHECK (question_type IN ('yes_no','multiple_choice','text','numeric','photo','signature','gps_location','rating')),
    options              JSONB   DEFAULT '[]',
    is_required          BOOLEAN DEFAULT TRUE,
    requires_photo_if    TEXT,
    requires_comment_if  TEXT,
    risk_weight          INTEGER DEFAULT 1 CHECK (risk_weight >= 1 AND risk_weight <= 5),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Seed 12 questions for the safety-walkthrough-v1 template
-- Section: Fire Safety (seq 1–4)
INSERT INTO field_audit_template_questions
    (template_id, section_name, sequence_number, question_text, question_type, is_required, requires_photo_if, requires_comment_if, risk_weight)
SELECT
    t.id,
    q.section_name,
    q.sequence_number,
    q.question_text,
    q.question_type,
    q.is_required,
    q.requires_photo_if,
    q.requires_comment_if,
    q.risk_weight
FROM field_audit_templates t
CROSS JOIN (VALUES
    ('Fire Safety',      1, 'Are fire extinguishers in-date and accessible?',              'yes_no',         TRUE,  'no',  'no',  5),
    ('Fire Safety',      2, 'Are fire exit routes clear and unobstructed?',                 'yes_no',         TRUE,  'no',  'no',  5),
    ('Fire Safety',      3, 'How many fire extinguishers are present in this area?',        'numeric',        TRUE,  NULL,  NULL,  2),
    ('Fire Safety',      4, 'Fire safety rating for this area',                             'rating',         FALSE, NULL,  NULL,  3),
    ('Electrical Safety',5, 'Are all electrical panels labeled and accessible?',            'yes_no',         TRUE,  'no',  'no',  4),
    ('Electrical Safety',6, 'Are extension cords used appropriately (no daisy-chaining)?', 'yes_no',         TRUE,  'no',  'no',  3),
    ('Electrical Safety',7, 'Date of last electrical inspection',                           'text',           FALSE, NULL,  NULL,  2),
    ('Electrical Safety',8, 'Capture photo of main electrical panel',                       'photo',          TRUE,  NULL,  NULL,  2),
    ('General Safety',   9, 'Are aisles and walkways free of obstructions?',                'yes_no',         TRUE,  'no',  'no',  3),
    ('Electrical Safety',10,'Is PPE available and properly stored?',                        'yes_no',         TRUE,  'no',  'no',  3),
    ('General Safety',   11,'Record GPS location of inspection point',                      'gps_location',   TRUE,  NULL,  NULL,  1),
    ('General Safety',   12,'Overall facility safety assessment',                           'multiple_choice',FALSE, NULL,  NULL,  2)
) AS q(section_name, sequence_number, question_text, question_type, is_required, requires_photo_if, requires_comment_if, risk_weight)
WHERE t.template_key = 'safety-walkthrough-v1';

-- Set options for multiple_choice question (seq 12)
UPDATE field_audit_template_questions
SET options = '["Satisfactory","Needs Improvement","Unsatisfactory"]'::JSONB
WHERE template_id = (SELECT id FROM field_audit_templates WHERE template_key = 'safety-walkthrough-v1')
  AND sequence_number = 12;

CREATE INDEX IF NOT EXISTS idx_field_audit_template_questions_template_id
    ON field_audit_template_questions (template_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_template_questions_section_name
    ON field_audit_template_questions (section_name);

GRANT SELECT ON field_audit_template_questions TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. field_audit_assignments  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_assignments (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID    NOT NULL,
    engagement_id       UUID,
    template_id         UUID    NOT NULL REFERENCES field_audit_templates(id),
    assigned_to_email   TEXT    NOT NULL,
    assigned_to_name    TEXT,
    location_name       TEXT    NOT NULL,
    location_address    TEXT,
    scheduled_date      DATE    NOT NULL,
    due_date            DATE    NOT NULL,
    priority            TEXT    NOT NULL DEFAULT 'medium'
                                CHECK (priority IN ('critical','high','medium','low')),
    status              TEXT    NOT NULL DEFAULT 'assigned'
                                CHECK (status IN ('assigned','in_progress','completed','overdue','cancelled')),
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_audit_assignments_tenant_id
    ON field_audit_assignments (tenant_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_assignments_assigned_to_email
    ON field_audit_assignments (assigned_to_email);

CREATE INDEX IF NOT EXISTS idx_field_audit_assignments_status
    ON field_audit_assignments (status);

CREATE INDEX IF NOT EXISTS idx_field_audit_assignments_scheduled_date
    ON field_audit_assignments (scheduled_date);

CREATE INDEX IF NOT EXISTS idx_field_audit_assignments_due_date
    ON field_audit_assignments (due_date);

ALTER TABLE field_audit_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_audit_assignments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_field_audit_assignments_tenant'
          AND tablename  = 'field_audit_assignments'
    ) THEN
        CREATE POLICY rls_field_audit_assignments_tenant
            ON field_audit_assignments
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON field_audit_assignments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. field_audits  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audits (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID    NOT NULL,
    assignment_id        UUID    REFERENCES field_audit_assignments(id),
    template_id          UUID    NOT NULL REFERENCES field_audit_templates(id),
    auditor_email        TEXT    NOT NULL,
    auditor_name         TEXT,
    location_name        TEXT    NOT NULL,
    status               TEXT    NOT NULL DEFAULT 'in_progress'
                                 CHECK (status IN ('in_progress','completed','submitted','synced')),
    started_at           TIMESTAMPTZ DEFAULT NOW(),
    completed_at         TIMESTAMPTZ,
    submitted_at         TIMESTAMPTZ,
    synced_at            TIMESTAMPTZ,
    device_id            TEXT,
    client_created_at    TIMESTAMPTZ,
    gps_latitude         NUMERIC(10,7),
    gps_longitude        NUMERIC(10,7),
    gps_accuracy_meters  NUMERIC(6,2),
    overall_score        NUMERIC(5,2),
    risk_level           TEXT    CHECK (risk_level IN ('critical','high','medium','low','n_a')),
    total_findings       INTEGER DEFAULT 0,
    auditor_signature    TEXT,
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_audits_tenant_id
    ON field_audits (tenant_id);

CREATE INDEX IF NOT EXISTS idx_field_audits_assignment_id
    ON field_audits (assignment_id);

CREATE INDEX IF NOT EXISTS idx_field_audits_auditor_email
    ON field_audits (auditor_email);

CREATE INDEX IF NOT EXISTS idx_field_audits_status
    ON field_audits (status);

CREATE INDEX IF NOT EXISTS idx_field_audits_client_created_at
    ON field_audits (client_created_at);

ALTER TABLE field_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_audits FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_field_audits_tenant'
          AND tablename  = 'field_audits'
    ) THEN
        CREATE POLICY rls_field_audits_tenant
            ON field_audits
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON field_audits TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. field_audit_responses  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_responses (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID    NOT NULL,
    field_audit_id      UUID    NOT NULL REFERENCES field_audits(id),
    question_id         UUID    NOT NULL REFERENCES field_audit_template_questions(id),
    response_value      TEXT,
    numeric_response    NUMERIC(10,2),
    boolean_response    BOOLEAN,
    gps_latitude        NUMERIC(10,7),
    gps_longitude       NUMERIC(10,7),
    comment             TEXT,
    is_finding          BOOLEAN DEFAULT FALSE,
    finding_severity    TEXT    CHECK (finding_severity IN ('critical','high','medium','low')),
    photo_references    TEXT[],
    client_answered_at  TIMESTAMPTZ,
    sync_id             TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (field_audit_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_field_audit_responses_tenant_id
    ON field_audit_responses (tenant_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_responses_field_audit_id
    ON field_audit_responses (field_audit_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_responses_question_id
    ON field_audit_responses (question_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_responses_is_finding
    ON field_audit_responses (is_finding)
    WHERE is_finding = TRUE;

CREATE INDEX IF NOT EXISTS idx_field_audit_responses_sync_id
    ON field_audit_responses (sync_id);

ALTER TABLE field_audit_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_audit_responses FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_field_audit_responses_tenant'
          AND tablename  = 'field_audit_responses'
    ) THEN
        CREATE POLICY rls_field_audit_responses_tenant
            ON field_audit_responses
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON field_audit_responses TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. field_audit_photos  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_audit_photos (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID    NOT NULL,
    field_audit_id    UUID    NOT NULL REFERENCES field_audits(id),
    response_id       UUID    REFERENCES field_audit_responses(id),
    minio_object_key  TEXT    NOT NULL,
    original_filename TEXT,
    file_size_bytes   INTEGER,
    mime_type         TEXT    DEFAULT 'image/jpeg',
    caption           TEXT,
    gps_latitude      NUMERIC(10,7),
    gps_longitude     NUMERIC(10,7),
    taken_at          TIMESTAMPTZ,
    sync_id           TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_audit_photos_tenant_id
    ON field_audit_photos (tenant_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_photos_field_audit_id
    ON field_audit_photos (field_audit_id);

CREATE INDEX IF NOT EXISTS idx_field_audit_photos_response_id
    ON field_audit_photos (response_id);

ALTER TABLE field_audit_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_audit_photos FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_field_audit_photos_tenant'
          AND tablename  = 'field_audit_photos'
    ) THEN
        CREATE POLICY rls_field_audit_photos_tenant
            ON field_audit_photos
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON field_audit_photos TO aegis_app;

-- -----------------------------------------------------------------------------
-- 8. sync_sessions  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_sessions (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID    NOT NULL,
    device_id           TEXT    NOT NULL,
    auditor_email       TEXT    NOT NULL,
    sync_type           TEXT    NOT NULL DEFAULT 'upload'
                                CHECK (sync_type IN ('upload','download','full')),
    records_uploaded    INTEGER DEFAULT 0,
    records_downloaded  INTEGER DEFAULT 0,
    conflicts_detected  INTEGER DEFAULT 0,
    conflicts_resolved  INTEGER DEFAULT 0,
    sync_status         TEXT    NOT NULL DEFAULT 'success'
                                CHECK (sync_status IN ('success','partial','failed')),
    error_details       JSONB   DEFAULT '{}',
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    duration_ms         INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_sessions_tenant_id
    ON sync_sessions (tenant_id);

CREATE INDEX IF NOT EXISTS idx_sync_sessions_device_id
    ON sync_sessions (device_id);

CREATE INDEX IF NOT EXISTS idx_sync_sessions_auditor_email
    ON sync_sessions (auditor_email);

CREATE INDEX IF NOT EXISTS idx_sync_sessions_synced_at
    ON sync_sessions (synced_at DESC);

ALTER TABLE sync_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_sessions FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_sync_sessions_tenant'
          AND tablename  = 'sync_sessions'
    ) THEN
        CREATE POLICY rls_sync_sessions_tenant
            ON sync_sessions
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON sync_sessions TO aegis_app;

-- Sprint 19: Mobile Field Audit & Offline Sync schema complete (8 tables, 6 template types + 3 templates + 12 questions seeded)
