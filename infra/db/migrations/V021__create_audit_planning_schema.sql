-- =============================================================================
-- V021__create_audit_planning_schema.sql
-- Sprint 17: Audit Planning & Engagement Management
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. audit_entity_types  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_entity_types (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_key     TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description  TEXT,
    icon         TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO audit_entity_types (type_key, display_name, description, icon)
VALUES
    ('business_process', 'Business Process',       'End-to-end business workflow or process',              'workflow'),
    ('it_system',        'IT System',               'Enterprise application or infrastructure component',   'server'),
    ('location',         'Physical Location',       'Office, data center, or operational site',             'map-pin'),
    ('business_unit',    'Business Unit',           'Organizational division or department',                'building'),
    ('vendor',           'Third-Party Vendor',      'External service provider or supplier',                'truck'),
    ('regulation',       'Regulatory Requirement',  'Compliance obligation or regulatory mandate',          'shield'),
    ('project',          'Strategic Project',       'Initiative or transformation program',                 'target')
ON CONFLICT (type_key) DO NOTHING;

GRANT SELECT ON audit_entity_types TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. audit_entities  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_entities (
    id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID    NOT NULL,
    name                  TEXT    NOT NULL,
    description           TEXT,
    entity_type_id        UUID    REFERENCES audit_entity_types(id),
    owner_name            TEXT,
    owner_email           TEXT,
    department            TEXT,
    risk_score            NUMERIC(4,2) DEFAULT 5.0 CHECK (risk_score >= 0 AND risk_score <= 10),
    last_audit_date       DATE,
    next_audit_due        DATE,
    audit_frequency_months INTEGER DEFAULT 12 CHECK (audit_frequency_months > 0),
    is_in_universe        BOOLEAN DEFAULT TRUE,
    tags                  TEXT[],
    metadata              JSONB   DEFAULT '{}',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_entities_tenant_id
    ON audit_entities (tenant_id);

CREATE INDEX IF NOT EXISTS idx_audit_entities_entity_type_id
    ON audit_entities (entity_type_id);

CREATE INDEX IF NOT EXISTS idx_audit_entities_risk_score
    ON audit_entities (risk_score DESC);

CREATE INDEX IF NOT EXISTS idx_audit_entities_is_in_universe
    ON audit_entities (tenant_id)
    WHERE is_in_universe = TRUE;

ALTER TABLE audit_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_entities FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_audit_entities_tenant'
          AND tablename  = 'audit_entities'
    ) THEN
        CREATE POLICY rls_audit_entities_tenant
            ON audit_entities
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_entities TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. audit_plans  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_plans (
    id                 UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID    NOT NULL,
    plan_year          INTEGER NOT NULL CHECK (plan_year >= 2020 AND plan_year <= 2099),
    title              TEXT    NOT NULL,
    description        TEXT,
    status             TEXT    NOT NULL DEFAULT 'draft'
                               CHECK (status IN ('draft','approved','active','closed')),
    total_budget_hours NUMERIC(10,2) DEFAULT 0,
    approved_by        TEXT,
    approved_at        TIMESTAMPTZ,
    created_by         TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, plan_year)
);

CREATE INDEX IF NOT EXISTS idx_audit_plans_tenant_id
    ON audit_plans (tenant_id);

CREATE INDEX IF NOT EXISTS idx_audit_plans_plan_year
    ON audit_plans (plan_year);

ALTER TABLE audit_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_plans FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_audit_plans_tenant'
          AND tablename  = 'audit_plans'
    ) THEN
        CREATE POLICY rls_audit_plans_tenant
            ON audit_plans
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_plans TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. audit_plan_items  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_plan_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    plan_id          UUID NOT NULL REFERENCES audit_plans(id) ON DELETE CASCADE,
    audit_entity_id  UUID REFERENCES audit_entities(id),
    title            TEXT NOT NULL,
    audit_type       TEXT NOT NULL DEFAULT 'internal'
                         CHECK (audit_type IN ('internal','external','regulatory','advisory','follow_up')),
    priority         TEXT NOT NULL DEFAULT 'medium'
                         CHECK (priority IN ('critical','high','medium','low')),
    planned_start_date DATE,
    planned_end_date   DATE,
    budget_hours       NUMERIC(8,2) DEFAULT 0,
    assigned_lead      TEXT,
    status             TEXT NOT NULL DEFAULT 'planned'
                           CHECK (status IN ('planned','scheduled','in_progress','completed','cancelled','deferred')),
    rationale          TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_plan_items_tenant_id
    ON audit_plan_items (tenant_id);

CREATE INDEX IF NOT EXISTS idx_audit_plan_items_plan_id
    ON audit_plan_items (plan_id);

CREATE INDEX IF NOT EXISTS idx_audit_plan_items_audit_entity_id
    ON audit_plan_items (audit_entity_id);

CREATE INDEX IF NOT EXISTS idx_audit_plan_items_status
    ON audit_plan_items (status);

CREATE INDEX IF NOT EXISTS idx_audit_plan_items_priority
    ON audit_plan_items (priority);

ALTER TABLE audit_plan_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_plan_items FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_audit_plan_items_tenant'
          AND tablename  = 'audit_plan_items'
    ) THEN
        CREATE POLICY rls_audit_plan_items_tenant
            ON audit_plan_items
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_plan_items TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. audit_engagements  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
--
-- V017 creates a minimal audit_engagements. This block extends it to the full
-- planning-schema shape via idempotent ADD COLUMN IF NOT EXISTS so we don't
-- redefine-and-shadow with a second CREATE TABLE (which previously silently
-- no-op'd on IF NOT EXISTS and left the older minimal shape in place).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_engagements (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    title              TEXT NOT NULL,
    audit_type         TEXT NOT NULL DEFAULT 'internal',
    status             TEXT NOT NULL DEFAULT 'planning',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS plan_item_id       UUID REFERENCES audit_plan_items(id);
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS engagement_code    TEXT;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS scope              TEXT;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS objectives         TEXT;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS planned_start_date DATE;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS planned_end_date   DATE;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS actual_start_date  DATE;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS actual_end_date    DATE;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS budget_hours       NUMERIC(8,2) DEFAULT 0;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS lead_auditor       TEXT;
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS team_members       TEXT[];
ALTER TABLE audit_engagements ADD COLUMN IF NOT EXISTS engagement_manager TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_engagements_tenant_id
    ON audit_engagements (tenant_id);

CREATE INDEX IF NOT EXISTS idx_audit_engagements_plan_item_id
    ON audit_engagements (plan_item_id);

CREATE INDEX IF NOT EXISTS idx_audit_engagements_status
    ON audit_engagements (status);

CREATE INDEX IF NOT EXISTS idx_audit_engagements_lead_auditor
    ON audit_engagements (lead_auditor);

CREATE INDEX IF NOT EXISTS idx_audit_engagements_engagement_code
    ON audit_engagements (engagement_code);

ALTER TABLE audit_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_engagements FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_audit_engagements_tenant'
          AND tablename  = 'audit_engagements'
    ) THEN
        CREATE POLICY rls_audit_engagements_tenant
            ON audit_engagements
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_engagements TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. time_entries  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS time_entries (
    id             UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID    NOT NULL,
    engagement_id  UUID    NOT NULL REFERENCES audit_engagements(id),
    auditor_name   TEXT    NOT NULL,
    auditor_email  TEXT,
    entry_date     DATE    NOT NULL DEFAULT CURRENT_DATE,
    hours          NUMERIC(4,2) NOT NULL CHECK (hours > 0 AND hours <= 24),
    activity_type  TEXT    NOT NULL DEFAULT 'fieldwork'
                           CHECK (activity_type IN ('planning','fieldwork','reporting','review','admin','travel','training')),
    description    TEXT,
    is_billable    BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_time_entries_tenant_id
    ON time_entries (tenant_id);

CREATE INDEX IF NOT EXISTS idx_time_entries_engagement_id
    ON time_entries (engagement_id);

CREATE INDEX IF NOT EXISTS idx_time_entries_auditor_email
    ON time_entries (auditor_email);

CREATE INDEX IF NOT EXISTS idx_time_entries_entry_date
    ON time_entries (entry_date);

CREATE INDEX IF NOT EXISTS idx_time_entries_activity_type
    ON time_entries (activity_type);

ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_entries FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_time_entries_tenant'
          AND tablename  = 'time_entries'
    ) THEN
        CREATE POLICY rls_time_entries_tenant
            ON time_entries
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON time_entries TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. audit_milestones  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_milestones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    engagement_id   UUID NOT NULL REFERENCES audit_engagements(id),
    title           TEXT NOT NULL,
    milestone_type  TEXT NOT NULL DEFAULT 'deliverable'
                        CHECK (milestone_type IN ('kickoff','planning_complete','fieldwork_start','fieldwork_complete','draft_report','management_response','final_report','closeout')),
    due_date        DATE NOT NULL,
    completed_date  DATE,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','completed','overdue','waived')),
    owner           TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_milestones_tenant_id
    ON audit_milestones (tenant_id);

CREATE INDEX IF NOT EXISTS idx_audit_milestones_engagement_id
    ON audit_milestones (engagement_id);

CREATE INDEX IF NOT EXISTS idx_audit_milestones_status
    ON audit_milestones (status);

CREATE INDEX IF NOT EXISTS idx_audit_milestones_due_date
    ON audit_milestones (due_date);

ALTER TABLE audit_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_milestones FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_audit_milestones_tenant'
          AND tablename  = 'audit_milestones'
    ) THEN
        CREATE POLICY rls_audit_milestones_tenant
            ON audit_milestones
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_milestones TO aegis_app;

-- -----------------------------------------------------------------------------
-- 8. resource_assignments  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resource_assignments (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID    NOT NULL,
    engagement_id   UUID    NOT NULL REFERENCES audit_engagements(id),
    auditor_name    TEXT    NOT NULL,
    auditor_email   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'staff'
                            CHECK (role IN ('lead','manager','staff','specialist','reviewer')),
    allocated_hours NUMERIC(8,2) DEFAULT 0,
    start_date      DATE,
    end_date        DATE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (engagement_id, auditor_email)
);

CREATE INDEX IF NOT EXISTS idx_resource_assignments_tenant_id
    ON resource_assignments (tenant_id);

CREATE INDEX IF NOT EXISTS idx_resource_assignments_engagement_id
    ON resource_assignments (engagement_id);

CREATE INDEX IF NOT EXISTS idx_resource_assignments_auditor_email
    ON resource_assignments (auditor_email);

CREATE INDEX IF NOT EXISTS idx_resource_assignments_is_active
    ON resource_assignments (tenant_id)
    WHERE is_active = TRUE;

ALTER TABLE resource_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_assignments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_resource_assignments_tenant'
          AND tablename  = 'resource_assignments'
    ) THEN
        CREATE POLICY rls_resource_assignments_tenant
            ON resource_assignments
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON resource_assignments TO aegis_app;

-- Sprint 17: Audit Planning & Engagement Management schema complete (8 tables, 7 entity types seeded)
