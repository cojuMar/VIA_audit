-- =============================================================================
-- V018__create_integration_schema.sql
-- Sprint 14: Enterprise Integration Hub
-- 8 tables: connector_definitions, tenant_integrations, integration_sync_logs,
--            integration_records, oauth_tokens, webhook_events,
--            field_mapping_templates, integration_data_mappings
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. connector_definitions  (PLATFORM — no RLS, SELECT only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connector_definitions (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_key         TEXT        NOT NULL UNIQUE,
    display_name          TEXT        NOT NULL,
    category              TEXT        NOT NULL CHECK (category IN ('erp','hris','itsm','cloud','identity','security','collaboration','source_control','crm','custom')),
    auth_type             TEXT        NOT NULL CHECK (auth_type IN ('oauth2','api_key','basic','webhook','service_account','none')),
    description           TEXT,
    logo_url              TEXT,
    docs_url              TEXT,
    supported_data_types  TEXT[]      NOT NULL DEFAULT '{}',
    config_schema         JSONB       NOT NULL DEFAULT '{}',
    is_active             BOOLEAN     NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

GRANT SELECT ON connector_definitions TO aegis_app;

-- Seed 22 connectors
INSERT INTO connector_definitions (connector_key, display_name, category, auth_type, supported_data_types) VALUES
    ('sap_s4hana',         'SAP S/4HANA',                  'erp',            'oauth2',          ARRAY['gl_transactions','vendors','purchase_orders','invoices','employees']),
    ('oracle_financials',  'Oracle Cloud Financials',       'erp',            'oauth2',          ARRAY['gl_transactions','invoices','purchase_orders','vendors','assets']),
    ('workday',            'Workday HCM',                   'hris',           'oauth2',          ARRAY['employees','payroll','org_chart','time_off','benefits']),
    ('adp_workforce',      'ADP Workforce Now',             'hris',           'api_key',         ARRAY['employees','payroll','time_attendance']),
    ('bamboohr',           'BambooHR',                      'hris',           'api_key',         ARRAY['employees','time_off','org_chart']),
    ('servicenow',         'ServiceNow ITSM',               'itsm',           'oauth2',          ARRAY['incidents','change_requests','cmdb','access_requests']),
    ('jira',               'Jira',                          'itsm',           'oauth2',          ARRAY['issues','projects','sprints','users']),
    ('aws',                'Amazon Web Services',           'cloud',          'service_account', ARRAY['iam_users','s3_buckets','security_groups','cloudtrail','config_rules']),
    ('azure',              'Microsoft Azure',               'cloud',          'oauth2',          ARRAY['ad_users','resource_groups','policy_compliance','activity_logs']),
    ('gcp',                'Google Cloud Platform',         'cloud',          'service_account', ARRAY['iam_bindings','storage_buckets','audit_logs','org_policy']),
    ('okta',               'Okta',                          'identity',       'oauth2',          ARRAY['users','groups','apps','mfa_factors','access_policies']),
    ('azure_ad',           'Microsoft Entra ID',            'identity',       'oauth2',          ARRAY['users','groups','conditional_access','sign_in_logs','mfa_status']),
    ('github',             'GitHub',                        'source_control', 'oauth2',          ARRAY['repositories','pull_requests','users','branch_protections','secrets_scanning']),
    ('gitlab',             'GitLab',                        'source_control', 'oauth2',          ARRAY['projects','merge_requests','users','ci_pipelines']),
    ('salesforce',         'Salesforce CRM',                'crm',            'oauth2',          ARRAY['accounts','contacts','opportunities','users','profiles']),
    ('slack',              'Slack',                         'collaboration',  'oauth2',          ARRAY['channels','users','messages_audit','workspace_settings']),
    ('ms_teams',           'Microsoft Teams',               'collaboration',  'oauth2',          ARRAY['teams','channels','users','meeting_recordings']),
    ('crowdstrike',        'CrowdStrike Falcon',            'security',       'api_key',         ARRAY['endpoints','detections','vulnerabilities','policies']),
    ('qualys',             'Qualys VMDR',                   'security',       'api_key',         ARRAY['vulnerabilities','assets','scans','compliance_reports']),
    ('splunk',             'Splunk',                        'security',       'api_key',         ARRAY['events','alerts','dashboards','saved_searches']),
    ('snowflake',          'Snowflake',                     'custom',         'basic',           ARRAY['query_results','access_logs','data_sharing']),
    ('webhook_generic',    'Generic Webhook',               'custom',         'webhook',         ARRAY['custom_events','raw_payload'])
ON CONFLICT (connector_key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. tenant_integrations  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_integrations (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID        NOT NULL,
    connector_id           UUID        NOT NULL REFERENCES connector_definitions(id),
    integration_name       TEXT        NOT NULL,
    status                 TEXT        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','error','paused','disabled')),
    auth_config            JSONB       NOT NULL DEFAULT '{}',
    field_mappings         JSONB       NOT NULL DEFAULT '{}',
    sync_schedule          TEXT        NOT NULL DEFAULT '0 */6 * * *',
    last_sync_at           TIMESTAMPTZ,
    last_sync_status       TEXT        CHECK (last_sync_status IN ('success','partial','failed')),
    last_sync_record_count INT,
    error_message          TEXT,
    webhook_secret         TEXT,
    webhook_url            TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_integrations_tenant_id
    ON tenant_integrations (tenant_id);

CREATE INDEX IF NOT EXISTS idx_tenant_integrations_tenant_status
    ON tenant_integrations (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_tenant_integrations_tenant_connector
    ON tenant_integrations (tenant_id, connector_id);

ALTER TABLE tenant_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_integrations FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_integrations_tenant_isolation'
          AND tablename  = 'tenant_integrations'
    ) THEN
        CREATE POLICY tenant_integrations_tenant_isolation
            ON tenant_integrations
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON tenant_integrations TO aegis_app;

-- ---------------------------------------------------------------------------
-- 3. integration_sync_logs  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integration_sync_logs (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID        NOT NULL,
    integration_id       UUID        NOT NULL REFERENCES tenant_integrations(id),
    sync_type            TEXT        NOT NULL CHECK (sync_type IN ('scheduled','manual','webhook','initial')),
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMPTZ,
    status               TEXT        NOT NULL CHECK (status IN ('running','success','partial','failed')),
    records_fetched      INT,
    records_processed    INT,
    records_failed       INT,
    data_types_synced    TEXT[]      DEFAULT '{}',
    error_summary        TEXT,
    sync_metadata        JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_integration_sync_logs_tenant_integration
    ON integration_sync_logs (tenant_id, integration_id);

CREATE INDEX IF NOT EXISTS idx_integration_sync_logs_tenant_started
    ON integration_sync_logs (tenant_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_integration_sync_logs_running
    ON integration_sync_logs (status)
    WHERE status = 'running';

ALTER TABLE integration_sync_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_sync_logs FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'integration_sync_logs_tenant_isolation'
          AND tablename  = 'integration_sync_logs'
    ) THEN
        CREATE POLICY integration_sync_logs_tenant_isolation
            ON integration_sync_logs
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON integration_sync_logs TO aegis_app;

-- ---------------------------------------------------------------------------
-- 4. integration_records  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integration_records (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    integration_id    UUID        NOT NULL REFERENCES tenant_integrations(id),
    sync_log_id       UUID        NOT NULL REFERENCES integration_sync_logs(id),
    data_type         TEXT        NOT NULL,
    source_record_id  TEXT        NOT NULL,
    source_system     TEXT        NOT NULL,
    normalized_data   JSONB       NOT NULL DEFAULT '{}',
    raw_data          JSONB       NOT NULL DEFAULT '{}',
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_integration_records_tenant_integration
    ON integration_records (tenant_id, integration_id);

CREATE INDEX IF NOT EXISTS idx_integration_records_tenant_data_type
    ON integration_records (tenant_id, data_type);

CREATE INDEX IF NOT EXISTS idx_integration_records_tenant_ingested
    ON integration_records (tenant_id, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_integration_records_tenant_integration_data_type
    ON integration_records (tenant_id, integration_id, data_type);

ALTER TABLE integration_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_records FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'integration_records_tenant_isolation'
          AND tablename  = 'integration_records'
    ) THEN
        CREATE POLICY integration_records_tenant_isolation
            ON integration_records
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON integration_records TO aegis_app;

-- ---------------------------------------------------------------------------
-- 5. oauth_tokens  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID        NOT NULL,
    integration_id UUID        NOT NULL REFERENCES tenant_integrations(id),
    access_token   TEXT        NOT NULL,
    refresh_token  TEXT,
    token_type     TEXT        NOT NULL DEFAULT 'Bearer',
    expires_at     TIMESTAMPTZ,
    scope          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_integration_token UNIQUE (integration_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_tenant_integration
    ON oauth_tokens (tenant_id, integration_id);

ALTER TABLE oauth_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_tokens FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'oauth_tokens_tenant_isolation'
          AND tablename  = 'oauth_tokens'
    ) THEN
        CREATE POLICY oauth_tokens_tenant_isolation
            ON oauth_tokens
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON oauth_tokens TO aegis_app;

-- ---------------------------------------------------------------------------
-- 6. webhook_events  (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_events (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    integration_id    UUID        NOT NULL REFERENCES tenant_integrations(id),
    event_type        TEXT        NOT NULL,
    source_event_id   TEXT,
    payload           JSONB       NOT NULL DEFAULT '{}',
    headers           JSONB       NOT NULL DEFAULT '{}',
    processing_status TEXT        NOT NULL DEFAULT 'received' CHECK (processing_status IN ('received','processing','processed','failed','ignored')),
    processed_at      TIMESTAMPTZ,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_tenant_integration
    ON webhook_events (tenant_id, integration_id);

CREATE INDEX IF NOT EXISTS idx_webhook_events_tenant_received
    ON webhook_events (tenant_id, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_events_tenant_processing_status
    ON webhook_events (tenant_id, processing_status);

ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'webhook_events_tenant_isolation'
          AND tablename  = 'webhook_events'
    ) THEN
        CREATE POLICY webhook_events_tenant_isolation
            ON webhook_events
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON webhook_events TO aegis_app;

-- ---------------------------------------------------------------------------
-- 7. field_mapping_templates  (PLATFORM — no RLS, SELECT only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_mapping_templates (
    id             UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_key  TEXT    NOT NULL,
    data_type      TEXT    NOT NULL,
    source_field   TEXT    NOT NULL,
    target_field   TEXT    NOT NULL,
    transform_fn   TEXT,
    is_required    BOOLEAN NOT NULL DEFAULT false,
    description    TEXT,
    CONSTRAINT uq_mapping_template UNIQUE (connector_key, data_type, source_field)
);

GRANT SELECT ON field_mapping_templates TO aegis_app;

-- Seed: workday → employees (8 mappings)
INSERT INTO field_mapping_templates (connector_key, data_type, source_field, target_field, transform_fn, is_required) VALUES
    ('workday', 'employees', 'Worker_ID',                                                          'employee_id',        NULL,                                              true),
    ('workday', 'employees', 'Full_Name',                                                          'full_name',          NULL,                                              true),
    ('workday', 'employees', 'Email_Primary_Work',                                                 'email',              NULL,                                              true),
    ('workday', 'employees', 'Worker_Status',                                                      'employment_status',  'map: Active→active, Terminated→terminated',       false),
    ('workday', 'employees', 'Management_Chain_Data.Primary_Job.Position.Department',              'department',         NULL,                                              false),
    ('workday', 'employees', 'Management_Chain_Data.Primary_Job.Position.Job_Profile',             'job_title',          NULL,                                              false),
    ('workday', 'employees', 'Management_Chain_Data.Primary_Job.Position.Manager',                 'manager_id',         NULL,                                              false),
    ('workday', 'employees', 'Hire_Date',                                                          'hire_date',          NULL,                                              false)
ON CONFLICT (connector_key, data_type, source_field) DO NOTHING;

-- Seed: okta → users (7 mappings)
INSERT INTO field_mapping_templates (connector_key, data_type, source_field, target_field, transform_fn, is_required) VALUES
    ('okta', 'users', 'id',                     'source_user_id',    NULL,                                                    true),
    ('okta', 'users', 'profile.login',           'email',             NULL,                                                    true),
    ('okta', 'users', 'profile.firstName + profile.lastName', 'full_name', 'concat: firstName lastName',                      false),
    ('okta', 'users', 'status',                  'employment_status', 'map: ACTIVE→active, DEPROVISIONED→terminated',          false),
    ('okta', 'users', 'profile.department',      'department',        NULL,                                                    false),
    ('okta', 'users', 'profile.title',           'job_title',         NULL,                                                    false),
    ('okta', 'users', 'profile.mobilePhone',     'phone',             NULL,                                                    false)
ON CONFLICT (connector_key, data_type, source_field) DO NOTHING;

-- Seed: aws → iam_users (6 mappings)
INSERT INTO field_mapping_templates (connector_key, data_type, source_field, target_field, transform_fn, is_required) VALUES
    ('aws', 'iam_users', 'UserName',         'username',        NULL,                          true),
    ('aws', 'iam_users', 'UserId',           'source_user_id',  NULL,                          true),
    ('aws', 'iam_users', 'Arn',              'arn',             NULL,                          false),
    ('aws', 'iam_users', 'CreateDate',       'created_at',      NULL,                          false),
    ('aws', 'iam_users', 'PasswordLastUsed', 'last_login_at',   NULL,                          false),
    ('aws', 'iam_users', 'MFADevices',       'mfa_enabled',     'expr: len(MFADevices) > 0',   false)
ON CONFLICT (connector_key, data_type, source_field) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 8. integration_data_mappings  (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integration_data_mappings (
    id                           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                    UUID        NOT NULL,
    integration_id               UUID        NOT NULL REFERENCES tenant_integrations(id),
    data_type                    TEXT        NOT NULL,
    mappings                     JSONB       NOT NULL DEFAULT '[]',
    auto_populate_from_template  BOOLEAN     NOT NULL DEFAULT true,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_integration_data_type UNIQUE (integration_id, data_type)
);

CREATE INDEX IF NOT EXISTS idx_integration_data_mappings_tenant_integration
    ON integration_data_mappings (tenant_id, integration_id);

ALTER TABLE integration_data_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_data_mappings FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'integration_data_mappings_tenant_isolation'
          AND tablename  = 'integration_data_mappings'
    ) THEN
        CREATE POLICY integration_data_mappings_tenant_isolation
            ON integration_data_mappings
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON integration_data_mappings TO aegis_app;

-- Sprint 14: Enterprise Integration Hub schema complete (8 tables, 22 connectors seeded, field mapping templates seeded)
