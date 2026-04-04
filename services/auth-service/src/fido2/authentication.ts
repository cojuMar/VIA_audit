/**
 * WebAuthn / FIDO2 authentication (assertion) flow.
 *
 * Two-step process:
 *   1. `generateAuthenticationOptions` — produce a challenge, store in Redis,
 *      return options to the client.
 *   2. `verifyAuthentication` — verify the client's signed assertion, update
 *      the sign counter, and return the verified user.
 *
 * Security notes:
 *  - `userVerification: 'required'` ensures biometric/PIN is always performed.
 *  - The sign counter is checked to detect cloned authenticators.
 *  - Challenges are single-use and expire after 5 minutes.
 */

import {
  generateAuthenticationOptions as _generateAuthenticationOptions,
  verifyAuthenticationResponse,
  type AuthenticationResponseJSON,
  type AuthenticatorTransportFuture,
} from '@simplewebauthn/server';
import { isoBase64URL } from '@simplewebauthn/server/helpers';
import { queryNoTenant } from '../db.js';
import { getRedis } from '../redis.js';
import type { User } from '../types.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Challenge TTL in seconds — 5 minutes */
const CHALLENGE_TTL_SECONDS = 300;

function authChallengeKey(userId: string): string {
  return `webauthn_auth_challenge:${userId}`;
}

// ---------------------------------------------------------------------------
// DB row types
// ---------------------------------------------------------------------------

interface CredentialRow {
  credential_id: string;
  user_id: string;
  tenant_id: string;
  public_key: Buffer;
  sign_count: number;
  transports: string | null;
  device_name: string | null;
}

interface UserRow {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Step 1: Generate options
// ---------------------------------------------------------------------------

/**
 * Loads the user's registered credentials from the DB, generates an
 * authentication challenge, and stores it in Redis.
 *
 * @returns The authentication options to send to the client.
 */
export async function generateAuthenticationOptions(
  userId: string,
  _tenantId: string
): Promise<Awaited<ReturnType<typeof _generateAuthenticationOptions>>> {
  // Load all credentials for this user
  const credResult = await queryNoTenant<CredentialRow>(
    `SELECT credential_id, user_id, tenant_id, public_key, sign_count, transports, device_name
       FROM webauthn_credentials
      WHERE user_id = $1`,
    [userId]
  );

  const allowCredentials = credResult.rows.map((row) => ({
    id: isoBase64URL.fromBuffer(Buffer.from(row.credential_id, 'base64url')),
    type: 'public-key' as const,
    transports: row.transports
      ? (JSON.parse(row.transports) as AuthenticatorTransportFuture[])
      : undefined,
  }));

  const options = await _generateAuthenticationOptions({
    rpID: (await import('../config.js')).config.webauthn.rpId,
    userVerification: 'required',
    allowCredentials,
    timeout: CHALLENGE_TTL_SECONDS * 1000,
  });

  // Store the challenge in Redis — single use, expires in 5 minutes
  const redis = getRedis();
  await redis.set(
    authChallengeKey(userId),
    options.challenge,
    'EX',
    CHALLENGE_TTL_SECONDS
  );

  return options;
}

// ---------------------------------------------------------------------------
// Step 2: Verify authentication
// ---------------------------------------------------------------------------

export interface AuthenticationResult {
  user: User;
  /** True if the authenticator performed user verification (biometric/PIN) */
  userVerified: boolean;
}

/**
 * Verifies the client's authentication assertion response.
 *
 * On success:
 *  - Updates `sign_count` and `last_used_at` in the DB.
 *  - Deletes the challenge from Redis.
 *  - Returns the authenticated User and UV flag.
 *
 * Throws if:
 *  - Challenge is missing or expired.
 *  - Credential not found for this user.
 *  - Signature verification fails.
 *  - Sign counter indicates a cloned authenticator.
 */
export async function verifyAuthentication(
  userId: string,
  tenantId: string,
  response: AuthenticationResponseJSON
): Promise<AuthenticationResult> {
  const { config } = await import('../config.js');

  // ------------------------------------------------------------------
  // Retrieve the stored challenge
  // ------------------------------------------------------------------
  const redis = getRedis();
  const storedChallenge = await redis.get(authChallengeKey(userId));
  if (storedChallenge === null) {
    throw new Error(
      'WebAuthn authentication challenge not found or expired. Please start authentication again.'
    );
  }

  // ------------------------------------------------------------------
  // Load the specific credential being asserted
  // ------------------------------------------------------------------
  // response.id is the base64url-encoded credential ID
  const credResult = await queryNoTenant<CredentialRow>(
    `SELECT credential_id, user_id, tenant_id, public_key, sign_count, transports, device_name
       FROM webauthn_credentials
      WHERE credential_id = $1
        AND user_id = $2`,
    [response.id, userId]
  );

  if (credResult.rows.length === 0) {
    throw new Error(
      `Credential "${response.id}" not found for user "${userId}"`
    );
  }

  const credRow = credResult.rows[0];
  if (!credRow) throw new Error('Unexpected empty credential row');

  const transports = credRow.transports
    ? (JSON.parse(credRow.transports) as AuthenticatorTransportFuture[])
    : undefined;

  // ------------------------------------------------------------------
  // Verify the response
  // ------------------------------------------------------------------
  const verification = await verifyAuthenticationResponse({
    response,
    expectedChallenge: storedChallenge,
    expectedOrigin: config.webauthn.origin,
    expectedRPID: config.webauthn.rpId,
    requireUserVerification: true,
    credential: {
      id: credRow.credential_id,
      publicKey: new Uint8Array(credRow.public_key),
      counter: credRow.sign_count,
      transports,
    },
  });

  if (!verification.verified) {
    throw new Error('WebAuthn authentication verification failed');
  }

  const { authenticationInfo } = verification;

  // ------------------------------------------------------------------
  // Detect cloned authenticators via sign counter
  // ------------------------------------------------------------------
  if (
    authenticationInfo.newCounter > 0 &&
    authenticationInfo.newCounter <= credRow.sign_count
  ) {
    process.stderr.write(
      `[webauthn] SECURITY ALERT: sign counter regression for credential ` +
        `${credRow.credential_id} (user ${userId}). Possible cloned authenticator. ` +
        `stored=${credRow.sign_count}, received=${authenticationInfo.newCounter}\n`
    );
    throw new Error(
      'Authenticator sign counter regression detected — possible cloned device'
    );
  }

  // ------------------------------------------------------------------
  // Update sign_count and last_used_at
  // ------------------------------------------------------------------
  await queryNoTenant(
    `UPDATE webauthn_credentials
        SET sign_count = $1,
            last_used_at = NOW()
      WHERE credential_id = $2
        AND user_id = $3`,
    [authenticationInfo.newCounter, credRow.credential_id, userId]
  );

  // ------------------------------------------------------------------
  // Delete the challenge (single use)
  // ------------------------------------------------------------------
  await redis.del(authChallengeKey(userId));

  // ------------------------------------------------------------------
  // Load and return the full user record
  // ------------------------------------------------------------------
  const userResult = await queryNoTenant<UserRow>(
    `SELECT user_id, tenant_id, email, display_name, role, is_active
       FROM users
      WHERE user_id = $1
        AND tenant_id = $2
        AND is_active = true`,
    [userId, tenantId]
  );

  if (userResult.rows.length === 0) {
    throw new Error(`User "${userId}" not found or inactive`);
  }

  const userRow = userResult.rows[0];
  if (!userRow) throw new Error('Unexpected empty user row');

  const user: User = {
    userId: userRow.user_id,
    tenantId: userRow.tenant_id,
    email: userRow.email,
    displayName: userRow.display_name,
    role: userRow.role as User['role'],
    isActive: userRow.is_active,
  };

  return {
    user,
    userVerified: authenticationInfo.userVerified,
  };
}
