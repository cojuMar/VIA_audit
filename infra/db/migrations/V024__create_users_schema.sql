-- V024: VIA User Authentication Schema
-- Creates the via_users table for platform authentication.
-- Users are tenant-scoped with role-based access control.

CREATE TABLE IF NOT EXISTS via_users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    email           TEXT        NOT NULL,
    password_hash   TEXT        NOT NULL,
    full_name       TEXT        NOT NULL DEFAULT '',
    role            TEXT        NOT NULL DEFAULT 'end_user'
                                CHECK (role IN ('super_admin', 'admin', 'end_user')),
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT via_users_tenant_email_uq UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_via_users_tenant
    ON via_users (tenant_id);

CREATE INDEX IF NOT EXISTS idx_via_users_email
    ON via_users (email);

-- Row Level Security
ALTER TABLE via_users ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'via_users' AND policyname = 'via_users_tenant_isolation'
    ) THEN
        CREATE POLICY via_users_tenant_isolation ON via_users
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    END IF;
END $$;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON via_users TO aegis_app;

-- Updated-at trigger (reuse existing function if it exists)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'via_users_updated_at'
    ) THEN
        CREATE TRIGGER via_users_updated_at
            BEFORE UPDATE ON via_users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
EXCEPTION WHEN undefined_function THEN
    -- update_updated_at_column doesn't exist yet, skip trigger
    NULL;
END $$;
