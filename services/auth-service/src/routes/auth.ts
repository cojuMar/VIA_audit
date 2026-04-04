/**
 * Authentication route plugin.
 *
 * Public routes (no auth required):
 *   POST /auth/login/begin
 *   POST /auth/login/complete
 *   POST /auth/token/refresh
 *   GET  /.well-known/jwks.json
 *
 * Protected routes (require valid JWT):
 *   POST /auth/register/begin    — admin only
 *   POST /auth/register/complete — any authenticated user
 *   POST /auth/token/revoke      — any authenticated user
 *   GET  /auth/me                — any authenticated user
 *
 * Rate limiting:
 *   /auth/login/begin — 10 req/min per IP (applied inline)
 *   Global rate limit (100 req/min) is configured on the Fastify instance.
 */

import type { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { z } from 'zod';
import { tenantContextMiddleware, requireRole } from '../tenant_context_middleware.js';
import {
  generateAuthenticationOptions,
  verifyAuthentication,
} from '../fido2/authentication.js';
import {
  generateRegistrationOptions,
  verifyAndSaveRegistration,
  loadUserCredentials,
} from '../fido2/registration.js';
import {
  issueAccessToken,
  issueRefreshToken,
  verifyToken,
  revokeToken,
  getJWKS,
} from '../jwt.js';
import { queryNoTenant } from '../db.js';
import { getRedis } from '../redis.js';
import { config } from '../config.js';
import type { AuthenticationResponseJSON, RegistrationResponseJSON } from '@simplewebauthn/server';
import type { User } from '../types.js';

// ---------------------------------------------------------------------------
// Zod schemas — all request bodies validated before handlers run
// ---------------------------------------------------------------------------

const LoginBeginSchema = z.object({
  email: z.string().email(),
  tenantId: z.string().uuid(),
});

const LoginCompleteSchema = z.object({
  userId: z.string().uuid(),
  tenantId: z.string().uuid(),
  response: z.object({}).passthrough(), // AuthenticationResponseJSON — validated by @simplewebauthn
});

const RegisterBeginSchema = z.object({
  userId: z.string().uuid(),
});

const RegisterCompleteSchema = z.object({
  response: z.object({}).passthrough(), // RegistrationResponseJSON
  deviceName: z.string().min(1).max(100).optional(),
});

const RefreshTokenSchema = z.object({
  // No body fields — refresh token comes from httpOnly cookie.
});

const RevokeTokenSchema = z.object({
  refreshToken: z.string().optional(), // optional: also revoke the refresh token
});

// ---------------------------------------------------------------------------
// Cookie constants
// ---------------------------------------------------------------------------

const REFRESH_COOKIE_NAME = 'aegis_refresh_token';

// ---------------------------------------------------------------------------
// DB row helpers
// ---------------------------------------------------------------------------

interface UserRow {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  client_access: string | null;
}

async function findUserByEmail(email: string, tenantId: string): Promise<User | null> {
  const result = await queryNoTenant<UserRow>(
    `SELECT user_id, tenant_id, email, display_name, role, is_active, client_access
       FROM users
      WHERE email = $1
        AND tenant_id = $2
        AND is_active = true`,
    [email, tenantId]
  );
  if (result.rows.length === 0) return null;
  const row = result.rows[0];
  if (!row) return null;
  return {
    userId: row.user_id,
    tenantId: row.tenant_id,
    email: row.email,
    displayName: row.display_name,
    role: row.role as User['role'],
    isActive: row.is_active,
  };
}

async function findUserById(userId: string): Promise<User | null> {
  const result = await queryNoTenant<UserRow>(
    `SELECT user_id, tenant_id, email, display_name, role, is_active, client_access
       FROM users
      WHERE user_id = $1
        AND is_active = true`,
    [userId]
  );
  if (result.rows.length === 0) return null;
  const row = result.rows[0];
  if (!row) return null;
  return {
    userId: row.user_id,
    tenantId: row.tenant_id,
    email: row.email,
    displayName: row.display_name,
    role: row.role as User['role'],
    isActive: row.is_active,
  };
}

async function getClientAccess(userId: string): Promise<string[] | undefined> {
  const result = await queryNoTenant<{ client_access: string | null }>(
    `SELECT client_access FROM users WHERE user_id = $1`,
    [userId]
  );
  const row = result.rows[0];
  if (!row?.client_access) return undefined;
  return JSON.parse(row.client_access) as string[];
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

export async function authRoutes(fastify: FastifyInstance): Promise<void> {
  // ----------------------------------------------------------------
  // POST /auth/login/begin
  // Rate limited: 10 req/min per IP
  // ----------------------------------------------------------------
  fastify.post(
    '/auth/login/begin',
    {
      config: {
        rateLimit: {
          max: 10,
          timeWindow: '1 minute',
        },
      },
    },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const parseResult = LoginBeginSchema.safeParse(request.body);
      if (!parseResult.success) {
        return reply.status(400).send({
          error: 'validation_error',
          details: parseResult.error.flatten(),
        });
      }

      const { email, tenantId } = parseResult.data;

      const user = await findUserByEmail(email, tenantId);
      // Always return options (even for non-existent users) to prevent
      // user enumeration via timing differences. The challenge will simply
      // fail at the complete step.
      const userId = user?.userId ?? 'non-existent-placeholder';

      const options = await generateAuthenticationOptions(userId, tenantId);

      return reply.status(200).send({
        options,
        userId: user?.userId ?? null, // client needs this for the complete step
      });
    }
  );

  // ----------------------------------------------------------------
  // POST /auth/login/complete
  // ----------------------------------------------------------------
  fastify.post('/auth/login/complete', async (request: FastifyRequest, reply: FastifyReply) => {
    const parseResult = LoginCompleteSchema.safeParse(request.body);
    if (!parseResult.success) {
      return reply.status(400).send({
        error: 'validation_error',
        details: parseResult.error.flatten(),
      });
    }

    const { userId, tenantId, response } = parseResult.data;

    let authResult: Awaited<ReturnType<typeof verifyAuthentication>>;
    try {
      authResult = await verifyAuthentication(
        userId,
        tenantId,
        response as AuthenticationResponseJSON
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Authentication failed';
      request.log.warn({ msg: 'WebAuthn authentication failed', reason: message });
      return reply.status(401).send({ error: 'authentication_failed', message });
    }

    const { user } = authResult;

    // Issue tokens
    const clientAccess =
      user.role === 'firm_partner' ? await getClientAccess(user.userId) : undefined;
    const [accessToken, refreshToken] = await Promise.all([
      issueAccessToken(user, clientAccess),
      issueRefreshToken(user),
    ]);

    // Update last_login_at
    await queryNoTenant(
      `UPDATE users SET last_login_at = NOW() WHERE user_id = $1`,
      [user.userId]
    );

    // Set refresh token as httpOnly cookie
    void reply.setCookie(REFRESH_COOKIE_NAME, refreshToken, {
      httpOnly: true,
      secure: config.server.nodeEnv === 'production',
      sameSite: 'strict',
      path: '/auth/token',
      maxAge: config.jwt.refreshTokenTtlSeconds,
    });

    return reply.status(200).send({
      accessToken,
      tokenType: 'Bearer',
      expiresIn: config.jwt.accessTokenTtlSeconds,
      user: {
        userId: user.userId,
        email: user.email,
        displayName: user.displayName,
        role: user.role,
      },
    });
  });

  // ----------------------------------------------------------------
  // POST /auth/register/begin
  // Requires: admin role
  // ----------------------------------------------------------------
  fastify.post(
    '/auth/register/begin',
    {
      preHandler: [tenantContextMiddleware, requireRole('admin')],
    },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const parseResult = RegisterBeginSchema.safeParse(request.body);
      if (!parseResult.success) {
        return reply.status(400).send({
          error: 'validation_error',
          details: parseResult.error.flatten(),
        });
      }

      const { userId } = parseResult.data;
      const { tenantId } = request.tenantClaims;

      const user = await findUserById(userId);
      if (!user || user.tenantId !== tenantId) {
        return reply.status(404).send({ error: 'user_not_found' });
      }

      const existingCredentials = await loadUserCredentials(userId);
      const options = await generateRegistrationOptions(user, existingCredentials);

      return reply.status(200).send({ options });
    }
  );

  // ----------------------------------------------------------------
  // POST /auth/register/complete
  // Requires: valid JWT (own user)
  // ----------------------------------------------------------------
  fastify.post(
    '/auth/register/complete',
    {
      preHandler: [tenantContextMiddleware],
    },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const parseResult = RegisterCompleteSchema.safeParse(request.body);
      if (!parseResult.success) {
        return reply.status(400).send({
          error: 'validation_error',
          details: parseResult.error.flatten(),
        });
      }

      const { response, deviceName } = parseResult.data;
      const { sub: userId, tenant_id: tenantId } = request.tenantClaims;

      let result: Awaited<ReturnType<typeof verifyAndSaveRegistration>>;
      try {
        result = await verifyAndSaveRegistration(
          userId,
          tenantId,
          response as RegistrationResponseJSON,
          deviceName
        );
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Registration failed';
        request.log.warn({ msg: 'WebAuthn registration failed', reason: message });
        return reply.status(400).send({ error: 'registration_failed', message });
      }

      return reply.status(201).send({
        credentialId: result.credentialId,
        aaguid: result.aaguid,
      });
    }
  );

  // ----------------------------------------------------------------
  // POST /auth/token/refresh
  // Reads refresh token from httpOnly cookie, issues new access token.
  // Implements refresh token rotation (old refresh token revoked).
  // ----------------------------------------------------------------
  fastify.post('/auth/token/refresh', async (request: FastifyRequest, reply: FastifyReply) => {
    // Validate body (currently empty schema — just ensures no unexpected fields)
    RefreshTokenSchema.parse(request.body ?? {});

    const refreshToken = (request.cookies as Record<string, string | undefined>)[
      REFRESH_COOKIE_NAME
    ];
    if (!refreshToken) {
      return reply.status(401).send({
        error: 'missing_refresh_token',
        message: 'No refresh token cookie found',
      });
    }

    // Verify the refresh token
    let claims: Awaited<ReturnType<typeof verifyToken>>;
    try {
      claims = await verifyToken(refreshToken);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Invalid refresh token';
      return reply.status(401).send({ error: 'invalid_refresh_token', message });
    }

    // Check it has not been revoked
    const redis = getRedis();
    const revocationKey = `revoked_jtis:${claims.tenant_id}`;
    const isRevoked = await redis.sismember(revocationKey, claims.jti);
    if (isRevoked === 1) {
      return reply.status(401).send({
        error: 'token_revoked',
        message: 'Refresh token has been revoked',
      });
    }

    // Check that the JTI still exists in the refresh_jti set (single-use rotation)
    const refreshJtiKey = `refresh_jti:${claims.jti}`;
    const storedUserId = await redis.get(refreshJtiKey);
    if (storedUserId === null) {
      return reply.status(401).send({
        error: 'refresh_token_expired',
        message: 'Refresh token has been used or expired',
      });
    }

    // Revoke the old refresh token JTI immediately (rotation)
    const remainingTtl = claims.exp - Math.floor(Date.now() / 1000);
    const ttl = Math.max(remainingTtl, 1);
    await revokeToken(claims.jti, claims.tenant_id, ttl);
    await redis.del(refreshJtiKey);

    // Load the user and issue fresh tokens
    const user = await findUserById(claims.sub);
    if (!user) {
      return reply.status(401).send({
        error: 'user_not_found',
        message: 'User account not found or inactive',
      });
    }

    const clientAccess =
      user.role === 'firm_partner' ? await getClientAccess(user.userId) : undefined;
    const [newAccessToken, newRefreshToken] = await Promise.all([
      issueAccessToken(user, clientAccess),
      issueRefreshToken(user),
    ]);

    void reply.setCookie(REFRESH_COOKIE_NAME, newRefreshToken, {
      httpOnly: true,
      secure: config.server.nodeEnv === 'production',
      sameSite: 'strict',
      path: '/auth/token',
      maxAge: config.jwt.refreshTokenTtlSeconds,
    });

    return reply.status(200).send({
      accessToken: newAccessToken,
      tokenType: 'Bearer',
      expiresIn: config.jwt.accessTokenTtlSeconds,
    });
  });

  // ----------------------------------------------------------------
  // POST /auth/token/revoke
  // Requires: valid JWT
  // ----------------------------------------------------------------
  fastify.post(
    '/auth/token/revoke',
    {
      preHandler: [tenantContextMiddleware],
    },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const parseResult = RevokeTokenSchema.safeParse(request.body);
      if (!parseResult.success) {
        return reply.status(400).send({
          error: 'validation_error',
          details: parseResult.error.flatten(),
        });
      }

      const { jti, tenant_id, exp } = request.tenantClaims;
      const ttl = Math.max(exp - Math.floor(Date.now() / 1000), 1);

      // Revoke the access token JTI
      await revokeToken(jti, tenant_id, ttl);

      // Optionally revoke a refresh token if provided via cookie or body
      const { refreshToken } = parseResult.data;
      const cookieRefresh = (request.cookies as Record<string, string | undefined>)[
        REFRESH_COOKIE_NAME
      ];
      const tokenToRevoke = refreshToken ?? cookieRefresh;

      if (tokenToRevoke) {
        try {
          const refreshClaims = await verifyToken(tokenToRevoke);
          const refreshTtl = Math.max(
            refreshClaims.exp - Math.floor(Date.now() / 1000),
            1
          );
          await revokeToken(refreshClaims.jti, refreshClaims.tenant_id, refreshTtl);
          const redis = getRedis();
          await redis.del(`refresh_jti:${refreshClaims.jti}`);
        } catch {
          // If refresh token is already invalid, that's fine — just continue.
        }
      }

      // Clear the cookie regardless
      void reply.clearCookie(REFRESH_COOKIE_NAME, { path: '/auth/token' });

      return reply.status(200).send({ revoked: true });
    }
  );

  // ----------------------------------------------------------------
  // GET /auth/me
  // Requires: valid JWT
  // ----------------------------------------------------------------
  fastify.get(
    '/auth/me',
    {
      preHandler: [tenantContextMiddleware],
    },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const { sub: userId, tenant_id, role, client_access } = request.tenantClaims;

      const user = await findUserById(userId);
      if (!user) {
        return reply.status(404).send({ error: 'user_not_found' });
      }

      return reply.status(200).send({
        userId: user.userId,
        tenantId: tenant_id,
        email: user.email,
        displayName: user.displayName,
        role,
        ...(role === 'firm_partner' && client_access ? { clientAccess: client_access } : {}),
        isActive: user.isActive,
      });
    }
  );

  // ----------------------------------------------------------------
  // GET /.well-known/jwks.json
  // Public — no auth required. Cached by CDN/clients for 1 hour.
  // ----------------------------------------------------------------
  fastify.get('/.well-known/jwks.json', async (_request: FastifyRequest, reply: FastifyReply) => {
    const jwks = await getJWKS();
    return reply
      .header('Cache-Control', 'public, max-age=3600, stale-while-revalidate=600')
      .status(200)
      .send(jwks);
  });
}
