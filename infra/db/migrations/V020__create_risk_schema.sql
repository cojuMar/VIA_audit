-- =============================================================================
-- V020__create_risk_schema.sql
-- Sprint 16: Risk Management Engine
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. risk_categories  (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_categories (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_key  TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    description   TEXT,
    icon          TEXT,
    sort_order    INT  NOT NULL DEFAULT 0
);

INSERT INTO risk_categories (category_key, display_name, sort_order)
VALUES
    ('strategic',      'Strategic',            1),
    ('operational',    'Operational',          2),
    ('financial',      'Financial',            3),
    ('compliance',     'Compliance',           4),
    ('technology',     'Technology',           5),
    ('cybersecurity',  'Cybersecurity',        6),
    ('vendor',         'Vendor / Third-Party', 7),
    ('people',         'People & HR',          8),
    ('reputational',   'Reputational',         9),
    ('esg',            'ESG & Sustainability', 10)
ON CONFLICT (category_key) DO NOTHING;

GRANT SELECT ON risk_categories TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. risk_appetite_statements  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_appetite_statements (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL,
    category_id            UUID NOT NULL REFERENCES risk_categories(id),
    appetite_level         TEXT NOT NULL CHECK (appetite_level IN ('zero','low','moderate','high','very_high')),
    description            TEXT,
    max_acceptable_score   NUMERIC(4,1)  NOT NULL DEFAULT 12.0,
    review_frequency_days  INT           NOT NULL DEFAULT 365,
    last_reviewed_at       DATE,
    approved_by            TEXT,
    effective_date         DATE          NOT NULL DEFAULT CURRENT_DATE,
    created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_category_appetite UNIQUE (tenant_id, category_id)
);

CREATE INDEX IF NOT EXISTS idx_risk_appetite_statements_tenant_id
    ON risk_appetite_statements (tenant_id);

CREATE INDEX IF NOT EXISTS idx_risk_appetite_statements_tenant_category
    ON risk_appetite_statements (tenant_id, category_id);

ALTER TABLE risk_appetite_statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_appetite_statements FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_appetite_statements_tenant'
          AND tablename  = 'risk_appetite_statements'
    ) THEN
        CREATE POLICY rls_risk_appetite_statements_tenant
            ON risk_appetite_statements
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON risk_appetite_statements TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. risks  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risks (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    risk_id                 TEXT NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    category_id             UUID NOT NULL REFERENCES risk_categories(id),
    owner                   TEXT,
    department              TEXT,
    status                  TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','in_treatment','accepted','closed','transferred')),
    -- Inherent risk (before controls)
    inherent_likelihood     INT  NOT NULL CHECK (inherent_likelihood BETWEEN 1 AND 5),
    inherent_impact         INT  NOT NULL CHECK (inherent_impact     BETWEEN 1 AND 5),
    inherent_score          NUMERIC(4,1) GENERATED ALWAYS AS (inherent_likelihood * inherent_impact) STORED,
    -- Residual risk (after controls)
    residual_likelihood     INT  CHECK (residual_likelihood BETWEEN 1 AND 5),
    residual_impact         INT  CHECK (residual_impact     BETWEEN 1 AND 5),
    residual_score          NUMERIC(4,1) GENERATED ALWAYS AS (residual_likelihood * residual_impact) STORED,
    -- Target risk (desired state)
    target_likelihood       INT  CHECK (target_likelihood BETWEEN 1 AND 5),
    target_impact           INT  CHECK (target_impact     BETWEEN 1 AND 5),
    -- Related references
    framework_control_refs  TEXT[]  DEFAULT '{}',
    monitoring_finding_ids  UUID[]  DEFAULT '{}',
    related_risk_ids        UUID[]  DEFAULT '{}',
    -- Source
    source                  TEXT NOT NULL DEFAULT 'manual'
                                CHECK (source IN ('manual','monitoring_auto','vendor_auto','ai_suggested')),
    auto_source_id          TEXT,
    -- Dates
    identified_date         DATE        NOT NULL DEFAULT CURRENT_DATE,
    review_date             DATE,
    closed_date             DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_risk_id UNIQUE (tenant_id, risk_id)
);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_id
    ON risks (tenant_id);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_status
    ON risks (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_category
    ON risks (tenant_id, category_id);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_inherent_score
    ON risks (tenant_id, inherent_score DESC);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_residual_score
    ON risks (tenant_id, residual_score DESC);

CREATE INDEX IF NOT EXISTS idx_risks_tenant_review_date
    ON risks (review_date)
    WHERE review_date IS NOT NULL AND status = 'open';

ALTER TABLE risks ENABLE ROW LEVEL SECURITY;
ALTER TABLE risks FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risks_tenant'
          AND tablename  = 'risks'
    ) THEN
        CREATE POLICY rls_risks_tenant
            ON risks
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON risks TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. risk_assessments  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_assessments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    risk_id              UUID NOT NULL REFERENCES risks(id),
    assessed_by          TEXT NOT NULL,
    inherent_likelihood  INT  NOT NULL,
    inherent_impact      INT  NOT NULL,
    residual_likelihood  INT,
    residual_impact      INT,
    assessment_notes     TEXT,
    controls_evaluated   TEXT[],
    assessed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_tenant_risk
    ON risk_assessments (tenant_id, risk_id);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_tenant_assessed_at
    ON risk_assessments (tenant_id, assessed_at DESC);

ALTER TABLE risk_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_assessments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_assessments_tenant'
          AND tablename  = 'risk_assessments'
    ) THEN
        CREATE POLICY rls_risk_assessments_tenant
            ON risk_assessments
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON risk_assessments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. risk_treatments  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_treatments (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL,
    risk_id              UUID NOT NULL REFERENCES risks(id),
    treatment_type       TEXT NOT NULL CHECK (treatment_type IN ('mitigate','accept','transfer','avoid')),
    title                TEXT NOT NULL,
    description          TEXT NOT NULL,
    owner                TEXT,
    status               TEXT NOT NULL DEFAULT 'planned'
                             CHECK (status IN ('planned','in_progress','completed','cancelled')),
    target_date          DATE,
    completed_date       DATE,
    cost_estimate        NUMERIC(12,2),
    effectiveness_rating INT CHECK (effectiveness_rating BETWEEN 1 AND 5),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_treatments_tenant_risk
    ON risk_treatments (tenant_id, risk_id);

CREATE INDEX IF NOT EXISTS idx_risk_treatments_tenant_status
    ON risk_treatments (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_risk_treatments_tenant_target_date
    ON risk_treatments (target_date)
    WHERE target_date IS NOT NULL AND status IN ('planned','in_progress');

ALTER TABLE risk_treatments ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_treatments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_treatments_tenant'
          AND tablename  = 'risk_treatments'
    ) THEN
        CREATE POLICY rls_risk_treatments_tenant
            ON risk_treatments
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON risk_treatments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. risk_score_history  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_score_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    risk_id             UUID NOT NULL REFERENCES risks(id),
    inherent_likelihood INT         NOT NULL,
    inherent_impact     INT         NOT NULL,
    inherent_score      NUMERIC(4,1) NOT NULL,
    residual_likelihood INT,
    residual_impact     INT,
    residual_score      NUMERIC(4,1),
    changed_by          TEXT,
    change_reason       TEXT,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_score_history_tenant_risk
    ON risk_score_history (tenant_id, risk_id);

CREATE INDEX IF NOT EXISTS idx_risk_score_history_tenant_recorded_at
    ON risk_score_history (tenant_id, recorded_at DESC);

ALTER TABLE risk_score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_score_history FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_score_history_tenant'
          AND tablename  = 'risk_score_history'
    ) THEN
        CREATE POLICY rls_risk_score_history_tenant
            ON risk_score_history
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON risk_score_history TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. risk_indicators  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_indicators (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    risk_id          UUID NOT NULL REFERENCES risks(id),
    indicator_name   TEXT NOT NULL,
    description      TEXT,
    metric_type      TEXT NOT NULL CHECK (metric_type IN ('kri','kpi','kci')),
    threshold_green  NUMERIC(10,2),
    threshold_amber  NUMERIC(10,2),
    threshold_red    NUMERIC(10,2),
    current_value    NUMERIC(10,2),
    current_status   TEXT DEFAULT 'green'
                         CHECK (current_status IN ('green','amber','red','unknown')),
    last_updated_at  TIMESTAMPTZ,
    data_source      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_indicators_tenant_risk
    ON risk_indicators (tenant_id, risk_id);

CREATE INDEX IF NOT EXISTS idx_risk_indicators_tenant_status
    ON risk_indicators (tenant_id, current_status);

ALTER TABLE risk_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_indicators FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_indicators_tenant'
          AND tablename  = 'risk_indicators'
    ) THEN
        CREATE POLICY rls_risk_indicators_tenant
            ON risk_indicators
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON risk_indicators TO aegis_app;

-- -----------------------------------------------------------------------------
-- 8. risk_indicator_readings  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_indicator_readings (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    indicator_id UUID NOT NULL REFERENCES risk_indicators(id),
    risk_id      UUID NOT NULL REFERENCES risks(id),
    value        NUMERIC(10,2) NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('green','amber','red')),
    notes        TEXT,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_indicator_readings_tenant_indicator
    ON risk_indicator_readings (tenant_id, indicator_id);

CREATE INDEX IF NOT EXISTS idx_risk_indicator_readings_tenant_recorded_at
    ON risk_indicator_readings (tenant_id, recorded_at DESC);

ALTER TABLE risk_indicator_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_indicator_readings FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'rls_risk_indicator_readings_tenant'
          AND tablename  = 'risk_indicator_readings'
    ) THEN
        CREATE POLICY rls_risk_indicator_readings_tenant
            ON risk_indicator_readings
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON risk_indicator_readings TO aegis_app;

-- Sprint 16: Risk Management Engine schema complete (8 tables, 10 risk categories seeded)
