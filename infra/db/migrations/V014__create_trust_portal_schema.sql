-- =============================================================================
-- V014__create_trust_portal_schema.sql
-- Project: Aegis 2026 – Sprint 10 – Client-Facing Trust Portal
--
-- Purpose:
--   Creates the Trust Portal schema: per-tenant portal configuration,
--   document library, NDA signing, access logging, questionnaire deflection,
--   and AI chatbot session/message persistence.
--
-- Design:
--   * Fully idempotent — safe to run multiple times (CREATE ... IF NOT EXISTS,
--     DO $$ ... $$ guards on RLS policies checking pg_policies).
--   * All tables are per-tenant and enforce RLS via
--     current_setting('app.tenant_id', TRUE)::UUID.
--   * portal_ndas and trust_portal_access_logs and portal_chatbot_messages are
--     append-only: aegis_app receives INSERT and SELECT only — no UPDATE or
--     DELETE — to preserve immutable audit trails.
--
-- Tables:
--   trust_portal_configs              – per-tenant portal configuration
--   trust_portal_documents            – per-tenant document library
--   portal_ndas                       – per-tenant immutable NDA signing records
--   trust_portal_access_logs          – per-tenant immutable access event log
--   portal_questionnaire_deflections  – per-tenant questionnaire deflection jobs
--   portal_chatbot_sessions           – per-tenant chatbot session state
--   portal_chatbot_messages           – per-tenant immutable chatbot message log
--
-- Roles assumed to exist: aegis_app
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. trust_portal_configs
--    Per-tenant public-facing Trust Portal configuration.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.trust_portal_configs (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID        NOT NULL,
    slug                    TEXT        NOT NULL UNIQUE,
    company_name            TEXT        NOT NULL,
    tagline                 TEXT,
    logo_url                TEXT,
    primary_color           TEXT        NOT NULL DEFAULT '#6366f1',
    portal_enabled          BOOLEAN     NOT NULL DEFAULT false,
    require_nda             BOOLEAN     NOT NULL DEFAULT true,
    nda_document_url        TEXT,
    nda_version             TEXT        NOT NULL DEFAULT '1.0',
    show_compliance_scores  BOOLEAN     NOT NULL DEFAULT true,
    show_framework_badges   BOOLEAN     NOT NULL DEFAULT true,
    allowed_frameworks      TEXT[]               DEFAULT '{}',
    chatbot_enabled         BOOLEAN     NOT NULL DEFAULT true,
    chatbot_welcome_message TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.trust_portal_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trust_portal_configs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'trust_portal_configs'
          AND policyname = 'trust_portal_configs_tenant_isolation'
    ) THEN
        CREATE POLICY trust_portal_configs_tenant_isolation
            ON public.trust_portal_configs
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.trust_portal_configs TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_trust_portal_configs_tenant_id
    ON public.trust_portal_configs (tenant_id);

-- UNIQUE(slug) already enforced by the column constraint above; a supporting
-- index is created implicitly by PostgreSQL — no explicit CREATE INDEX needed.

-- ---------------------------------------------------------------------------
-- 2. trust_portal_documents
--    Per-tenant document library for the public Trust Portal.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.trust_portal_documents (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL,
    display_name     TEXT        NOT NULL,
    description      TEXT,
    document_type    TEXT        NOT NULL CHECK (document_type IN (
                         'soc2_report','iso_cert','pentest','security_overview',
                         'privacy_policy','dpa','custom')),
    minio_key        TEXT        NOT NULL,
    file_size_bytes  BIGINT,
    requires_nda     BOOLEAN     NOT NULL DEFAULT true,
    is_visible       BOOLEAN     NOT NULL DEFAULT true,
    valid_from       DATE,
    valid_until      DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.trust_portal_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trust_portal_documents FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'trust_portal_documents'
          AND policyname = 'trust_portal_documents_tenant_isolation'
    ) THEN
        CREATE POLICY trust_portal_documents_tenant_isolation
            ON public.trust_portal_documents
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.trust_portal_documents TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_trust_portal_documents_tenant_id
    ON public.trust_portal_documents (tenant_id);

-- Partial index — only rows where valid_until is set are relevant for expiry queries.
CREATE INDEX IF NOT EXISTS idx_trust_portal_documents_tenant_valid_until
    ON public.trust_portal_documents (tenant_id, valid_until)
    WHERE valid_until IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. portal_ndas
--    Per-tenant immutable NDA signing records.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE — to
--    preserve the legal signing audit trail.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.portal_ndas (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    signatory_name    TEXT        NOT NULL,
    signatory_email   TEXT        NOT NULL,
    signatory_company TEXT,
    ip_address        INET        NOT NULL,
    user_agent        TEXT,
    nda_version       TEXT        NOT NULL,
    accepted_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.portal_ndas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_ndas FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'portal_ndas'
          AND policyname = 'portal_ndas_tenant_isolation'
    ) THEN
        CREATE POLICY portal_ndas_tenant_isolation
            ON public.portal_ndas
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable NDA signing records.
GRANT SELECT, INSERT ON public.portal_ndas TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_portal_ndas_tenant_email
    ON public.portal_ndas (tenant_id, signatory_email);

CREATE INDEX IF NOT EXISTS idx_portal_ndas_tenant_accepted_at
    ON public.portal_ndas (tenant_id, accepted_at DESC);

-- ---------------------------------------------------------------------------
-- 4. trust_portal_access_logs
--    Per-tenant immutable access event log for the Trust Portal.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE — to
--    preserve the access audit trail.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.trust_portal_access_logs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL,
    event_type       TEXT        NOT NULL CHECK (event_type IN (
                         'page_view','document_view','document_download',
                         'chatbot_message','nda_signed','questionnaire_submitted',
                         'questionnaire_deflected')),
    visitor_email    TEXT,
    visitor_company  TEXT,
    document_id      UUID        REFERENCES public.trust_portal_documents(id) ON DELETE SET NULL,
    ip_address       INET        NOT NULL,
    user_agent       TEXT,
    metadata         JSONB       NOT NULL DEFAULT '{}',
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.trust_portal_access_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trust_portal_access_logs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'trust_portal_access_logs'
          AND policyname = 'trust_portal_access_logs_tenant_isolation'
    ) THEN
        CREATE POLICY trust_portal_access_logs_tenant_isolation
            ON public.trust_portal_access_logs
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable access event log.
GRANT SELECT, INSERT ON public.trust_portal_access_logs TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_trust_portal_access_logs_tenant_occurred_at
    ON public.trust_portal_access_logs (tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_trust_portal_access_logs_tenant_event_type
    ON public.trust_portal_access_logs (tenant_id, event_type);

-- Partial index — visitor_email is nullable; only index rows where it is set.
CREATE INDEX IF NOT EXISTS idx_trust_portal_access_logs_tenant_visitor_email
    ON public.trust_portal_access_logs (tenant_id, visitor_email)
    WHERE visitor_email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. portal_questionnaire_deflections
--    Per-tenant questionnaire deflection jobs: incoming security questionnaires
--    are matched against the tenant's Trust Portal document library and
--    AI-generated response documents are produced automatically.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.portal_questionnaire_deflections (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID        NOT NULL,
    requester_name        TEXT        NOT NULL,
    requester_email       TEXT        NOT NULL,
    requester_company     TEXT,
    questionnaire_type    TEXT        CHECK (questionnaire_type IN (
                              'sig_lite','caiq','soc2_inquiry','custom','unknown')),
    raw_questions         JSONB       NOT NULL DEFAULT '[]',
    deflection_mappings   JSONB                DEFAULT '[]',
    response_document_key TEXT,
    status                TEXT        NOT NULL DEFAULT 'pending' CHECK (status IN (
                              'pending','processing','completed','failed')),
    ai_model_used         TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMPTZ
);

ALTER TABLE public.portal_questionnaire_deflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_questionnaire_deflections FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'portal_questionnaire_deflections'
          AND policyname = 'portal_questionnaire_deflections_tenant_isolation'
    ) THEN
        CREATE POLICY portal_questionnaire_deflections_tenant_isolation
            ON public.portal_questionnaire_deflections
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.portal_questionnaire_deflections TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_portal_questionnaire_deflections_tenant_status
    ON public.portal_questionnaire_deflections (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_portal_questionnaire_deflections_tenant_created_at
    ON public.portal_questionnaire_deflections (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 6. portal_chatbot_sessions
--    Per-tenant chatbot session state: tracks active visitor chat sessions
--    including visitor identity (if provided), session token, and activity.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.portal_chatbot_sessions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID        NOT NULL,
    visitor_email    TEXT,
    visitor_company  TEXT,
    session_token    TEXT        NOT NULL UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_count    INT         NOT NULL DEFAULT 0
);

ALTER TABLE public.portal_chatbot_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_chatbot_sessions FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'portal_chatbot_sessions'
          AND policyname = 'portal_chatbot_sessions_tenant_isolation'
    ) THEN
        CREATE POLICY portal_chatbot_sessions_tenant_isolation
            ON public.portal_chatbot_sessions
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.portal_chatbot_sessions TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_portal_chatbot_sessions_tenant_id
    ON public.portal_chatbot_sessions (tenant_id);

-- UNIQUE(session_token) already enforced by the column constraint above; a
-- supporting index is created implicitly by PostgreSQL — no explicit CREATE
-- INDEX needed.

-- ---------------------------------------------------------------------------
-- 7. portal_chatbot_messages
--    Per-tenant immutable chatbot message log.
--    aegis_app receives INSERT and SELECT only — no UPDATE or DELETE — to
--    preserve the conversation audit trail.
--    RLS enforced.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.portal_chatbot_messages (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID        NOT NULL,
    session_id UUID        NOT NULL REFERENCES public.portal_chatbot_sessions(id),
    role       TEXT        NOT NULL CHECK (role IN ('user','assistant')),
    content    TEXT        NOT NULL,
    sources    JSONB       NOT NULL DEFAULT '[]',
    sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.portal_chatbot_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_chatbot_messages FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'portal_chatbot_messages'
          AND policyname = 'portal_chatbot_messages_tenant_isolation'
    ) THEN
        CREATE POLICY portal_chatbot_messages_tenant_isolation
            ON public.portal_chatbot_messages
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END;
$$;

-- Append-only: no UPDATE or DELETE — immutable chatbot message log.
GRANT SELECT, INSERT ON public.portal_chatbot_messages TO aegis_app;

CREATE INDEX IF NOT EXISTS idx_portal_chatbot_messages_tenant_session
    ON public.portal_chatbot_messages (tenant_id, session_id);

CREATE INDEX IF NOT EXISTS idx_portal_chatbot_messages_tenant_sent_at
    ON public.portal_chatbot_messages (tenant_id, sent_at DESC);

-- Sprint 10: Trust Portal schema complete (7 tables)
