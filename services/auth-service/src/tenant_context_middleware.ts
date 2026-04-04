/**
 * Tenant context middleware — THE most critical security boundary.
 *
 * Every protected route MUST be gated by this middleware. It:
 *   1. Extracts and validates the Bearer JWT
 *   2. Checks the token has not been revoked (Redis revocation set)
 *   3. Validates required claims: tenant_id (UUIDv4), sub, role, jti
 *   4. Attaches verified claims to `request.tenantClaims`
 *
 * It deliberately does NOT log the raw token — only the tenant_id and jti.
 */

import { FastifyRequest, FastifyReply, FastifyInstance } from 'fastify';
import { verifyToken } from './jwt.js';
import { getRedis } from './redis.js';
import type { TenantClaims, UserRole } from './types.js';

// ---------------------------------------------------------------------------
// Fastify augmentation — carries verified claims through the request lifecycle
// ---------------------------------------------------------------------------

declare module 'fastify' {
  interface FastifyRequest {
    tenantClaims: TenantClaims;
  }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** UUID v4 regex — enforces the format, not just "is a string". */
const UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const VALID_ROLES: ReadonlySet<string> = new Set<UserRole>([
  'admin',
  'auditor',
  'firm_partner',
  'smb_owner',
  'readonly',
]);

// ---------------------------------------------------------------------------
// Main middleware
// ---------------------------------------------------------------------------

export async function tenantContextMiddleware(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  // ------------------------------------------------------------------
  // 1. Extract the Authorization header
  // ------------------------------------------------------------------
  const authHeader = request.headers['authorization'];
  if (typeof authHeader !== 'string' || !authHeader.startsWith('Bearer ')) {
    return reply.status(401).send({
      error: 'missing_token',
      message: 'Authorization: Bearer <token> header is required',
    });
  }

  const token = authHeader.slice(7); // strip "Bearer "

  // ------------------------------------------------------------------
  // 2. Verify signature + standard JWT claims (exp, iss, aud)
  // ------------------------------------------------------------------
  let claims: TenantClaims;
  try {
    claims = await verifyToken(token);
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Token verification failed';
    // Intentionally do NOT include the raw token in the log
    request.log.warn({ msg: 'JWT verification failed', reason: message });
    return reply.status(401).send({ error: 'invalid_token', message });
  }

  // ------------------------------------------------------------------
  // 3. Validate required application-level claims
  // ------------------------------------------------------------------
  if (!claims.tenant_id || !UUID_V4_RE.test(claims.tenant_id)) {
    request.log.warn({ msg: 'JWT missing or invalid tenant_id' });
    return reply.status(401).send({
      error: 'invalid_token',
      message: 'Token is missing a valid tenant_id claim',
    });
  }

  if (!claims.sub || typeof claims.sub !== 'string') {
    return reply.status(401).send({
      error: 'invalid_token',
      message: 'Token is missing sub claim',
    });
  }

  if (!claims.role || !VALID_ROLES.has(claims.role)) {
    return reply.status(401).send({
      error: 'invalid_token',
      message: `Token contains an unknown role: "${String(claims.role)}"`,
    });
  }

  if (!claims.jti || typeof claims.jti !== 'string') {
    return reply.status(401).send({
      error: 'invalid_token',
      message: 'Token is missing jti claim',
    });
  }

  // ------------------------------------------------------------------
  // 4. Check the revocation set in Redis
  // ------------------------------------------------------------------
  const revocationKey = `revoked_jtis:${claims.tenant_id}`;
  try {
    const redis = getRedis();
    const isRevoked = await redis.sismember(revocationKey, claims.jti);
    if (isRevoked === 1) {
      request.log.warn({
        msg: 'Revoked JWT presented',
        jti: claims.jti,
        tenant_id: claims.tenant_id,
      });
      return reply.status(401).send({
        error: 'token_revoked',
        message: 'This token has been revoked',
      });
    }
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Redis error';
    // If Redis is unavailable we must fail closed — deny access.
    request.log.error({
      msg: 'Redis revocation check failed — denying request',
      error: message,
      tenant_id: claims.tenant_id,
    });
    return reply.status(503).send({
      error: 'service_unavailable',
      message: 'Unable to validate token revocation status',
    });
  }

  // ------------------------------------------------------------------
  // 5. Attach claims and log (never log the raw token)
  // ------------------------------------------------------------------
  request.tenantClaims = claims;

  request.log.debug({
    msg: 'Tenant context established',
    tenant_id: claims.tenant_id,
    sub: claims.sub,
    role: claims.role,
    jti: claims.jti,
  });
}

// ---------------------------------------------------------------------------
// Role-based access control preHandler factory
// ---------------------------------------------------------------------------

/**
 * Returns a Fastify preHandler that checks the request's role is in the
 * `allowedRoles` list. Must run AFTER `tenantContextMiddleware`.
 *
 * Usage:
 *   fastify.post('/admin/thing', {
 *     preHandler: [requireRole('admin')],
 *   }, handler);
 */
export function requireRole(
  ...allowedRoles: UserRole[]
): (request: FastifyRequest, reply: FastifyReply) => Promise<void> {
  const allowed = new Set<string>(allowedRoles);

  return async function roleGuard(
    request: FastifyRequest,
    reply: FastifyReply
  ): Promise<void> {
    // tenantClaims must have been set by tenantContextMiddleware first.
    if (!request.tenantClaims) {
      return reply.status(401).send({
        error: 'unauthenticated',
        message: 'Authentication required',
      });
    }

    if (!allowed.has(request.tenantClaims.role)) {
      request.log.warn({
        msg: 'Forbidden — insufficient role',
        required: allowedRoles,
        actual: request.tenantClaims.role,
        sub: request.tenantClaims.sub,
        tenant_id: request.tenantClaims.tenant_id,
      });
      return reply.status(403).send({
        error: 'forbidden',
        message: `This action requires one of: ${allowedRoles.join(', ')}`,
      });
    }
  };
}

// ---------------------------------------------------------------------------
// Plugin registration helper
// ---------------------------------------------------------------------------

/**
 * Registers `tenantContextMiddleware` as a global `onRequest` hook.
 *
 * Call this from the Fastify bootstrap ONLY on a sub-router that covers
 * protected routes — public routes (login, JWKS) must be registered on
 * a sibling router that does NOT have this hook.
 */
export function registerTenantMiddleware(fastify: FastifyInstance): void {
  fastify.addHook('onRequest', tenantContextMiddleware);
}
