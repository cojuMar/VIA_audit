-- V025: Notification System for VIA Platform
-- Per-user, tenant-scoped notification store.
-- All CRUD goes through auth-service which enforces RLS via SET app.tenant_id.

CREATE TABLE IF NOT EXISTS notifications (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL,
    user_id     UUID        NOT NULL REFERENCES via_users(id) ON DELETE CASCADE,
    type        TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    body        TEXT        NOT NULL DEFAULT '',
    entity_type TEXT,
    entity_id   TEXT,
    severity    TEXT        NOT NULL DEFAULT 'info'
                            CHECK (severity IN ('info', 'warning', 'critical')),
    read        BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary access pattern: tenant + user + unread + recency
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_user_read
    ON notifications (tenant_id, user_id, read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_tenant_created
    ON notifications (tenant_id, created_at DESC);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'notifications' AND policyname = 'notifications_tenant_isolation'
    ) THEN
        CREATE POLICY notifications_tenant_isolation ON notifications
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO aegis_app;
