-- =============================================================================
-- V022__create_esg_board_schema.sql
-- Sprint 18: ESG Disclosure & Board Governance
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. esg_frameworks  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS esg_frameworks (
    id             UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_key  TEXT    NOT NULL UNIQUE,
    display_name   TEXT    NOT NULL,
    description    TEXT,
    category       TEXT    NOT NULL CHECK (category IN ('environmental','social','governance','integrated','sdg')),
    version        TEXT,
    issuing_body   TEXT,
    website_url    TEXT,
    is_mandatory   BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO esg_frameworks
    (framework_key, display_name, description, category, version, issuing_body, website_url, is_mandatory)
VALUES
    ('gri',        'Global Reporting Initiative (GRI)',                              'Universal standards for sustainability reporting',                                  'integrated',   '2021', 'GRI',                 'https://www.globalreporting.org',         false),
    ('sasb',       'SASB Standards',                                                'Industry-specific sustainability accounting standards',                              'integrated',   '2023', 'ISSB/SASB',           'https://www.sasb.org',                    false),
    ('tcfd',       'TCFD Recommendations',                                          'Task Force on Climate-related Financial Disclosures',                               'environmental','2017', 'TCFD',                'https://www.fsb-tcfd.org',                false),
    ('ifrs_s1',    'IFRS S1',                                                       'General Requirements for Disclosure of Sustainability-related Financial Information','integrated',   '2023', 'ISSB',                'https://www.ifrs.org',                    false),
    ('ifrs_s2',    'IFRS S2',                                                       'Climate-related Disclosures',                                                       'environmental','2023', 'ISSB',                'https://www.ifrs.org',                    false),
    ('eu_taxonomy','EU Taxonomy Regulation',                                        'EU classification system for sustainable economic activities',                      'environmental','2020', 'European Commission', 'https://finance.ec.europa.eu',            true),
    ('csrd',       'CSRD / ESRS',                                                   'Corporate Sustainability Reporting Directive',                                       'integrated',   '2023', 'European Commission', 'https://finance.ec.europa.eu',            true),
    ('cdp',        'CDP Disclosure',                                                'Carbon Disclosure Project environmental reporting',                                 'environmental','2023', 'CDP',                 'https://www.cdp.net',                     false),
    ('un_sdg',     'UN Sustainable Development Goals',                              '17 SDGs for people and planet by 2030',                                             'sdg',          '2015', 'United Nations',      'https://sdgs.un.org',                     false),
    ('ungc',       'UN Global Compact',                                             'Ten principles on human rights, labour, environment, anti-corruption',              'integrated',   '2000', 'United Nations',      'https://www.unglobalcompact.org',          false)
ON CONFLICT (framework_key) DO NOTHING;

GRANT SELECT ON esg_frameworks TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. esg_metric_definitions  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS esg_metric_definitions (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id         UUID    REFERENCES esg_frameworks(id),
    metric_key           TEXT    NOT NULL UNIQUE,
    display_name         TEXT    NOT NULL,
    description          TEXT,
    category             TEXT    NOT NULL CHECK (category IN ('environmental','social','governance')),
    subcategory          TEXT,
    unit                 TEXT    NOT NULL,
    data_type            TEXT    NOT NULL DEFAULT 'numeric'
                                 CHECK (data_type IN ('numeric','percentage','boolean','text','currency')),
    lower_is_better      BOOLEAN DEFAULT TRUE,
    is_required          BOOLEAN DEFAULT FALSE,
    disclosure_reference TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO esg_metric_definitions
    (metric_key, display_name, description, category, subcategory, unit, data_type, lower_is_better, is_required, disclosure_reference)
VALUES
    -- Environmental (7)
    ('ghg_scope1',                 'GHG Emissions — Scope 1',         'Direct greenhouse gas emissions',                       'environmental', 'climate',   'tCO2e',      'numeric',    true,  true,  'GRI 305-1'),
    ('ghg_scope2',                 'GHG Emissions — Scope 2',         'Indirect emissions from purchased energy',              'environmental', 'climate',   'tCO2e',      'numeric',    true,  true,  'GRI 305-2'),
    ('ghg_scope3',                 'GHG Emissions — Scope 3',         'Value chain indirect emissions',                        'environmental', 'climate',   'tCO2e',      'numeric',    true,  false, 'GRI 305-3'),
    ('energy_consumption',         'Total Energy Consumption',         'Energy consumed across all operations',                 'environmental', 'energy',    'MWh',        'numeric',    true,  false, 'GRI 302-1'),
    ('renewable_energy_pct',       'Renewable Energy Percentage',      'Share of energy from renewable sources',                'environmental', 'energy',    'percentage', 'percentage', false, false, 'GRI 302-1'),
    ('water_withdrawal',           'Water Withdrawal',                 'Total water withdrawn from all sources',                'environmental', 'water',     'liters',     'numeric',    true,  false, 'GRI 303-3'),
    ('waste_generated',            'Total Waste Generated',            'Total weight of waste generated',                      'environmental', 'waste',     'tonnes',     'numeric',    true,  false, 'GRI 306-3'),
    -- Social (5)
    ('employee_count',             'Total Employees',                  'Total number of employees at period end',               'social',        'workforce', 'count',      'numeric',    false, true,  'GRI 2-7'),
    ('employee_turnover_rate',     'Employee Turnover Rate',           'Percentage of employees who left during period',        'social',        'workforce', 'percentage', 'percentage', true,  false, 'GRI 401-1'),
    ('gender_diversity_pct',       'Gender Diversity — Women %',       'Percentage of women in total workforce',                'social',        'diversity', 'percentage', 'percentage', false, false, 'GRI 405-1'),
    ('training_hours_per_employee','Training Hours per Employee',      'Average training hours per employee per year',          'social',        'training',  'hours',      'numeric',    false, false, 'GRI 404-1'),
    ('lost_time_injury_rate',      'Lost Time Injury Rate',            'Injuries per million hours worked',                     'social',        'safety',    'ratio',      'numeric',    true,  false, 'GRI 403-9'),
    -- Governance (3)
    ('board_independence_pct',     'Board Independence %',             'Percentage of independent board directors',             'governance',    'board',     'percentage', 'percentage', false, true,  'GRI 2-9'),
    ('board_gender_diversity_pct', 'Board Gender Diversity %',         'Percentage of women on board',                          'governance',    'board',     'percentage', 'percentage', false, false, 'GRI 405-1'),
    ('ethics_violations_count',    'Ethics/Compliance Violations',     'Number of substantiated ethics violations',             'governance',    'ethics',    'count',      'numeric',    true,  false, 'GRI 205-3')
ON CONFLICT (metric_key) DO NOTHING;

GRANT SELECT ON esg_metric_definitions TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. esg_disclosures  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS esg_disclosures (
    id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID    NOT NULL,
    metric_definition_id  UUID    NOT NULL REFERENCES esg_metric_definitions(id),
    reporting_period      TEXT    NOT NULL,
    period_type           TEXT    NOT NULL DEFAULT 'annual'
                                  CHECK (period_type IN ('annual','semi_annual','quarterly','monthly')),
    numeric_value         NUMERIC(20,4),
    text_value            TEXT,
    boolean_value         BOOLEAN,
    currency_value        NUMERIC(20,2),
    currency_code         TEXT    DEFAULT 'USD',
    notes                 TEXT,
    data_source           TEXT,
    assurance_level       TEXT    CHECK (assurance_level IN ('none','limited','reasonable')),
    assured_by            TEXT,
    submitted_by          TEXT,
    submitted_at          TIMESTAMPTZ DEFAULT NOW(),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_esg_disclosures_tenant_id
    ON esg_disclosures (tenant_id);

CREATE INDEX IF NOT EXISTS idx_esg_disclosures_metric_definition_id
    ON esg_disclosures (metric_definition_id);

CREATE INDEX IF NOT EXISTS idx_esg_disclosures_reporting_period
    ON esg_disclosures (reporting_period);

CREATE INDEX IF NOT EXISTS idx_esg_disclosures_tenant_metric_period
    ON esg_disclosures (tenant_id, metric_definition_id, reporting_period);

ALTER TABLE esg_disclosures ENABLE ROW LEVEL SECURITY;
ALTER TABLE esg_disclosures FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_esg_disclosures_tenant'
          AND tablename  = 'esg_disclosures'
    ) THEN
        CREATE POLICY rls_esg_disclosures_tenant
            ON esg_disclosures
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON esg_disclosures TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. esg_targets  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS esg_targets (
    id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID    NOT NULL,
    metric_definition_id  UUID    NOT NULL REFERENCES esg_metric_definitions(id),
    target_year           INTEGER NOT NULL CHECK (target_year >= 2020 AND target_year <= 2050),
    baseline_year         INTEGER CHECK (baseline_year >= 2010),
    baseline_value        NUMERIC(20,4),
    target_value          NUMERIC(20,4) NOT NULL,
    target_type           TEXT    NOT NULL DEFAULT 'absolute'
                                  CHECK (target_type IN ('absolute','intensity','percentage_reduction','percentage_increase')),
    description           TEXT,
    science_based         BOOLEAN DEFAULT FALSE,
    framework_alignment   TEXT[],
    status                TEXT    NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','achieved','missed','revised','withdrawn')),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, metric_definition_id, target_year)
);

CREATE INDEX IF NOT EXISTS idx_esg_targets_tenant_id
    ON esg_targets (tenant_id);

CREATE INDEX IF NOT EXISTS idx_esg_targets_metric_definition_id
    ON esg_targets (metric_definition_id);

CREATE INDEX IF NOT EXISTS idx_esg_targets_target_year
    ON esg_targets (target_year);

CREATE INDEX IF NOT EXISTS idx_esg_targets_status
    ON esg_targets (status);

ALTER TABLE esg_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE esg_targets FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_esg_targets_tenant'
          AND tablename  = 'esg_targets'
    ) THEN
        CREATE POLICY rls_esg_targets_tenant
            ON esg_targets
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON esg_targets TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. board_committees  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_committees (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID    NOT NULL,
    name                TEXT    NOT NULL,
    committee_type      TEXT    NOT NULL DEFAULT 'other'
                                CHECK (committee_type IN ('audit','risk','esg','compensation','nominating','executive','finance','other')),
    charter             TEXT,
    members             TEXT[],
    chair               TEXT,
    quorum_requirement  INTEGER DEFAULT 3,
    meeting_frequency   TEXT    DEFAULT 'quarterly',
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_board_committees_tenant_id
    ON board_committees (tenant_id);

CREATE INDEX IF NOT EXISTS idx_board_committees_committee_type
    ON board_committees (committee_type);

CREATE INDEX IF NOT EXISTS idx_board_committees_is_active
    ON board_committees (tenant_id)
    WHERE is_active = TRUE;

ALTER TABLE board_committees ENABLE ROW LEVEL SECURITY;
ALTER TABLE board_committees FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_board_committees_tenant'
          AND tablename  = 'board_committees'
    ) THEN
        CREATE POLICY rls_board_committees_tenant
            ON board_committees
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON board_committees TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. board_meetings  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_meetings (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID    NOT NULL,
    committee_id         UUID    REFERENCES board_committees(id),
    title                TEXT    NOT NULL,
    meeting_type         TEXT    NOT NULL DEFAULT 'regular'
                                 CHECK (meeting_type IN ('regular','special','annual','emergency')),
    scheduled_date       TIMESTAMPTZ NOT NULL,
    actual_date          TIMESTAMPTZ,
    location             TEXT,
    virtual_link         TEXT,
    status               TEXT    NOT NULL DEFAULT 'scheduled'
                                 CHECK (status IN ('scheduled','in_progress','completed','cancelled','postponed')),
    quorum_met           BOOLEAN,
    attendees            TEXT[],
    minutes_text         TEXT,
    minutes_approved     BOOLEAN DEFAULT FALSE,
    minutes_approved_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_board_meetings_tenant_id
    ON board_meetings (tenant_id);

CREATE INDEX IF NOT EXISTS idx_board_meetings_committee_id
    ON board_meetings (committee_id);

CREATE INDEX IF NOT EXISTS idx_board_meetings_status
    ON board_meetings (status);

CREATE INDEX IF NOT EXISTS idx_board_meetings_scheduled_date
    ON board_meetings (scheduled_date);

ALTER TABLE board_meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE board_meetings FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_board_meetings_tenant'
          AND tablename  = 'board_meetings'
    ) THEN
        CREATE POLICY rls_board_meetings_tenant
            ON board_meetings
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON board_meetings TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. board_agenda_items  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_agenda_items (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID    NOT NULL,
    meeting_id       UUID    NOT NULL REFERENCES board_meetings(id) ON DELETE CASCADE,
    sequence_number  INTEGER NOT NULL,
    title            TEXT    NOT NULL,
    item_type        TEXT    NOT NULL DEFAULT 'discussion'
                             CHECK (item_type IN ('approval','discussion','information','presentation','action_review','aob')),
    description      TEXT,
    presenter        TEXT,
    duration_minutes INTEGER DEFAULT 15,
    status           TEXT    DEFAULT 'pending'
                             CHECK (status IN ('pending','presented','approved','rejected','deferred','tabled')),
    decision         TEXT,
    action_items     TEXT[],
    attachments      TEXT[],
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_board_agenda_items_tenant_id
    ON board_agenda_items (tenant_id);

CREATE INDEX IF NOT EXISTS idx_board_agenda_items_meeting_id
    ON board_agenda_items (meeting_id);

CREATE INDEX IF NOT EXISTS idx_board_agenda_items_sequence_number
    ON board_agenda_items (sequence_number);

ALTER TABLE board_agenda_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE board_agenda_items FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_board_agenda_items_tenant'
          AND tablename  = 'board_agenda_items'
    ) THEN
        CREATE POLICY rls_board_agenda_items_tenant
            ON board_agenda_items
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON board_agenda_items TO aegis_app;

-- -----------------------------------------------------------------------------
-- 8. board_packages  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_packages (
    id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID    NOT NULL,
    meeting_id           UUID    REFERENCES board_meetings(id),
    title                TEXT    NOT NULL,
    package_type         TEXT    NOT NULL DEFAULT 'board_pack'
                                 CHECK (package_type IN ('board_pack','committee_pack','special_report','esg_report','audit_report','risk_report')),
    reporting_period     TEXT,
    status               TEXT    NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft','under_review','approved','distributed','archived')),
    prepared_by          TEXT,
    approved_by          TEXT,
    distributed_at       TIMESTAMPTZ,
    recipient_list       TEXT[],
    executive_summary    TEXT,
    ai_generated_summary TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_board_packages_tenant_id
    ON board_packages (tenant_id);

CREATE INDEX IF NOT EXISTS idx_board_packages_meeting_id
    ON board_packages (meeting_id);

CREATE INDEX IF NOT EXISTS idx_board_packages_status
    ON board_packages (status);

CREATE INDEX IF NOT EXISTS idx_board_packages_package_type
    ON board_packages (package_type);

ALTER TABLE board_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE board_packages FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_board_packages_tenant'
          AND tablename  = 'board_packages'
    ) THEN
        CREATE POLICY rls_board_packages_tenant
            ON board_packages
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON board_packages TO aegis_app;

-- -----------------------------------------------------------------------------
-- 9. board_package_items  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_package_items (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID    NOT NULL,
    package_id       UUID    NOT NULL REFERENCES board_packages(id) ON DELETE CASCADE,
    sequence_number  INTEGER NOT NULL,
    section_title    TEXT    NOT NULL,
    content_type     TEXT    NOT NULL DEFAULT 'text'
                             CHECK (content_type IN ('text','metrics_table','chart_data','risk_heatmap','audit_findings','esg_scorecard','custom')),
    content_data     JSONB   DEFAULT '{}',
    source_service   TEXT,
    source_id        UUID,
    is_confidential  BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_board_package_items_tenant_id
    ON board_package_items (tenant_id);

CREATE INDEX IF NOT EXISTS idx_board_package_items_package_id
    ON board_package_items (package_id);

CREATE INDEX IF NOT EXISTS idx_board_package_items_sequence_number
    ON board_package_items (sequence_number);

ALTER TABLE board_package_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE board_package_items FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_board_package_items_tenant'
          AND tablename  = 'board_package_items'
    ) THEN
        CREATE POLICY rls_board_package_items_tenant
            ON board_package_items
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON board_package_items TO aegis_app;

-- Sprint 18: ESG Disclosure & Board Governance schema complete (9 tables, 10 frameworks + 15 metrics seeded)
