-- =============================================================================
-- Sprint 1 Integration Test Seed Data
-- Run by the CI/CD pipeline before integration tests.
-- Creates test tenants, users, and credentials in a transaction so CI teardown
-- can ROLLBACK cleanly (if the test runner supports it) or truncate explicitly.
-- =============================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- Seed tenants
-- ---------------------------------------------------------------------------
INSERT INTO tenants (tenant_id, external_id, display_name, tier, region)
VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', 'ci-tenant-alpha', 'CI Tenant Alpha (SMB Pool)', 'smb_pool', 'us-east-1'),
    ('bbbbbbbb-0000-0000-0000-000000000002', 'ci-tenant-beta',  'CI Tenant Beta  (SMB Pool)', 'smb_pool', 'us-east-1'),
    ('cccccccc-0000-0000-0000-000000000003', 'ci-firm-gamma',   'CI Audit Firm Gamma',        'smb_pool', 'us-east-1')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO chain_sequence_counters (tenant_id)
VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001'),
    ('bbbbbbbb-0000-0000-0000-000000000002'),
    ('cccccccc-0000-0000-0000-000000000003')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Seed users (one per tenant, various roles)
-- ---------------------------------------------------------------------------

-- Tenant A: admin + auditor + readonly
INSERT INTO users (user_id, tenant_id, email, email_verified, display_name, role, is_active)
VALUES
    ('a1000000-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'admin@alpha.test', TRUE, 'Alpha Admin', 'admin', TRUE),
    ('a1000000-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'auditor@alpha.test', TRUE, 'Alpha Auditor', 'auditor', TRUE),
    ('a1000000-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001', 'readonly@alpha.test', TRUE, 'Alpha Readonly', 'readonly', TRUE)
ON CONFLICT DO NOTHING;

-- Tenant B: admin + auditor
INSERT INTO users (user_id, tenant_id, email, email_verified, display_name, role, is_active)
VALUES
    ('b1000000-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-000000000002', 'admin@beta.test', TRUE, 'Beta Admin', 'admin', TRUE),
    ('b1000000-0000-0000-0000-000000000002', 'bbbbbbbb-0000-0000-0000-000000000002', 'auditor@beta.test', TRUE, 'Beta Auditor', 'auditor', TRUE)
ON CONFLICT DO NOTHING;

-- Firm Gamma: firm_partner
INSERT INTO users (user_id, tenant_id, email, email_verified, display_name, role, is_active)
VALUES
    ('c1000000-0000-0000-0000-000000000001', 'cccccccc-0000-0000-0000-000000000003', 'partner@gamma.test', TRUE, 'Gamma Partner', 'firm_partner', TRUE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Seed evidence records (using superuser to bypass RLS for seeding)
-- ---------------------------------------------------------------------------
SET app.tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001';

INSERT INTO evidence_records (
    evidence_id, tenant_id, source_system, collected_at_utc,
    payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version
)
VALUES (
    'e1000000-0000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'aws_cloudtrail',
    NOW() - INTERVAL '1 hour',
    decode('deadbeef', 'hex'),
    '{"event":"s3:PutObject","bucket":"alpha-secure-docs","encryption":"AES256"}'::jsonb,
    decode('cafebabe', 'hex'),
    1,
    '1.0.0'
) ON CONFLICT DO NOTHING;

SET app.tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002';

INSERT INTO evidence_records (
    evidence_id, tenant_id, source_system, collected_at_utc,
    payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version
)
VALUES (
    'e2000000-0000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'quickbooks',
    NOW() - INTERVAL '2 hours',
    decode('feedface', 'hex'),
    '{"account":"5000","vendor":"ACME Corp","amount":12500.00,"date":"2026-04-01"}'::jsonb,
    decode('badf00d0', 'hex'),
    1,
    '1.0.0'
) ON CONFLICT DO NOTHING;

-- Reset tenant context
SET app.tenant_id = '';

-- ---------------------------------------------------------------------------
-- Seed PAM chain sequence
-- ---------------------------------------------------------------------------
INSERT INTO chain_sequence_counters_pam DEFAULT VALUES ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Print seeded data summary
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE 'Seed complete: % tenants, % users, % evidence records',
        (SELECT COUNT(*) FROM tenants WHERE external_id LIKE 'ci-%'),
        (SELECT COUNT(*) FROM users WHERE email LIKE '%@%.test'),
        (SELECT COUNT(*) FROM evidence_records WHERE source_system IN ('aws_cloudtrail','quickbooks'));
END;
$$;
