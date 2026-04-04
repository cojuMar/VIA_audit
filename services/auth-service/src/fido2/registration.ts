/**
 * WebAuthn / FIDO2 registration (attestation) flow.
 *
 * Two-step process:
 *   1. `generateRegistrationOptions` — produce a challenge, store it in Redis,
 *      return options to the client.
 *   2. `verifyAndSaveRegistration` — verify the client's signed response,
 *      persist the credential to the DB.
 *
 * Security notes:
 *  - Challenges are single-use and expire after 5 minutes (Redis TTL).
 *  - `attestationType: 'none'` is used for broad device compatibility.
 *    Enterprise deployments can switch to 'direct' or 'enterprise' to
 *    enforce FIDO MDS attestation.
 *  - We exclude existing credentials to prevent re-registering the same
 *    authenticator (prevents credential ID collision).
 */

import {
  generateRegistrationOptions as _generateRegistrationOptions,
  verifyRegistrationResponse,
  type GenerateRegistrationOptionsOpts,
  type RegistrationResponseJSON,
  type AuthenticatorTransportFuture,
} from '@simplewebauthn/server';
import { isoBase64URL } from '@simplewebauthn/server/helpers';
import { v4 as uuidv4 } from 'uuid';
import { config } from '../config.js';
import { queryNoTenant } from '../db.js';
import { getRedis } from '../redis.js';
import type { User, WebAuthnCredential } from '../types.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Challenge TTL in seconds — 5 minutes */
const CHALLENGE_TTL_SECONDS = 300;

function challengeKey(userId: string): string {
  return `webauthn_challenge:${userId}`;
}

// ---------------------------------------------------------------------------
// Step 1: Generate options
// ---------------------------------------------------------------------------

/**
 * Generates WebAuthn registration options for `user` and stores the
 * challenge in Redis so it can be verified in step 2.
 *
 * @param user               The user initiating registration.
 * @param existingCredentials Currently registered credentials for this user
 *                            (used to build the excludeCredentials list).
 */
export async function generateRegistrationOptions(
  user: User,
  existingCredentials: WebAuthnCredential[]
): Promise<Awaited<ReturnType<typeof _generateRegistrationOptions>>> {
  const opts: GenerateRegistrationOptionsOpts = {
    rpName: config.webauthn.rpName,
    rpID: config.webauthn.rpId,
    // W3C spec: userID must be a BufferSource — use the raw UUID bytes.
    userID: Buffer.from(user.userId),
    userName: user.email,
    userDisplayName: user.displayName,
    attestationType: 'none', // broad device compatibility
    authenticatorSelection: {
      authenticatorAttachment: 'platform',
      residentKey: 'preferred',
      userVerification: 'required',
    },
    excludeCredentials: existingCredentials.map((cred) => ({
      id: isoBase64URL.fromBuffer(Buffer.from(cred.credentialId, 'base64url')),
      type: 'public-key' as const,
      transports: cred.transports as AuthenticatorTransportFuture[] | undefined,
    })),
    timeout: CHALLENGE_TTL_SECONDS * 1000,
  };

  const options = await _generateRegistrationOptions(opts);

  // Store the challenge in Redis — single use, expires in 5 minutes
  const redis = getRedis();
  await redis.set(
    challengeKey(user.userId),
    options.challenge,
    'EX',
    CHALLENGE_TTL_SECONDS
  );

  return options;
}

// ---------------------------------------------------------------------------
// Step 2: Verify and persist
// ---------------------------------------------------------------------------

export interface RegistrationResult {
  credentialId: string;
  aaguid: string;
}

/**
 * Verifies the client's registration response, persists the credential,
 * and cleans up the challenge from Redis.
 *
 * Throws if:
 *  - The challenge is missing or expired (Redis TTL).
 *  - Verification fails (bad signature, attestation mismatch, etc.).
 *  - The DB insert fails.
 */
export async function verifyAndSaveRegistration(
  userId: string,
  tenantId: string,
  response: RegistrationResponseJSON,
  deviceName?: string
): Promise<RegistrationResult> {
  // ------------------------------------------------------------------
  // Retrieve the stored challenge
  // ------------------------------------------------------------------
  const redis = getRedis();
  const storedChallenge = await redis.get(challengeKey(userId));
  if (storedChallenge === null) {
    throw new Error(
      'WebAuthn registration challenge not found or expired. Please start registration again.'
    );
  }

  // ------------------------------------------------------------------
  // Verify the response
  // ------------------------------------------------------------------
  const verification = await verifyRegistrationResponse({
    response,
    expectedChallenge: storedChallenge,
    expectedOrigin: config.webauthn.origin,
    expectedRPID: config.webauthn.rpId,
    requireUserVerification: true,
  });

  if (!verification.verified || !verification.registrationInfo) {
    throw new Error('WebAuthn registration verification failed');
  }

  const { registrationInfo } = verification;
  const {
    credential,
    aaguid,
  } = registrationInfo;

  // credential.id is a base64url string; credential.publicKey is a Uint8Array
  const credentialId = credential.id;
  const publicKeyBuffer = Buffer.from(credential.publicKey);
  const signCount = credential.counter;
  const transports = response.response.transports as AuthenticatorTransportFuture[] | undefined;

  // ------------------------------------------------------------------
  // Persist to DB
  // ------------------------------------------------------------------
  const newCredentialId = uuidv4(); // internal PK separate from FIDO2 credential ID

  await queryNoTenant(
    `INSERT INTO webauthn_credentials
       (id, credential_id, user_id, tenant_id, public_key, sign_count, transports, device_name, aaguid, created_at, last_used_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NULL)`,
    [
      newCredentialId,
      credentialId,
      userId,
      tenantId,
      publicKeyBuffer,
      signCount,
      transports ? JSON.stringify(transports) : null,
      deviceName ?? null,
      aaguid ?? null,
    ]
  );

  // ------------------------------------------------------------------
  // Clean up the challenge from Redis (single use)
  // ------------------------------------------------------------------
  await redis.del(challengeKey(userId));

  // ------------------------------------------------------------------
  // Advisory: warn if the user has fewer than 2 registered credentials
  // ------------------------------------------------------------------
  const countResult = await queryNoTenant<{ count: string }>(
    `SELECT COUNT(*) AS count FROM webauthn_credentials WHERE user_id = $1`,
    [userId]
  );
  const credCount = parseInt(countResult.rows[0]?.count ?? '0', 10);
  if (credCount < 2) {
    process.stderr.write(
      `[webauthn] WARNING: user ${userId} has only ${credCount} registered credential(s). ` +
        'Recommend registering at least 2 authenticators for account recovery.\n'
    );
  }

  return { credentialId, aaguid: aaguid ?? '' };
}

// ---------------------------------------------------------------------------
// Helper: load existing credentials for a user (used by registration begin)
// ---------------------------------------------------------------------------

export async function loadUserCredentials(
  userId: string
): Promise<WebAuthnCredential[]> {
  const result = await queryNoTenant<{
    credential_id: string;
    user_id: string;
    tenant_id: string;
    public_key: Buffer;
    sign_count: number;
    transports: string | null;
    device_name: string | null;
  }>(
    `SELECT credential_id, user_id, tenant_id, public_key, sign_count, transports, device_name
       FROM webauthn_credentials
      WHERE user_id = $1`,
    [userId]
  );

  return result.rows.map((row) => ({
    credentialId: row.credential_id,
    userId: row.user_id,
    tenantId: row.tenant_id,
    publicKey: row.public_key,
    signCount: row.sign_count,
    transports: row.transports
      ? (JSON.parse(row.transports) as AuthenticatorTransportFuture[])
      : undefined,
    deviceName: row.device_name ?? undefined,
  }));
}
