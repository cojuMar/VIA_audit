-- =============================================================================
-- Project Aegis 2026 — Sprint 1
-- Migration : V003__create_auth_tables.sql
-- Purpose   : Authentication, WebAuthn (FIDO2 passkeys), and session
--             management tables.
--
-- Design notes
-- ────────────
--   • users         — principal directory; one row per identity within a tenant.
--   • webauthn_credentials — FIDO2 passkey registrations; a single user may
--                   register multiple devices (phone, laptop, hardware key).
--   • sessions      — JWT session tracking.  Every issued JWT is recorded here;
--                   revocation is checked by looking up jti.
--   • jwt_rotation_keys — RSA/EC keypairs used to sign JWTs.  Multiple active
--                   keys support zero-downtime key rotation.  No RLS because
--                   key material is platform-level, not tenant-scoped.
--   • recovery_codes — Single-use emergency access codes hashed with Argon2id.
--
-- Row-Level Security
-- ──────────────────
--   All tables except jwt_rotation_keys are RLS + FORCE RLS protected using
--   the same tenant_isolation policy pattern from V001.
--
-- Idempotency
-- ───────────
--   CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, and
--   DROP POLICY IF EXISTS / CREATE POLICY ensure safe re-runs.
--
-- Prerequisites
-- ─────────────
--   V001__create_pool_model_schema.sql (for tenants table, get_tenant_id(),
--   aegis_app role).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. USERS TABLE
--    Central identity store.  One row per user per tenant.
--    The role column controls which UI surfaces and API endpoints a user may
--    access; business-level ABAC rules are enforced in the application layer
--    on top of these coarse roles.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    user_id        UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id      UUID        NOT NULL,
    -- Email is the primary login identifier; stored in lowercase by the
    -- application before insert to guarantee case-insensitive uniqueness.
    email          TEXT        NOT NULL,
    email_verified BOOLEAN     NOT NULL DEFAULT FALSE,
    display_name   TEXT        NULL,
    -- Coarse role for the user within this tenant.
    -- admin         : full tenant administration.
    -- auditor       : read-only access plus can submit findings.
    -- firm_partner  : cross-client view for CPA firm users.
    -- smb_owner     : SMB business owner; sees only their own tenant.
    -- readonly      : view-only access to dashboards.
    role           TEXT        NOT NULL
                        CHECK (role IN ('admin', 'auditor', 'firm_partner', 'smb_owner', 'readonly')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at  TIMESTAMPTZ NULL,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT users_pkey
        PRIMARY KEY (user_id),
    CONSTRAINT users_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT,
    -- Email must be unique within a tenant; the same email may exist in
    -- different tenants (multi-tenancy scenario).
    CONSTRAINT users_tenant_email_unique
        UNIQUE (tenant_id, email)
);

COMMENT ON TABLE  public.users IS
    'Principal directory. One row per user per tenant. The role column provides '
    'coarse-grained access control; fine-grained ABAC is handled in the application. '
    'RLS enforces tenant isolation — a user can only see/modify rows within their tenant.';
COMMENT ON COLUMN public.users.email IS
    'Lowercase email address (normalised by the application before insert). '
    'Unique within a tenant via the users_tenant_email_unique constraint.';
COMMENT ON COLUMN public.users.role IS
    'Coarse access role. Values: admin | auditor | firm_partner | smb_owner | readonly.';
COMMENT ON COLUMN public.users.last_login_at IS
    'Timestamp of the most recent successful authentication. Updated by the '
    'auth service on every successful login.';

-- RLS on users.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.users;
CREATE POLICY tenant_isolation
    ON public.users
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- Trigger: stamp updated_at on every UPDATE.
DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

-- ---------------------------------------------------------------------------
-- 2. WEBAUTHN CREDENTIALS TABLE
--    Stores FIDO2 passkey registrations (authenticator data) per user.
--    A single user may register multiple authenticators (e.g. Touch ID on
--    laptop, Face ID on iPhone, YubiKey).
--    The sign_count is updated on every successful assertion to detect
--    authenticator cloning (sign_count regression is a security signal).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.webauthn_credentials (
    -- credential_id is the raw credential ID bytes returned by the
    -- authenticator, base64url-encoded.  It is the authenticator''s primary
    -- key for this registration.
    credential_id  TEXT        NOT NULL,
    user_id        UUID        NOT NULL,
    tenant_id      UUID        NOT NULL,
    -- DER-encoded COSE public key (EC P-256 or RSA-2048 typically).
    public_key     BYTEA       NOT NULL,
    -- Monotonically increasing counter maintained by the authenticator.
    -- The server checks that sign_count > last stored value on each assertion.
    -- A value of 0 means the authenticator does not implement the counter
    -- (some platform authenticators, e.g. iOS).
    sign_count     BIGINT      NOT NULL DEFAULT 0,
    -- AAGUID identifies the authenticator model (e.g. YubiKey 5 NFC).
    -- NULL for authenticators that do not attest.
    aaguid         TEXT        NULL,
    -- Transport hints: array of strings such as ['usb','nfc','ble','internal'].
    transport      TEXT[]      NULL,
    -- Whether the credential is backed up to the platform cloud keychain
    -- (e.g. iCloud Keychain, Google Password Manager).
    backed_up      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at   TIMESTAMPTZ NULL,
    -- Human-readable label the user assigned to this device.
    device_name    TEXT        NULL,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT webauthn_credentials_pkey
        PRIMARY KEY (credential_id),
    CONSTRAINT webauthn_credentials_user_fk
        FOREIGN KEY (user_id) REFERENCES public.users (user_id)
        ON DELETE CASCADE,   -- passkeys are revoked when the user is deleted
    CONSTRAINT webauthn_credentials_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE  public.webauthn_credentials IS
    'FIDO2/WebAuthn passkey registrations. One row per registered authenticator '
    'per user. sign_count is updated on each successful assertion; a regression '
    'indicates a possible cloned authenticator and should trigger a security alert. '
    'RLS ensures tenant isolation.';
COMMENT ON COLUMN public.webauthn_credentials.sign_count IS
    'Authenticator signature counter. Must increase on every assertion. '
    'A value of 0 after the first assertion is normal for platform authenticators '
    'that do not implement the counter (check the AAGUID metadata).';
COMMENT ON COLUMN public.webauthn_credentials.backed_up IS
    'TRUE if the credential is synced to the platform cloud keychain. '
    'Synced credentials are not hardware-bound; factor this into the risk model.';

-- RLS on webauthn_credentials.
ALTER TABLE public.webauthn_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webauthn_credentials FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.webauthn_credentials;
CREATE POLICY tenant_isolation
    ON public.webauthn_credentials
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 3. SESSIONS TABLE
--    Tracks every issued JWT.  On each API request the application looks up
--    the jti (JWT ID claim) to verify the session has not been revoked and
--    has not expired.  This enables server-side session revocation without
--    waiting for token expiry — critical for break-glass and incident response.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sessions (
    session_id           UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id              UUID        NOT NULL,
    tenant_id            UUID        NOT NULL,
    -- jti: JWT ID claim — globally unique per token, used as the lookup key
    -- on every API request.  TEXT rather than UUID to accommodate JWTs whose
    -- jti is a non-UUID opaque string.
    jti                  TEXT        NOT NULL,
    issued_at            TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ NOT NULL,
    -- revoked_at is NULL while the session is live; set by the revocation
    -- endpoint (logout, admin revoke, break-glass expiry).
    revoked_at           TIMESTAMPTZ NULL,
    -- Client metadata for anomaly detection and audit.
    ip_address           INET        NULL,
    user_agent           TEXT        NULL,
    -- FIDO2 assertion ID from the login ceremony that produced this session.
    -- Links the session to the specific authenticator assertion in WebAuthn logs.
    fido2_assertion_id   TEXT        NULL,

    CONSTRAINT sessions_pkey
        PRIMARY KEY (session_id),
    CONSTRAINT sessions_user_fk
        FOREIGN KEY (user_id) REFERENCES public.users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT sessions_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT,
    -- jti uniqueness is global across all tenants to prevent token reuse attacks.
    CONSTRAINT sessions_jti_unique
        UNIQUE (jti)
);

COMMENT ON TABLE  public.sessions IS
    'JWT session registry. Every issued access token is recorded here. '
    'The auth middleware checks jti on every request to support server-side '
    'revocation (logout, admin revoke, break-glass expiry). '
    'RLS enforces tenant isolation.';
COMMENT ON COLUMN public.sessions.jti IS
    'JWT ID claim. Globally unique. Used as the primary lookup key by the '
    'token validation middleware on each API request.';
COMMENT ON COLUMN public.sessions.revoked_at IS
    'NULL while the session is live. Set to NOW() by the revocation endpoint. '
    'The middleware must check: revoked_at IS NULL AND expires_at > NOW().';
COMMENT ON COLUMN public.sessions.fido2_assertion_id IS
    'Links this session to the FIDO2 assertion that authenticated it. '
    'Used by the PAM broker to verify MFA was completed for break-glass access.';

-- RLS on sessions.
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.sessions;
CREATE POLICY tenant_isolation
    ON public.sessions
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 4. JWT ROTATION KEYS TABLE (platform-level — NO RLS)
--    Stores the asymmetric keypairs used to sign JWTs.  Multiple rows may be
--    active simultaneously to support zero-downtime rotation:
--      • New key is created and added (is_active = TRUE, retired_at = NULL).
--      • A rotation window allows old tokens signed with the previous key to
--        remain valid until they expire.
--      • After the rotation window, the old key''s is_active is set to FALSE
--        and retired_at is stamped.
--    The private_key_encrypted column stores the private key encrypted with
--    the KMS-managed envelope key.  The plaintext private key is NEVER stored
--    in the database.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.jwt_rotation_keys (
    -- Human-readable / KMS key alias, e.g. 'aegis-jwt-2026-04-01'.
    key_id                TEXT        NOT NULL,
    -- PEM-encoded public key for token verification by third-party services.
    public_key_pem        TEXT        NOT NULL,
    -- KMS-envelope-encrypted private key bytes.  Decryption requires a live
    -- call to the KMS (AWS KMS, HashiCorp Vault, etc.).
    private_key_encrypted BYTEA       NOT NULL,
    -- Signing algorithm: 'RS256' (RSA-PKCS1-v1.5), 'RS384', 'ES256' (ECDSA P-256).
    algorithm             TEXT        NOT NULL DEFAULT 'RS256',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Set when this key is taken out of active signing rotation.
    retired_at            TIMESTAMPTZ NULL,
    -- Verification flag: FALSE keys are still usable for validating existing
    -- tokens during the rotation window, but the signing service will not issue
    -- new tokens with a retired key.
    is_active             BOOLEAN     NOT NULL DEFAULT TRUE,

    CONSTRAINT jwt_rotation_keys_pkey
        PRIMARY KEY (key_id)
);

COMMENT ON TABLE  public.jwt_rotation_keys IS
    'RSA / EC keypairs for JWT signing and verification. Platform-level table — '
    'no RLS. The private_key_encrypted column stores KMS-envelope-encrypted key '
    'material; the plaintext key is never persisted. Multiple active keys support '
    'zero-downtime rotation.';
COMMENT ON COLUMN public.jwt_rotation_keys.private_key_encrypted IS
    'KMS-envelope-encrypted private key. Decrypt only via the KMS API at signing '
    'time. Never log, print, or store the decrypted value.';
COMMENT ON COLUMN public.jwt_rotation_keys.is_active IS
    'FALSE = key has been rotated out. Still usable for verifying tokens issued '
    'before retirement until those tokens expire.';

-- No RLS on jwt_rotation_keys — access is controlled by role grants only.
-- Only the auth service role (not aegis_app) should be granted SELECT on this table.

-- ---------------------------------------------------------------------------
-- 5. RECOVERY CODES TABLE
--    Single-use emergency access codes for account recovery when all FIDO2
--    authenticators are lost.  Codes are hashed with Argon2id before storage;
--    the plaintext is shown to the user exactly once at generation time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recovery_codes (
    code_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL,
    tenant_id  UUID        NOT NULL,
    -- Argon2id hash of the plaintext recovery code.  The salt is embedded in
    -- the Argon2id hash string (PHC format).  Never store plaintext.
    code_hash  TEXT        NOT NULL,
    -- Set when this code was consumed; NULL = still valid.
    used_at    TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Recovery codes must be regenerated periodically; expires_at is typically
    -- set to NOW() + INTERVAL ''1 year'' at generation time.
    expires_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT recovery_codes_pkey
        PRIMARY KEY (code_id),
    CONSTRAINT recovery_codes_user_fk
        FOREIGN KEY (user_id) REFERENCES public.users (user_id)
        ON DELETE CASCADE,
    CONSTRAINT recovery_codes_tenant_fk
        FOREIGN KEY (tenant_id) REFERENCES public.tenants (tenant_id)
        ON DELETE RESTRICT
);

COMMENT ON TABLE  public.recovery_codes IS
    'Single-use emergency access codes for FIDO2 authenticator loss recovery. '
    'code_hash stores the Argon2id PHC-format hash; the plaintext is shown to '
    'the user once and is never stored. used_at is stamped on consumption. '
    'RLS enforces tenant isolation.';
COMMENT ON COLUMN public.recovery_codes.code_hash IS
    'Argon2id PHC-format hash string (includes salt). NEVER store or log '
    'the plaintext recovery code. Verify with a constant-time Argon2id '
    'compare in the application.';

-- RLS on recovery_codes.
ALTER TABLE public.recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recovery_codes FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.recovery_codes;
CREATE POLICY tenant_isolation
    ON public.recovery_codes
    AS PERMISSIVE
    FOR ALL
    TO PUBLIC
    USING      (tenant_id = public.get_tenant_id())
    WITH CHECK (tenant_id = public.get_tenant_id());

-- ---------------------------------------------------------------------------
-- 6. INDEXES
-- ---------------------------------------------------------------------------

-- users: look up by email during login (case-insensitive in application,
-- stored lowercase in DB).
CREATE INDEX IF NOT EXISTS idx_users_email
    ON public.users (email);

COMMENT ON INDEX public.idx_users_email IS
    'Supports login lookups by email. Application normalises to lowercase before querying.';

-- users: list users within a tenant filtered by role (e.g. show all admins).
CREATE INDEX IF NOT EXISTS idx_users_tenant_role
    ON public.users (tenant_id, role);

COMMENT ON INDEX public.idx_users_tenant_role IS
    'Supports per-tenant role-based user listing for admin dashboards.';

-- webauthn_credentials: look up all registered authenticators for a user
-- during the assertion ceremony.
CREATE INDEX IF NOT EXISTS idx_webauthn_user_id
    ON public.webauthn_credentials (user_id);

COMMENT ON INDEX public.idx_webauthn_user_id IS
    'Used by the WebAuthn assertion flow to retrieve all credentials for a '
    'given user_id during passkey authentication.';

-- sessions: primary lookup path — token validation middleware queries by jti.
-- The UNIQUE constraint already creates a B-tree index, but naming it
-- explicitly for clarity and monitoring.
CREATE INDEX IF NOT EXISTS idx_sessions_jti
    ON public.sessions (jti);

COMMENT ON INDEX public.idx_sessions_jti IS
    'Primary session lookup by JWT ID claim. Hit on every authenticated API request.';

-- sessions: list active sessions for a user (e.g. "logout all other devices").
CREATE INDEX IF NOT EXISTS idx_sessions_user_expires
    ON public.sessions (user_id, expires_at DESC);

COMMENT ON INDEX public.idx_sessions_user_expires IS
    'Supports listing and revoking active sessions for a specific user.';

-- ---------------------------------------------------------------------------
-- 7. GRANTS TO aegis_app
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON public.users                  TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.webauthn_credentials   TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.sessions               TO aegis_app;
GRANT SELECT, INSERT, UPDATE ON public.recovery_codes         TO aegis_app;
-- jwt_rotation_keys is intentionally withheld from aegis_app.
-- Only the dedicated auth-service DB role should access key material.
-- Grant that separately when provisioning the auth-service role:
--   GRANT SELECT ON public.jwt_rotation_keys TO aegis_auth_service;

-- ---------------------------------------------------------------------------
-- END OF MIGRATION V003
-- ---------------------------------------------------------------------------
