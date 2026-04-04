-- =============================================================================
-- V009__create_dashboard_schema.sql
-- Project Aegis 2026 – Sprint 5: Tri-Modal UX Dashboard
-- =============================================================================
-- Purpose:
--   Creates the full dashboard schema required by the dashboard-service BFF.
--   All DDL is fully idempotent – every CREATE TABLE, CREATE INDEX, and INSERT
--   uses IF NOT EXISTS / ON CONFLICT DO NOTHING so this migration can be
--   replayed safely without error.  RLS policies are guarded by DO $$ $$ blocks
--   that check pg_policies before issuing CREATE POLICY.
--
-- Tables created:
--   1. white_label_configs      – per-tenant branding for Firm Mode
--   2. dashboard_configs        – per-user layout and mode preference
--   3. audit_hub_items          – SMB Mode action items in the Audit Hub
--   4. health_score_snapshots   – time-series health scores for Autonomous Mode
--   5. firm_client_links        – Firm Mode: firm-to-client tenant relationships
--
-- Row-Level Security:
--   Tables 1–4 enforce tenant isolation via RLS (FORCE RLS).
--   Table 5 (firm_client_links) has NO RLS – managed by platform admin.
--
-- Author  : Aegis Platform Team
-- Sprint  : 5 (Tri-Modal UX Dashboard)
-- Created : 2026-04-03
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSION
-- ---------------------------------------------------------------------------
-- pgcrypto provides gen_random_uuid() used in all PK defaults.
-- Idempotent – safe to run even if already installed.
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- TABLE 1: white_label_configs
-- =============================================================================
-- Stores per-tenant branding configuration for Firm Mode white-labeling.
-- One row per tenant (enforced by UNIQUE on tenant_id).
--
-- primary_color / secondary_color / accent_color:
--   CSS hex color strings.  Defaults match the Aegis platform design system.
--
-- font_family:
--   Google Fonts or system font stack name injected into the CSS custom
--   property --font-family at runtime.
--
-- custom_css:
--   Optional freeform CSS injected into the dashboard <style> block.
--   Sanitised by the application layer before storage.
-- =============================================================================
CREATE TABLE IF NOT EXISTS white_label_configs (
    white_label_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL UNIQUE
                                  REFERENCES tenants(tenant_id),
    firm_name         TEXT        NOT NULL,
    -- HTTPS URL to the firm's logo asset hosted in MinIO / CDN.
    logo_url          TEXT,
    primary_color     TEXT        NOT NULL DEFAULT '#1a56db',
    secondary_color   TEXT        NOT NULL DEFAULT '#7e3af2',
    accent_color      TEXT        NOT NULL DEFAULT '#0e9f6e',
    font_family       TEXT        NOT NULL DEFAULT 'Inter',
    -- Optional freeform CSS overrides (sanitised at the app layer).
    custom_css        TEXT,
    support_email     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT white_label_configs_pkey PRIMARY KEY (white_label_id)
);

ALTER TABLE white_label_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE white_label_configs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'white_label_configs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON white_label_configs
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE
    ON white_label_configs
    TO aegis_app;

-- =============================================================================
-- TABLE 2: dashboard_configs
-- =============================================================================
-- Stores per-user dashboard layout and tri-modal mode preference.
-- One row per (tenant_id, user_id) pair, enforced by a UNIQUE constraint.
--
-- mode:
--   'firm'        – Accounting Firm view: multi-client portfolio panel
--   'smb'         – SMB view: Audit Hub action items and guided workflows
--   'autonomous'  – Autonomous Mode: health score trending and AI-driven alerts
--
-- layout_json:
--   Serialised widget grid configuration (positions and sizes).
--   Consumed and produced by the React grid layout library on the frontend.
--
-- pinned_controls:
--   Array of control IDs (e.g. 'CC6.1', 'A.9.1.2') pinned to the top of the
--   control panel for quick access.
--
-- default_framework:
--   The compliance framework shown by default in new sessions.
--
-- date_range_days:
--   Default trailing window for trend charts (30, 60, 90, 180, 365).
-- =============================================================================
CREATE TABLE IF NOT EXISTS dashboard_configs (
    config_id           UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id           UUID        NOT NULL REFERENCES tenants(tenant_id),
    user_id             UUID        NOT NULL REFERENCES users(user_id),
    mode                TEXT        NOT NULL DEFAULT 'smb'
                                    CHECK (mode IN ('firm', 'smb', 'autonomous')),
    -- Widget positions and sizes for the React grid layout.
    layout_json         JSONB       NOT NULL DEFAULT '{}',
    -- Array of control IDs pinned to the top of the control panel.
    pinned_controls     TEXT[]      NOT NULL DEFAULT '{}',
    default_framework   TEXT        NOT NULL DEFAULT 'soc2',
    date_range_days     INTEGER     NOT NULL DEFAULT 30,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT dashboard_configs_pkey PRIMARY KEY (config_id),
    CONSTRAINT dashboard_configs_tenant_user_unique UNIQUE (tenant_id, user_id)
);

ALTER TABLE dashboard_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_configs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'dashboard_configs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON dashboard_configs
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE
    ON dashboard_configs
    TO aegis_app;

-- =============================================================================
-- TABLE 3: audit_hub_items
-- =============================================================================
-- Stores SMB Mode action items surfaced in the Audit Hub widget.  Each row
-- represents one compliance gap or outstanding task for a specific framework
-- control within a tenant.
--
-- status lifecycle:
--   open → in_progress → resolved
--                     → waived  (management decision, requires justification)
--
-- priority:
--   Determines sort order in the Audit Hub list.  The partial index below
--   covers the most common query: open/in-progress items ordered by priority
--   and due date.
--
-- evidence_count:
--   Denormalised count of attached evidence records, updated by the
--   dashboard-service on evidence attachment / detachment events.
--
-- narrative_id:
--   Optional FK to an audit_narratives row if a RAG-generated narrative has
--   been produced for this control.
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_hub_items (
    item_id           UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL REFERENCES tenants(tenant_id),
    framework         TEXT        NOT NULL,
    control_id        TEXT        NOT NULL,
    title             TEXT        NOT NULL,
    description       TEXT,
    status            TEXT        NOT NULL DEFAULT 'open'
                                  CHECK (status IN ('open', 'in_progress', 'resolved', 'waived')),
    priority          TEXT        NOT NULL DEFAULT 'medium'
                                  CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    due_date          DATE,
    assigned_to       UUID        REFERENCES users(user_id),
    -- Denormalised count of attached evidence records.
    evidence_count    INTEGER     NOT NULL DEFAULT 0,
    -- Optional link to a RAG-generated narrative for this control.
    narrative_id      UUID        REFERENCES audit_narratives(narrative_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT audit_hub_items_pkey PRIMARY KEY (item_id)
);

ALTER TABLE audit_hub_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_hub_items FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'audit_hub_items'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON audit_hub_items
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- Partial index: covers the primary Audit Hub query – active items for a
-- tenant, sorted by highest priority first, then earliest due date.
-- Excludes resolved items to keep the index small.
CREATE INDEX IF NOT EXISTS idx_audit_hub_status
    ON audit_hub_items (tenant_id, status, priority DESC, due_date ASC)
    WHERE status != 'resolved';

GRANT SELECT, INSERT, UPDATE
    ON audit_hub_items
    TO aegis_app;

-- =============================================================================
-- TABLE 4: health_score_snapshots
-- =============================================================================
-- Stores time-series health score snapshots consumed by the Autonomous Mode
-- trending charts.  One row per (tenant_id, framework) per snapshot interval
-- (default: every 15 minutes, driven by HEALTH_SCORE_CRON in dashboard-service).
--
-- All score columns are NUMERIC(4,3) in [0, 1]:
--   overall_score      – composite weighted score across all sub-dimensions
--   access_control     – access control and identity management health
--   data_integrity     – data integrity and change management health
--   anomaly_rate       – inverse of normalised anomaly detection rate
--   evidence_freshness – recency of collected evidence vs. expected cadence
--   narrative_quality  – average combined_score of recent RAG narratives
--
-- open_issues / critical_issues:
--   Denormalised counts from audit_hub_items at snapshot time, stored so the
--   trending chart can display issue volume alongside the score without joining.
-- =============================================================================
CREATE TABLE IF NOT EXISTS health_score_snapshots (
    snapshot_id        UUID         NOT NULL DEFAULT gen_random_uuid(),
    tenant_id          UUID         NOT NULL REFERENCES tenants(tenant_id),
    framework          TEXT         NOT NULL,
    snapshot_time      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Composite health score in [0, 1].  Required.
    overall_score      NUMERIC(4,3) NOT NULL CHECK (overall_score BETWEEN 0 AND 1),
    -- Sub-dimension scores in [0, 1].  NULL if the dimension cannot be computed
    -- (e.g. no evidence exists yet for a newly onboarded tenant).
    access_control     NUMERIC(4,3) CHECK (access_control BETWEEN 0 AND 1),
    data_integrity     NUMERIC(4,3) CHECK (data_integrity BETWEEN 0 AND 1),
    anomaly_rate       NUMERIC(4,3) CHECK (anomaly_rate BETWEEN 0 AND 1),
    evidence_freshness NUMERIC(4,3) CHECK (evidence_freshness BETWEEN 0 AND 1),
    narrative_quality  NUMERIC(4,3) CHECK (narrative_quality BETWEEN 0 AND 1),
    -- Denormalised issue counts at snapshot time.
    open_issues        INTEGER      NOT NULL DEFAULT 0,
    critical_issues    INTEGER      NOT NULL DEFAULT 0,

    CONSTRAINT health_score_snapshots_pkey PRIMARY KEY (snapshot_id)
);

ALTER TABLE health_score_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_score_snapshots FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'health_score_snapshots'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON health_score_snapshots
            USING (tenant_id = current_setting('app.tenant_id')::UUID);
    END IF;
END;
$$;

-- Full time-series index: supports arbitrary date-range queries on the
-- trending chart (ordered most-recent first).
CREATE INDEX IF NOT EXISTS idx_health_snapshots_time
    ON health_score_snapshots (tenant_id, framework, snapshot_time DESC);

-- Partial index: hot path for the dashboard's default 90-day trending window.
-- Keeps the working set small for the most common access pattern.
CREATE INDEX IF NOT EXISTS idx_health_snapshots_recent
    ON health_score_snapshots (tenant_id, framework, snapshot_time DESC)
    WHERE snapshot_time > NOW() - INTERVAL '90 days';

GRANT SELECT, INSERT
    ON health_score_snapshots
    TO aegis_app;

-- =============================================================================
-- TABLE 5: firm_client_links
-- =============================================================================
-- Records the relationship between an accounting firm tenant and each of its
-- client tenants in Firm Mode.  The dashboard-service uses this table to build
-- the multi-client portfolio panel and to enforce cross-tenant read access for
-- firm users.
--
-- No RLS – this table is managed by platform administrators and is not subject
-- to per-tenant row filtering.  Application-layer authorisation controls access.
--
-- client_alias:
--   Optional display name for the client as shown in the firm's portfolio panel.
--   When NULL, the firm sees the client's canonical tenant name.
--
-- engagement_code:
--   Firm's internal reference code (e.g. engagement ID from their practice
--   management system).  Stored for display purposes only.
--
-- is_active:
--   Soft-delete flag.  Inactive links are hidden from the portfolio panel but
--   retained for audit history.
--
-- CHECK (firm_tenant_id != client_tenant_id):
--   Prevents a tenant from being linked to itself.
-- =============================================================================
CREATE TABLE IF NOT EXISTS firm_client_links (
    link_id            UUID        NOT NULL DEFAULT gen_random_uuid(),
    firm_tenant_id     UUID        NOT NULL REFERENCES tenants(tenant_id),
    client_tenant_id   UUID        NOT NULL REFERENCES tenants(tenant_id),
    -- Optional display name for the client in the firm's portfolio panel.
    client_alias       TEXT,
    -- Firm's internal engagement reference code.
    engagement_code    TEXT,
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    linked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT firm_client_links_pkey PRIMARY KEY (link_id),
    CONSTRAINT firm_client_links_pair_unique
        UNIQUE (firm_tenant_id, client_tenant_id),
    CONSTRAINT firm_client_links_no_self_link
        CHECK (firm_tenant_id != client_tenant_id)
);

-- No RLS – managed by platform admin, not subject to per-tenant row filtering.

GRANT SELECT, INSERT, UPDATE
    ON firm_client_links
    TO aegis_app;

-- =============================================================================
-- END OF MIGRATION V009
-- =============================================================================
