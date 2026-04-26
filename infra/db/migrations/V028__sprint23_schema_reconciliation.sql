-- ============================================================================
--  V028 — Sprint 23: Schema Reconciliation
-- ============================================================================
--
--  Resolves the two duplicate-schema defects that left audit-planning-service
--  and risk-service non-functional:
--
--    1. audit_engagements — V017 defined an older shape with engagement_name /
--       engagement_type / period_start / period_end / description; V021 tried
--       to redefine with CREATE TABLE IF NOT EXISTS (silent no-op on existing
--       table). Sprint 23 canonicalises on the V021 shape and adds the one
--       column the remediation plan called out but neither migration had
--       (`status_notes`). V017 and V021 have also been rewritten to be
--       reconciled: V017 now defines a minimal core; V021 extends via
--       idempotent ADD COLUMN IF NOT EXISTS.
--
--    2. risks.target_score — risks table had `inherent_score` and
--       `residual_score` as GENERATED ALWAYS but no equivalent `target_score`,
--       which made the risk-service INSERT statement (Sprint 20 code review,
--       risk_manager.py:71-113) reference a column that didn't exist AND try
--       to INSERT values into the two generated columns. This migration adds
--       `target_score` as GENERATED ALWAYS for symmetry; the service code is
--       updated in the same sprint to stop inserting any of the three.
--
--  After this lands, POST /pbc/engagements, POST /audit-planning/engagements,
--  and POST /risk/risks all succeed end-to-end.
-- ============================================================================

-- ── 1. audit_engagements: missing status_notes column ──────────────────────
--
-- Called out in the remediation plan; neither V017 nor V021 defined it.

ALTER TABLE audit_engagements
    ADD COLUMN IF NOT EXISTS status_notes TEXT;

-- ── 2. risks.target_score: generated column to match inherent / residual ──
--
-- Without this, risk_manager.py either inserts a value into a non-existent
-- column (today) or inserts into a regular column that the business logic
-- has to keep in sync manually (bug-prone). Making it GENERATED matches the
-- shape of inherent_score / residual_score and eliminates the drift.

ALTER TABLE risks
    ADD COLUMN IF NOT EXISTS target_score NUMERIC(4,1)
        GENERATED ALWAYS AS (target_likelihood * target_impact) STORED;

CREATE INDEX IF NOT EXISTS idx_risks_tenant_target_score
    ON risks (tenant_id, target_score DESC);
