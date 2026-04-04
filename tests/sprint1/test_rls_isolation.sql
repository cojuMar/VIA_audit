-- =============================================================================
-- Sprint 1 Cross-Tenant RLS Isolation Tests
-- Run via: psql $DATABASE_URL -f tests/sprint1/test_rls_isolation.sql
-- ALL tests must pass (zero failures) before deployment.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------
-- Test harness: lightweight pass/fail counter
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE test_results (
    test_name   TEXT NOT NULL,
    passed      BOOLEAN NOT NULL,
    detail      TEXT
);

CREATE OR REPLACE FUNCTION assert_true(p_name TEXT, p_condition BOOLEAN, p_detail TEXT DEFAULT NULL)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO test_results VALUES (p_name, p_condition, p_detail);
    IF NOT p_condition THEN
        RAISE WARNING 'FAIL: % — %', p_name, COALESCE(p_detail, '(no detail)');
    ELSE
        RAISE NOTICE 'PASS: %', p_name;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION assert_equals(p_name TEXT, p_expected ANYELEMENT, p_actual ANYELEMENT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    PERFORM assert_true(
        p_name,
        p_expected IS NOT DISTINCT FROM p_actual,
        format('expected %s, got %s', p_expected::text, p_actual::text)
    );
END;
$$;

CREATE OR REPLACE FUNCTION assert_zero_rows(p_name TEXT, p_count BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    PERFORM assert_true(p_name, p_count = 0, format('expected 0 rows, got %s', p_count));
END;
$$;

-- ---------------------------------------------------------------------------
-- Fixture setup: two tenants, seed data in each
-- ---------------------------------------------------------------------------
INSERT INTO tenants (tenant_id, external_id, display_name, tier, region)
VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', 'test-tenant-a', 'Tenant Alpha (Pool)', 'smb_pool', 'us-east-1'),
    ('bbbbbbbb-0000-0000-0000-000000000002', 'test-tenant-b', 'Tenant Beta  (Pool)', 'smb_pool', 'us-east-1')
ON CONFLICT DO NOTHING;

INSERT INTO chain_sequence_counters (tenant_id) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001'),
    ('bbbbbbbb-0000-0000-0000-000000000002')
ON CONFLICT DO NOTHING;

-- Seed evidence records directly as superuser (bypasses RLS for fixture setup)
-- We must SET ROLE to a non-owner to activate RLS below.
SET app.tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001';
INSERT INTO evidence_records (tenant_id, source_system, collected_at_utc, payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version)
VALUES (
    'aaaaaaaa-0000-0000-0000-000000000001',
    'aws_cloudtrail',
    NOW(),
    '\xdeadbeef'::bytea,
    '{"action":"s3:GetObject","bucket":"alpha-bucket"}'::jsonb,
    '\xcafebabe'::bytea,
    1,
    '1.0.0'
);

SET app.tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002';
INSERT INTO evidence_records (tenant_id, source_system, collected_at_utc, payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version)
VALUES (
    'bbbbbbbb-0000-0000-0000-000000000002',
    'quickbooks',
    NOW(),
    '\xfeedface'::bytea,
    '{"account":"5000","amount":99999.00}'::jsonb,
    '\xbadf00d0'::bytea,
    1,
    '1.0.0'
);

-- Reset to empty to verify fail-closed behavior
SET app.tenant_id = '';

-- ---------------------------------------------------------------------------
-- TEST BLOCK 1: RLS fail-closed with empty tenant_id
-- Critical: no rows must be returned when app.tenant_id is '' or null
-- ---------------------------------------------------------------------------

PERFORM assert_zero_rows(
    'CRITICAL: empty tenant_id returns zero rows from evidence_records',
    (SELECT COUNT(*) FROM evidence_records)
);

PERFORM assert_zero_rows(
    'CRITICAL: empty tenant_id returns zero rows from risk_scores',
    (SELECT COUNT(*) FROM risk_scores)
);

-- ---------------------------------------------------------------------------
-- TEST BLOCK 2: Tenant A can only see its own evidence
-- ---------------------------------------------------------------------------

SET app.tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001';

PERFORM assert_equals(
    'CRITICAL: tenant A sees exactly 1 evidence record (its own)',
    1::bigint,
    (SELECT COUNT(*) FROM evidence_records)
);

PERFORM assert_equals(
    'CRITICAL: tenant A evidence source_system = aws_cloudtrail',
    'aws_cloudtrail',
    (SELECT source_system FROM evidence_records LIMIT 1)
);

-- Attempt to read tenant B data by specifying its tenant_id directly in the WHERE clause.
-- RLS should prevent this — the row is invisible even with an explicit filter.
PERFORM assert_zero_rows(
    'CRITICAL: tenant A cannot read tenant B evidence via explicit tenant_id filter',
    (SELECT COUNT(*) FROM evidence_records
     WHERE tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002')
);

-- ---------------------------------------------------------------------------
-- TEST BLOCK 3: Tenant B can only see its own evidence
-- ---------------------------------------------------------------------------

SET app.tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002';

PERFORM assert_equals(
    'CRITICAL: tenant B sees exactly 1 evidence record (its own)',
    1::bigint,
    (SELECT COUNT(*) FROM evidence_records)
);

PERFORM assert_equals(
    'CRITICAL: tenant B evidence source_system = quickbooks',
    'quickbooks',
    (SELECT source_system FROM evidence_records LIMIT 1)
);

-- Attempt to read tenant A data
PERFORM assert_zero_rows(
    'CRITICAL: tenant B cannot read tenant A evidence via explicit tenant_id filter',
    (SELECT COUNT(*) FROM evidence_records
     WHERE tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001')
);

-- ---------------------------------------------------------------------------
-- TEST BLOCK 4: WITH CHECK enforcement — tenant cannot INSERT for another tenant
-- ---------------------------------------------------------------------------

SET app.tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001';

DO $$
DECLARE
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        -- Attempt to INSERT a row for tenant B while authenticated as tenant A
        INSERT INTO evidence_records (tenant_id, source_system, collected_at_utc, payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version)
        VALUES (
            'bbbbbbbb-0000-0000-0000-000000000002',  -- WRONG tenant_id
            'injected',
            NOW(),
            '\x00000000'::bytea,
            '{}'::jsonb,
            '\x11111111'::bytea,
            999,
            '1.0.0'
        );
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    INSERT INTO test_results VALUES (
        'CRITICAL: RLS WITH CHECK blocks cross-tenant INSERT',
        v_raised,
        CASE WHEN v_raised THEN NULL ELSE 'INSERT succeeded — RLS WITH CHECK FAILED' END
    );
    IF v_raised THEN
        RAISE NOTICE 'PASS: CRITICAL: RLS WITH CHECK blocks cross-tenant INSERT';
    ELSE
        RAISE WARNING 'FAIL: CRITICAL: RLS WITH CHECK blocks cross-tenant INSERT — RLS WITH CHECK FAILED';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- TEST BLOCK 5: chain_sequence monotonicity enforcement
-- ---------------------------------------------------------------------------

SET app.tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001';

DO $$
DECLARE
    v_raised BOOLEAN := FALSE;
BEGIN
    BEGIN
        -- Attempt to INSERT with wrong chain_sequence (should be 2 but we use 999)
        INSERT INTO evidence_records (tenant_id, source_system, collected_at_utc, payload_hash, canonical_payload, chain_hash, chain_sequence, collector_version)
        VALUES (
            'aaaaaaaa-0000-0000-0000-000000000001',
            'test',
            NOW(),
            '\x12345678'::bytea,
            '{}'::jsonb,
            '\xabcdef00'::bytea,
            999,  -- Wrong sequence
            '1.0.0'
        );
    EXCEPTION WHEN OTHERS THEN
        v_raised := TRUE;
    END;
    INSERT INTO test_results VALUES (
        'HIGH: chain_sequence trigger rejects out-of-order sequence',
        v_raised,
        CASE WHEN v_raised THEN NULL ELSE 'INSERT with wrong sequence succeeded' END
    );
    IF v_raised THEN
        RAISE NOTICE 'PASS: HIGH: chain_sequence trigger rejects out-of-order sequence';
    ELSE
        RAISE WARNING 'FAIL: HIGH: chain_sequence trigger rejects out-of-order sequence';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- TEST BLOCK 6: PAM audit log is immutable (UPDATE/DELETE raise exception)
-- ---------------------------------------------------------------------------

-- Insert a seed PAM log entry as superuser
SET app.tenant_id = '';
INSERT INTO chain_sequence_counters_pam DEFAULT VALUES ON CONFLICT DO NOTHING;

INSERT INTO pam_audit_log (request_id, actor_user_id, actor_role, action, logged_at, chain_hash, chain_sequence)
VALUES (
    gen_random_uuid(),
    'aaaaaaaa-0000-0000-0000-000000000099',
    'admin',
    'access_request_approved',
    NOW(),
    '\xdeadbeef'::bytea,
    1
) ON CONFLICT DO NOTHING;

DO $$
DECLARE
    v_update_raised BOOLEAN := FALSE;
    v_delete_raised BOOLEAN := FALSE;
    v_log_id UUID;
BEGIN
    SELECT log_id INTO v_log_id FROM pam_audit_log LIMIT 1;

    -- Attempt UPDATE
    BEGIN
        UPDATE pam_audit_log SET action = 'tampered' WHERE log_id = v_log_id;
    EXCEPTION WHEN OTHERS THEN
        v_update_raised := TRUE;
    END;

    -- Attempt DELETE
    BEGIN
        DELETE FROM pam_audit_log WHERE log_id = v_log_id;
    EXCEPTION WHEN OTHERS THEN
        v_delete_raised := TRUE;
    END;

    INSERT INTO test_results VALUES (
        'CRITICAL: pam_audit_log UPDATE is blocked by immutability trigger',
        v_update_raised, NULL
    );
    INSERT INTO test_results VALUES (
        'CRITICAL: pam_audit_log DELETE is blocked by immutability trigger',
        v_delete_raised, NULL
    );

    IF v_update_raised THEN RAISE NOTICE 'PASS: CRITICAL: pam_audit_log UPDATE is blocked';
    ELSE RAISE WARNING 'FAIL: CRITICAL: pam_audit_log UPDATE is blocked'; END IF;

    IF v_delete_raised THEN RAISE NOTICE 'PASS: CRITICAL: pam_audit_log DELETE is blocked';
    ELSE RAISE WARNING 'FAIL: CRITICAL: pam_audit_log DELETE is blocked'; END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- TEST BLOCK 7: FORCE ROW LEVEL SECURITY — table owner cannot bypass RLS
-- ---------------------------------------------------------------------------
-- This verifies FORCE RLS is set. We check pg_class.relforcerowsecurity.

PERFORM assert_true(
    'CRITICAL: evidence_records has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'evidence_records'),
    'relforcerowsecurity is FALSE — table owner can bypass RLS'
);

PERFORM assert_true(
    'CRITICAL: risk_scores has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'risk_scores'),
    'relforcerowsecurity is FALSE'
);

PERFORM assert_true(
    'CRITICAL: evidence_chunks has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'evidence_chunks'),
    'relforcerowsecurity is FALSE'
);

PERFORM assert_true(
    'CRITICAL: users has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'users'),
    'relforcerowsecurity is FALSE'
);

PERFORM assert_true(
    'CRITICAL: webauthn_credentials has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'webauthn_credentials'),
    'relforcerowsecurity is FALSE'
);

PERFORM assert_true(
    'CRITICAL: sessions has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'sessions'),
    'relforcerowsecurity is FALSE'
);

PERFORM assert_true(
    'CRITICAL: hitl_queue has FORCE ROW LEVEL SECURITY enabled',
    (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'hitl_queue'),
    'relforcerowsecurity is FALSE'
);

-- ---------------------------------------------------------------------------
-- TEST BLOCK 8: RLS policies exist on all tenant-scoped tables
-- ---------------------------------------------------------------------------

PERFORM assert_true(
    'CRITICAL: RLS policy exists on evidence_records',
    EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'evidence_records' AND policyname = 'tenant_isolation'),
    'No tenant_isolation policy found on evidence_records'
);

PERFORM assert_true(
    'CRITICAL: RLS policy exists on risk_scores',
    EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'risk_scores' AND policyname = 'tenant_isolation'),
    'No tenant_isolation policy found on risk_scores'
);

PERFORM assert_true(
    'CRITICAL: RLS policy exists on users',
    EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'tenant_isolation'),
    'No tenant_isolation policy found on users'
);

-- ---------------------------------------------------------------------------
-- TEST BLOCK 9: JWT signing key table exists and is accessible
-- ---------------------------------------------------------------------------

PERFORM assert_true(
    'HIGH: jwt_rotation_keys table exists',
    EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'jwt_rotation_keys'),
    'jwt_rotation_keys table not found'
);

-- jwt_rotation_keys must NOT have RLS (platform-level table)
PERFORM assert_true(
    'HIGH: jwt_rotation_keys does NOT have RLS enabled (platform-level table)',
    NOT (SELECT relrowsecurity FROM pg_class WHERE relname = 'jwt_rotation_keys'),
    'jwt_rotation_keys unexpectedly has RLS enabled'
);

-- ---------------------------------------------------------------------------
-- Final: print summary
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    v_total    INT;
    v_passed   INT;
    v_failed   INT;
    v_rec      RECORD;
BEGIN
    SELECT COUNT(*), COUNT(*) FILTER (WHERE passed), COUNT(*) FILTER (WHERE NOT passed)
    INTO v_total, v_passed, v_failed
    FROM test_results;

    RAISE NOTICE '';
    RAISE NOTICE '======================================================';
    RAISE NOTICE 'Sprint 1 RLS Isolation Test Results';
    RAISE NOTICE '======================================================';
    RAISE NOTICE 'Total:  %', v_total;
    RAISE NOTICE 'Passed: %', v_passed;
    RAISE NOTICE 'Failed: %', v_failed;
    RAISE NOTICE '======================================================';

    IF v_failed > 0 THEN
        RAISE NOTICE 'FAILURES:';
        FOR v_rec IN SELECT test_name, detail FROM test_results WHERE NOT passed LOOP
            RAISE NOTICE '  FAIL: % — %', v_rec.test_name, COALESCE(v_rec.detail, '');
        END LOOP;
    END IF;

    IF v_failed > 0 THEN
        RAISE EXCEPTION 'Sprint 1 RLS tests FAILED: % of % tests failed', v_failed, v_total;
    END IF;
END;
$$;

ROLLBACK; -- Never commit test fixtures to the production DB
