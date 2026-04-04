-- =============================================================================
-- V019__create_ai_agent_schema.sql
-- Sprint 15: Agentic AI & Natural Language Platform Interface
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. agent_conversations
--    Tenant-mutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT, UPDATE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_conversations (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID        NOT NULL,
    title                TEXT        NOT NULL DEFAULT 'New Conversation',
    user_identifier      TEXT,
    model_used           TEXT        NOT NULL DEFAULT 'claude-opus-4-5',
    status               TEXT        NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active','archived','deleted')),
    message_count        INT         NOT NULL DEFAULT 0,
    total_input_tokens   INT         NOT NULL DEFAULT 0,
    total_output_tokens  INT         NOT NULL DEFAULT 0,
    context_summary      TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_conversations_tenant
    ON agent_conversations (tenant_id);

CREATE INDEX IF NOT EXISTS idx_agent_conversations_tenant_status
    ON agent_conversations (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_agent_conversations_tenant_updated_at
    ON agent_conversations (tenant_id, updated_at DESC);

ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conversations FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_conversations_tenant_isolation'
          AND tablename  = 'agent_conversations'
    ) THEN
        CREATE POLICY agent_conversations_tenant_isolation
            ON agent_conversations
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON agent_conversations TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. agent_messages
--    Tenant-immutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT  — NO UPDATE, NO DELETE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    conversation_id UUID        NOT NULL REFERENCES agent_conversations(id),
    role            TEXT        NOT NULL CHECK (role IN ('user','assistant','tool_result')),
    content         TEXT        NOT NULL,
    tool_calls      JSONB                DEFAULT '[]',
    tool_results    JSONB                DEFAULT '[]',
    input_tokens    INT,
    output_tokens   INT,
    model_used      TEXT,
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_tenant_conversation
    ON agent_messages (tenant_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_agent_messages_tenant_created_at
    ON agent_messages (tenant_id, created_at DESC);

ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_messages_tenant_isolation'
          AND tablename  = 'agent_messages'
    ) THEN
        CREATE POLICY agent_messages_tenant_isolation
            ON agent_messages
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON agent_messages TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. agent_tool_calls
--    Tenant-immutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT  — NO UPDATE, NO DELETE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    message_id        UUID        NOT NULL REFERENCES agent_messages(id),
    conversation_id   UUID        NOT NULL REFERENCES agent_conversations(id),
    tool_name         TEXT        NOT NULL,
    tool_input        JSONB       NOT NULL DEFAULT '{}',
    tool_output       JSONB,
    execution_time_ms INT,
    success           BOOLEAN     NOT NULL DEFAULT true,
    error_message     TEXT,
    called_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_tenant_conversation
    ON agent_tool_calls (tenant_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_tenant_tool_name
    ON agent_tool_calls (tenant_id, tool_name);

CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_tenant_called_at
    ON agent_tool_calls (tenant_id, called_at DESC);

ALTER TABLE agent_tool_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_tool_calls FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_tool_calls_tenant_isolation'
          AND tablename  = 'agent_tool_calls'
    ) THEN
        CREATE POLICY agent_tool_calls_tenant_isolation
            ON agent_tool_calls
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON agent_tool_calls TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. agent_reports
--    Tenant-immutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT  — NO UPDATE, NO DELETE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_reports (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID        NOT NULL,
    conversation_id     UUID        REFERENCES agent_conversations(id),
    report_type         TEXT        NOT NULL
                            CHECK (report_type IN (
                                'compliance_summary','gap_analysis','vendor_risk',
                                'monitoring_findings','training_status',
                                'audit_readiness','custom'
                            )),
    title               TEXT        NOT NULL,
    content             TEXT        NOT NULL,
    format              TEXT        NOT NULL DEFAULT 'markdown'
                            CHECK (format IN ('markdown','html','json')),
    model_used          TEXT        NOT NULL,
    generation_time_ms  INT,
    metadata            JSONB       NOT NULL DEFAULT '{}',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_reports_tenant_report_type
    ON agent_reports (tenant_id, report_type);

CREATE INDEX IF NOT EXISTS idx_agent_reports_tenant_generated_at
    ON agent_reports (tenant_id, generated_at DESC);

ALTER TABLE agent_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_reports FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_reports_tenant_isolation'
          AND tablename  = 'agent_reports'
    ) THEN
        CREATE POLICY agent_reports_tenant_isolation
            ON agent_reports
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON agent_reports TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. agent_scheduled_queries
--    Tenant-mutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT, UPDATE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_scheduled_queries (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID        NOT NULL,
    query_name             TEXT        NOT NULL,
    natural_language_query TEXT        NOT NULL,
    schedule_cron          TEXT        NOT NULL DEFAULT '0 9 * * 1',
    is_active              BOOLEAN     NOT NULL DEFAULT true,
    last_run_at            TIMESTAMPTZ,
    last_report_id         UUID        REFERENCES agent_reports(id),
    delivery_config        JSONB       NOT NULL DEFAULT '{}',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_scheduled_queries_tenant
    ON agent_scheduled_queries (tenant_id);

CREATE INDEX IF NOT EXISTS idx_agent_scheduled_queries_tenant_is_active
    ON agent_scheduled_queries (tenant_id, is_active);

ALTER TABLE agent_scheduled_queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_scheduled_queries FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_scheduled_queries_tenant_isolation'
          AND tablename  = 'agent_scheduled_queries'
    ) THEN
        CREATE POLICY agent_scheduled_queries_tenant_isolation
            ON agent_scheduled_queries
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON agent_scheduled_queries TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. agent_feedback
--    Tenant-immutable (RLS + FORCE ROW LEVEL SECURITY)
--    Grants: SELECT, INSERT  — NO UPDATE, NO DELETE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_feedback (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    message_id      UUID        NOT NULL REFERENCES agent_messages(id),
    conversation_id UUID        NOT NULL REFERENCES agent_conversations(id),
    rating          INT         NOT NULL CHECK (rating BETWEEN 1 AND 5),
    feedback_type   TEXT        CHECK (feedback_type IN (
                        'helpful','inaccurate','incomplete','off_topic','hallucination'
                    )),
    comment         TEXT,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_tenant_conversation
    ON agent_feedback (tenant_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_tenant_feedback_type
    ON agent_feedback (tenant_id, feedback_type);

ALTER TABLE agent_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_feedback FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'agent_feedback_tenant_isolation'
          AND tablename  = 'agent_feedback'
    ) THEN
        CREATE POLICY agent_feedback_tenant_isolation
            ON agent_feedback
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON agent_feedback TO aegis_app;

-- Sprint 15: Agentic AI & Natural Language Platform Interface schema complete (6 tables)
