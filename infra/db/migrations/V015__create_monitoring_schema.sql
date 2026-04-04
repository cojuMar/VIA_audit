-- =============================================================================
-- V015__create_monitoring_schema.sql
-- Sprint 11: Continuous Monitoring Engine
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. monitoring_rules (PLATFORM — no RLS, SELECT only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('payroll','ap','card','sod','cloud')),
    display_name TEXT NOT NULL,
    description TEXT,
    severity_default TEXT NOT NULL DEFAULT 'medium' CHECK (severity_default IN ('critical','high','medium','low','info')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    config_schema JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monitoring_rules_category ON monitoring_rules (category);
CREATE INDEX IF NOT EXISTS idx_monitoring_rules_is_active ON monitoring_rules (is_active);

GRANT SELECT ON monitoring_rules TO aegis_app;

-- Seed 15 monitoring rules
INSERT INTO monitoring_rules (rule_key, category, display_name, severity_default) VALUES
    ('payroll_statistical_outlier',  'payroll', 'Payroll Statistical Outlier',                    'high'),
    ('payroll_ghost_employee',       'payroll', 'Ghost Employee Detection',                       'critical'),
    ('payroll_benford_deviation',    'payroll', 'Payroll Benford''s Law Deviation',               'medium'),
    ('duplicate_invoice_exact',      'ap',      'Exact Duplicate Invoice',                        'high'),
    ('duplicate_invoice_fuzzy',      'ap',      'Near-Duplicate Invoice',                         'medium'),
    ('invoice_split_detection',      'ap',      'Invoice Split / Threshold Avoidance',            'high'),
    ('invoice_round_amount',         'ap',      'Suspiciously Round Invoice Amount',              'low'),
    ('card_policy_violation',        'card',    'Corporate Card Policy Violation',                'high'),
    ('card_weekend_spend',           'card',    'Card Spend on Weekend/Holiday',                  'medium'),
    ('card_round_amount',            'card',    'Round Amount Card Transaction',                   'low'),
    ('sod_conflict',                 'sod',     'Segregation of Duties Conflict',                 'high'),
    ('sod_privileged_access',        'sod',     'Privileged Access Without Compensating Control', 'high'),
    ('cloud_s3_public_access',       'cloud',   'S3 Bucket Public Access Enabled',               'critical'),
    ('cloud_sg_open_inbound',        'cloud',   'Security Group Open Inbound (0.0.0.0/0)',       'high'),
    ('cloud_mfa_disabled',           'cloud',   'IAM User MFA Disabled',                          'high')
ON CONFLICT (rule_key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. sod_rules (PLATFORM — no RLS, SELECT only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sod_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    role_a TEXT NOT NULL,
    role_b TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'high' CHECK (severity IN ('critical','high','medium','low')),
    framework_references TEXT[] DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_sod_rules_severity   ON sod_rules (severity);
CREATE INDEX IF NOT EXISTS idx_sod_rules_is_active  ON sod_rules (is_active);

GRANT SELECT ON sod_rules TO aegis_app;

-- Seed 10 SoD conflicts
INSERT INTO sod_rules (rule_key, display_name, role_a, role_b, severity, framework_references) VALUES
    ('ap_entry_approval',       'AP Entry and Approval',                     'accounts_payable_entry',  'accounts_payable_approval', 'critical', ARRAY['SOX','SOC2']),
    ('po_create_approve',       'PO Creation and Approval',                  'purchase_order_create',   'purchase_order_approve',    'critical', ARRAY['SOX','SOC2']),
    ('payroll_entry_approval',  'Payroll Entry and Approval',                'payroll_entry',           'payroll_approval',          'critical', ARRAY['SOX','SOC2']),
    ('sysadmin_audit',          'System Admin and Audit',                    'system_administrator',    'audit_compliance',          'high',     ARRAY['SOC2','ISO27001']),
    ('journal_entry_approval',  'Journal Entry and Approval',                'journal_entry',           'journal_approval',          'critical', ARRAY['SOX']),
    ('asset_acquire_dispose',   'Asset Acquisition and Disposal',            'asset_acquisition',       'asset_disposal',            'high',     ARRAY['SOX']),
    ('user_provision_review',   'User Provisioning and Access Review',       'user_provisioning',       'access_review',             'high',     ARRAY['SOC2','ISO27001']),
    ('cash_disburse_reconcile', 'Cash Disbursement and Bank Reconciliation', 'cash_disbursement',       'bank_reconciliation',       'critical', ARRAY['SOX']),
    ('it_change_approve',       'IT Change and IT Change Approval',          'it_change_management',    'it_change_approval',        'high',     ARRAY['SOC2','ISO27001']),
    ('vendor_create_pay',       'Vendor Creation and Payment Approval',      'vendor_master_maintenance','payment_approval',          'critical', ARRAY['SOX','SOC2'])
ON CONFLICT (rule_key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. tenant_monitoring_configs (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_monitoring_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    rule_id UUID NOT NULL REFERENCES monitoring_rules(id),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    config_overrides JSONB NOT NULL DEFAULT '{}',
    schedule_cron TEXT NOT NULL DEFAULT '0 2 * * *',
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_rule UNIQUE (tenant_id, rule_id)
);

CREATE INDEX IF NOT EXISTS idx_tmc_tenant_id         ON tenant_monitoring_configs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tmc_tenant_rule       ON tenant_monitoring_configs (tenant_id, rule_id);

ALTER TABLE tenant_monitoring_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_monitoring_configs FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'tenant_monitoring_configs'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.tenant_monitoring_configs
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON tenant_monitoring_configs TO aegis_app;

-- ---------------------------------------------------------------------------
-- 4. monitoring_data_sources (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('payroll_csv','erp_api','aws','gcp','azure','card_feed','manual_upload')),
    display_name TEXT NOT NULL,
    connection_config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_synced_at TIMESTAMPTZ,
    record_count INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mds_tenant_id          ON monitoring_data_sources (tenant_id);
CREATE INDEX IF NOT EXISTS idx_mds_tenant_source_type ON monitoring_data_sources (tenant_id, source_type);

ALTER TABLE monitoring_data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_data_sources FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'monitoring_data_sources'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.monitoring_data_sources
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON monitoring_data_sources TO aegis_app;

-- ---------------------------------------------------------------------------
-- 5. monitoring_runs (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    rule_id UUID NOT NULL REFERENCES monitoring_rules(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    records_processed INT,
    findings_count INT NOT NULL DEFAULT 0,
    error_message TEXT,
    run_metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_mr_tenant_started     ON monitoring_runs (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_mr_tenant_rule        ON monitoring_runs (tenant_id, rule_id);
CREATE INDEX IF NOT EXISTS idx_mr_status_running     ON monitoring_runs (status) WHERE status = 'running';

ALTER TABLE monitoring_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_runs FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'monitoring_runs'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.monitoring_runs
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON monitoring_runs TO aegis_app;

-- ---------------------------------------------------------------------------
-- 6. monitoring_findings (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES monitoring_runs(id),
    rule_id UUID NOT NULL REFERENCES monitoring_rules(id),
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    entity_name TEXT,
    evidence JSONB NOT NULL DEFAULT '{}',
    risk_score NUMERIC(5,2),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved','false_positive')),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mf_tenant_severity    ON monitoring_findings (tenant_id, severity);
CREATE INDEX IF NOT EXISTS idx_mf_tenant_status      ON monitoring_findings (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_mf_tenant_type        ON monitoring_findings (tenant_id, finding_type);
CREATE INDEX IF NOT EXISTS idx_mf_tenant_detected    ON monitoring_findings (tenant_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_mf_tenant_run         ON monitoring_findings (tenant_id, run_id);

ALTER TABLE monitoring_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_findings FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'monitoring_findings'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.monitoring_findings
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON monitoring_findings TO aegis_app;

-- ---------------------------------------------------------------------------
-- 7. sod_violations (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sod_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    sod_rule_id UUID NOT NULL REFERENCES sod_rules(id),
    user_id TEXT NOT NULL,
    user_name TEXT,
    user_email TEXT,
    role_a_detail TEXT NOT NULL,
    role_b_detail TEXT NOT NULL,
    department TEXT,
    risk_score NUMERIC(5,2),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_source TEXT
);

CREATE INDEX IF NOT EXISTS idx_sv_tenant_sod_rule    ON sod_violations (tenant_id, sod_rule_id);
CREATE INDEX IF NOT EXISTS idx_sv_tenant_detected    ON sod_violations (tenant_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_sv_tenant_user        ON sod_violations (tenant_id, user_id);

ALTER TABLE sod_violations ENABLE ROW LEVEL SECURITY;
ALTER TABLE sod_violations FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'sod_violations'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.sod_violations
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON sod_violations TO aegis_app;

-- ---------------------------------------------------------------------------
-- 8. cloud_config_snapshots (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cloud_config_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('aws','gcp','azure','generic')),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_name TEXT,
    region TEXT,
    config_snapshot JSONB NOT NULL DEFAULT '{}',
    issues JSONB NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL DEFAULT 'info' CHECK (risk_level IN ('critical','high','medium','low','info')),
    snapshotted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ccs_tenant_provider   ON cloud_config_snapshots (tenant_id, provider);
CREATE INDEX IF NOT EXISTS idx_ccs_tenant_risk        ON cloud_config_snapshots (tenant_id, risk_level);
CREATE INDEX IF NOT EXISTS idx_ccs_tenant_snapshotted ON cloud_config_snapshots (tenant_id, snapshotted_at DESC);

ALTER TABLE cloud_config_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE cloud_config_snapshots FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'cloud_config_snapshots'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.cloud_config_snapshots
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON cloud_config_snapshots TO aegis_app;

-- Sprint 11: Continuous Monitoring schema complete (8 tables, 15 rules seeded, 10 SoD rules seeded)
