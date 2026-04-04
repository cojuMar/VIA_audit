/**
 * JWT issuance, verification, and rotation.
 *
 * Key design decisions:
 *  - RS256 (asymmetric) so verifiers only need the public JWKS, never the
 *    private key.
 *  - Key pairs are stored in the DB (`jwt_rotation_keys` table).
 *    On startup, if no active key exists a new one is generated.
 *  - Refresh token JTIs are tracked in Redis with a TTL matching the token
 *    expiry, enabling single-use rotation.
 *  - Error types are our own — raw jsonwebtoken errors are never surfaced
 *    to callers, preventing information leakage.
 */

import * as jose from 'node-jose';
import jwt from 'jsonwebtoken';
import { v4 as uuidv4 } from 'uuid';
import { config } from './config.js';
import { queryNoTenant } from './db.js';
import { getRedis } from './redis.js';
import type { TenantClaims, User, UserRole } from './types.js';

// ---------------------------------------------------------------------------
// Custom error hierarchy — never expose raw JWT library errors
// ---------------------------------------------------------------------------

export class TokenExpiredError extends Error {
  constructor() {
    super('Token has expired');
    this.name = 'TokenExpiredError';
  }
}

export class TokenSignatureError extends Error {
  constructor() {
    super('Token signature is invalid');
    this.name = 'TokenSignatureError';
  }
}

export class TokenMalformedError extends Error {
  constructor(detail: string) {
    super(`Token is malformed: ${detail}`);
    this.name = 'TokenMalformedError';
  }
}

export class TokenClaimsError extends Error {
  constructor(detail: string) {
    super(`Token claims invalid: ${detail}`);
    this.name = 'TokenClaimsError';
  }
}

// ---------------------------------------------------------------------------
// In-memory cache for the active key pair (avoids a DB round-trip per request)
// ---------------------------------------------------------------------------

interface CachedKeyPair {
  keyId: string;
  /** node-jose key used to sign tokens */
  privateKey: jose.JWK.Key;
  /** PEM — used by jsonwebtoken verify */
  publicKeyPem: string;
}

let _cachedKeyPair: CachedKeyPair | null = null;

// ---------------------------------------------------------------------------
// Key management
// ---------------------------------------------------------------------------

/**
 * Loads the active RSA key pair from the DB, or generates a new one if none
 * exists. Caches the result in memory for the lifetime of the process.
 *
 * DB schema assumed:
 *   jwt_rotation_keys (
 *     key_id        TEXT PRIMARY KEY,
 *     public_key    TEXT NOT NULL,          -- PEM
 *     private_key   TEXT NOT NULL,          -- PEM (encrypted at rest by Vault ideally)
 *     algorithm     TEXT NOT NULL,          -- 'RS256'
 *     is_active     BOOLEAN NOT NULL,
 *     created_at    TIMESTAMPTZ NOT NULL
 *   )
 */
export async function loadOrGenerateKeyPair(): Promise<CachedKeyPair> {
  if (_cachedKeyPair !== null) return _cachedKeyPair;

  // Try to load from DB first
  const result = await queryNoTenant<{
    key_id: string;
    public_key: string;
    private_key: string;
  }>(
    `SELECT key_id, public_key, private_key
       FROM jwt_rotation_keys
      WHERE is_active = true
      ORDER BY created_at DESC
      LIMIT 1`,
    []
  );

  if (result.rows.length > 0) {
    const row = result.rows[0];
    if (!row) throw new Error('Unexpected empty row from jwt_rotation_keys');

    const keystore = jose.JWK.createKeyStore();
    const privateKey = await keystore.add(row.private_key, 'pem');

    _cachedKeyPair = {
      keyId: row.key_id,
      privateKey,
      publicKeyPem: row.public_key,
    };

    return _cachedKeyPair;
  }

  // No active key — generate a fresh 2048-bit RSA key pair
  process.stderr.write(
    '[jwt] No active key pair found in DB — generating new RSA-2048 key pair\n'
  );

  const keystore = jose.JWK.createKeyStore();
  const newKey = await keystore.generate('RSA', 2048, { alg: 'RS256', use: 'sig' });

  const publicKeyPem = newKey.toPEM(false);
  const privateKeyPem = newKey.toPEM(true);
  const keyId = uuidv4();

  await queryNoTenant(
    `INSERT INTO jwt_rotation_keys (key_id, public_key, private_key, algorithm, is_active, created_at)
     VALUES ($1, $2, $3, 'RS256', true, NOW())`,
    [keyId, publicKeyPem, privateKeyPem]
  );

  _cachedKeyPair = {
    keyId,
    privateKey: newKey,
    publicKeyPem,
  };

  return _cachedKeyPair;
}

/**
 * Invalidates the in-memory key cache.
 * Call after a key rotation event so the next request reloads from DB.
 */
export function invalidateKeyCache(): void {
  _cachedKeyPair = null;
}

// ---------------------------------------------------------------------------
// Token issuance
// ---------------------------------------------------------------------------

/**
 * Issues a short-lived access token (RS256, exp = now + 1 hour).
 */
export async function issueAccessToken(
  user: User,
  clientAccess?: string[]
): Promise<string> {
  const keyPair = await loadOrGenerateKeyPair();
  const now = Math.floor(Date.now() / 1000);
  const jti = uuidv4();

  const payload: TenantClaims & { iss: string; aud: string } = {
    sub: user.userId,
    tenant_id: user.tenantId,
    role: user.role,
    ...(user.role === 'firm_partner' && clientAccess !== undefined
      ? { client_access: clientAccess }
      : {}),
    iat: now,
    exp: now + config.jwt.accessTokenTtlSeconds,
    jti,
    iss: config.jwt.issuer,
    aud: config.jwt.audience,
  };

  // node-jose sign — produces a compact JWS string
  const signer = jose.JWS.createSign(
    { format: 'compact', fields: { kid: keyPair.keyId, alg: 'RS256' } },
    keyPair.privateKey
  );

  return signer.update(JSON.stringify(payload)).final() as unknown as Promise<string>;
}

/**
 * Issues a long-lived refresh token (RS256, exp = now + 7 days).
 * The JTI is stored in Redis so it can be validated and rotated.
 */
export async function issueRefreshToken(user: User): Promise<string> {
  const keyPair = await loadOrGenerateKeyPair();
  const now = Math.floor(Date.now() / 1000);
  const jti = uuidv4();
  const exp = now + config.jwt.refreshTokenTtlSeconds;

  const payload = {
    sub: user.userId,
    tenant_id: user.tenantId,
    role: user.role,
    type: 'refresh',
    iat: now,
    exp,
    jti,
    iss: config.jwt.issuer,
    aud: config.jwt.audience,
  };

  // Store JTI in Redis with TTL matching the token expiry
  const redis = getRedis();
  const refreshKey = `refresh_jti:${jti}`;
  await redis.set(refreshKey, user.userId, 'EX', config.jwt.refreshTokenTtlSeconds);

  const signer = jose.JWS.createSign(
    { format: 'compact', fields: { kid: keyPair.keyId, alg: 'RS256' } },
    keyPair.privateKey
  );

  return signer.update(JSON.stringify(payload)).final() as unknown as Promise<string>;
}

// ---------------------------------------------------------------------------
// Token verification
// ---------------------------------------------------------------------------

const VALID_ROLES: ReadonlySet<string> = new Set<UserRole>([
  'admin',
  'auditor',
  'firm_partner',
  'smb_owner',
  'readonly',
]);

/**
 * Verifies a token's signature, expiry, issuer, and audience.
 * Returns the typed TenantClaims on success.
 * Throws one of our custom error types on failure — never the raw library error.
 */
export async function verifyToken(token: string): Promise<TenantClaims> {
  const keyPair = await loadOrGenerateKeyPair();

  let decoded: jwt.JwtPayload;
  try {
    decoded = jwt.verify(token, keyPair.publicKeyPem, {
      algorithms: ['RS256'],
      issuer: config.jwt.issuer,
      audience: config.jwt.audience,
    }) as jwt.JwtPayload;
  } catch (err) {
    if (err instanceof jwt.TokenExpiredError) {
      throw new TokenExpiredError();
    }
    if (
      err instanceof jwt.JsonWebTokenError &&
      err.message.includes('invalid signature')
    ) {
      throw new TokenSignatureError();
    }
    if (err instanceof jwt.JsonWebTokenError) {
      throw new TokenMalformedError(err.message);
    }
    throw new TokenMalformedError('Unknown verification error');
  }

  // Validate required application claims
  if (typeof decoded.sub !== 'string' || decoded.sub === '') {
    throw new TokenClaimsError('missing sub');
  }
  if (typeof decoded['tenant_id'] !== 'string' || decoded['tenant_id'] === '') {
    throw new TokenClaimsError('missing tenant_id');
  }
  if (typeof decoded['role'] !== 'string' || !VALID_ROLES.has(decoded['role'])) {
    throw new TokenClaimsError(`invalid role: ${String(decoded['role'])}`);
  }
  if (typeof decoded['jti'] !== 'string' || decoded['jti'] === '') {
    throw new TokenClaimsError('missing jti');
  }
  if (typeof decoded['iat'] !== 'number') {
    throw new TokenClaimsError('missing iat');
  }
  if (typeof decoded['exp'] !== 'number') {
    throw new TokenClaimsError('missing exp');
  }

  const claims: TenantClaims = {
    sub: decoded.sub,
    tenant_id: decoded['tenant_id'] as string,
    role: decoded['role'] as UserRole,
    iat: decoded['iat'] as number,
    exp: decoded['exp'] as number,
    jti: decoded['jti'] as string,
  };

  const clientAccess = decoded['client_access'];
  if (
    claims.role === 'firm_partner' &&
    Array.isArray(clientAccess) &&
    clientAccess.every((c): c is string => typeof c === 'string')
  ) {
    claims.client_access = clientAccess;
  }

  return claims;
}

// ---------------------------------------------------------------------------
// Token revocation
// ---------------------------------------------------------------------------

/**
 * Adds `jti` to the per-tenant Redis revocation set with a TTL.
 * The TTL should match the token's remaining lifetime so the set does not
 * grow unboundedly.
 */
export async function revokeToken(
  jti: string,
  tenantId: string,
  ttlSeconds: number
): Promise<void> {
  const redis = getRedis();
  const key = `revoked_jtis:${tenantId}`;

  // Add to set and ensure the set itself has a TTL.
  // We use a pipeline to make both operations atomic-ish.
  const pipeline = redis.pipeline();
  pipeline.sadd(key, jti);
  pipeline.expire(key, ttlSeconds);
  await pipeline.exec();
}

// ---------------------------------------------------------------------------
// JWKS endpoint
// ---------------------------------------------------------------------------

/**
 * Returns the JWKS document for the `/.well-known/jwks.json` endpoint.
 * Only the public key is included — never the private key.
 */
export async function getJWKS(): Promise<{ keys: jose.JWK.Key[] }> {
  const keyPair = await loadOrGenerateKeyPair();

  // Export the public key as a JWK object (no private material)
  const publicJwk = keyPair.privateKey.toJSON(false) as jose.JWK.Key;

  return { keys: [publicJwk] };
}
