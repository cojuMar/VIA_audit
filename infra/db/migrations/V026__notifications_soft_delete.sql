-- V026: Soft-delete for notifications
-- Project standard: no physical deletes in production.
-- Records are flagged deleted=true and excluded from all queries.
-- Also drops the ON DELETE CASCADE FK (physical row removal) and
-- replaces it with ON DELETE RESTRICT so user records must be
-- soft-deleted at the application layer instead.

-- 1. Add soft-delete columns
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS deleted    BOOLEAN     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- 2. Drop the CASCADE FK, replace with RESTRICT
--    (no physical deletion of notifications when a user is soft-deleted)
ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;

ALTER TABLE notifications
    ADD CONSTRAINT notifications_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES via_users(id)
        ON DELETE RESTRICT;

-- 3. Rebuild the primary query index to exclude deleted rows
DROP INDEX IF EXISTS idx_notifications_tenant_user_read;

CREATE INDEX IF NOT EXISTS idx_notifications_tenant_user_active
    ON notifications (tenant_id, user_id, read, created_at DESC)
    WHERE deleted = false;
