/**
 * Fastify server bootstrap for the Aegis auth-service.
 *
 * Startup order:
 *  1. Load config (throws immediately if required env vars are missing)
 *  2. Build Fastify instance
 *  3. Register security plugins (helmet, cors, rate-limit)
 *  4. Register route plugins
 *  5. Register global error handler
 *  6. Listen
 *  7. Handle SIGTERM / SIGINT for graceful shutdown
 */

import Fastify, { type FastifyError, type FastifyInstance } from 'fastify';
import fastifyCookie from '@fastify/cookie';
import helmet from '@fastify/helmet';
import cors from '@fastify/cors';
import rateLimit from '@fastify/rate-limit';
import { ZodError } from 'zod';
import { config } from './config.js';
import { closePool, checkDbConnection } from './db.js';
import { closeRedis, checkRedisConnection } from './redis.js';
import { loadOrGenerateKeyPair } from './jwt.js';
import { authRoutes } from './routes/auth.js';

// ---------------------------------------------------------------------------
// Read package.json version for the health endpoint
// ---------------------------------------------------------------------------
// Using a static string to avoid a JSON import that may not be supported in
// all NodeNext module configurations without --resolveJsonModule adjustments.
const SERVICE_VERSION = '0.1.0';

// ---------------------------------------------------------------------------
// Build the Fastify instance
// ---------------------------------------------------------------------------

async function buildApp(): Promise<FastifyInstance> {
  const fastify = Fastify({
    logger: {
      level: config.server.nodeEnv === 'production' ? 'info' : 'debug',
      // In production use JSON (structured logging for log aggregators).
      // In development use pretty-print.
      ...(config.server.nodeEnv !== 'production'
        ? {
            transport: {
              target: 'pino-pretty',
              options: { colorize: true },
            },
          }
        : {}),
    },
    trustProxy: true,
  });

  // ----------------------------------------------------------------
  // Security: HTTP security headers
  // ----------------------------------------------------------------
  await fastify.register(helmet, {
    // Sensible defaults — enables CSP, HSTS, X-Frame-Options, etc.
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'none'"],
        frameAncestors: ["'none'"],
      },
    },
  });

  // ----------------------------------------------------------------
  // CORS — whitelist from env var (comma-separated list of origins)
  // ----------------------------------------------------------------
  const corsOrigins = (process.env['CORS_ORIGINS'] ?? '')
    .split(',')
    .map((o) => o.trim())
    .filter((o) => o.length > 0);

  await fastify.register(cors, {
    origin:
      corsOrigins.length > 0
        ? corsOrigins
        : config.server.nodeEnv === 'production'
          ? false // no CORS in production if not configured
          : true, // allow all in development
    credentials: true,
    methods: ['GET', 'POST', 'OPTIONS'],
  });

  // ----------------------------------------------------------------
  // Rate limiting — global default: 100 req/min per IP
  // Per-route overrides are specified inline (e.g. login: 10/min)
  // ----------------------------------------------------------------
  await fastify.register(rateLimit, {
    global: true,
    max: 100,
    timeWindow: '1 minute',
    // Use X-Forwarded-For when behind a trusted proxy
    keyGenerator: (request) =>
      (request.headers['x-forwarded-for'] as string | undefined)?.split(',')[0]?.trim() ??
      request.ip,
    errorResponseBuilder: (_request, context) => ({
      error: 'rate_limit_exceeded',
      message: `Too many requests. Retry after ${context.after}.`,
      retryAfter: context.after,
    }),
  });

  // ----------------------------------------------------------------
  // Cookie plugin (required for refresh token httpOnly cookie)
  // ----------------------------------------------------------------
  await fastify.register(fastifyCookie, {
    secret: process.env['COOKIE_SECRET'] ?? 'aegis-cookie-secret-change-in-production',
  });

  // ----------------------------------------------------------------
  // Routes
  // ----------------------------------------------------------------
  await fastify.register(authRoutes);

  // ----------------------------------------------------------------
  // Health check — checks DB + Redis liveness
  // ----------------------------------------------------------------
  fastify.get('/health', async (_request, reply) => {
    const [dbOk, redisOk] = await Promise.all([
      checkDbConnection(),
      checkRedisConnection(),
    ]);

    const status = dbOk && redisOk ? 'ok' : 'degraded';
    const httpStatus = status === 'ok' ? 200 : 503;

    return reply.status(httpStatus).send({
      status,
      timestamp: new Date().toISOString(),
      version: SERVICE_VERSION,
      checks: {
        database: dbOk ? 'ok' : 'error',
        redis: redisOk ? 'ok' : 'error',
      },
    });
  });

  // ----------------------------------------------------------------
  // Global error handler
  // ----------------------------------------------------------------
  fastify.setErrorHandler((error: FastifyError | ZodError | Error, request, reply) => {
    const isProd = config.server.nodeEnv === 'production';

    // ZodError → 400
    if (error instanceof ZodError) {
      return reply.status(400).send({
        error: 'validation_error',
        message: 'Request validation failed',
        details: error.flatten(),
      });
    }

    // Fastify rate-limit → 429 (already handled by errorResponseBuilder above,
    // but belt-and-suspenders check)
    if ((error as FastifyError).statusCode === 429) {
      return reply.status(429).send({
        error: 'rate_limit_exceeded',
        message: error.message,
      });
    }

    // Known auth errors (our custom error types) → 401
    if (
      error.name === 'TokenExpiredError' ||
      error.name === 'TokenSignatureError' ||
      error.name === 'TokenMalformedError' ||
      error.name === 'TokenClaimsError'
    ) {
      return reply.status(401).send({
        error: 'invalid_token',
        message: isProd ? 'Authentication failed' : error.message,
      });
    }

    // Fastify validation errors → 400
    if ((error as FastifyError).validation !== undefined) {
      return reply.status(400).send({
        error: 'validation_error',
        message: error.message,
      });
    }

    // Everything else → 500, never leaking stack traces in production
    const statusCode = (error as FastifyError).statusCode ?? 500;
    request.log.error({
      msg: 'Unhandled error',
      error: error.message,
      stack: isProd ? undefined : error.stack,
    });

    return reply.status(statusCode >= 400 ? statusCode : 500).send({
      error: 'internal_error',
      message: isProd ? 'An internal error occurred' : error.message,
    });
  });

  return fastify;
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // Fail fast if required env vars are missing (config throws at import time,
  // but we call this explicitly so errors surface before Fastify starts).
  const { port, host, nodeEnv } = config.server;

  const app = await buildApp();

  // Pre-load the JWT key pair so the first request is not slower
  try {
    await loadOrGenerateKeyPair();
    app.log.info('JWT key pair loaded');
  } catch (err) {
    app.log.error({ msg: 'Failed to load JWT key pair', error: String(err) });
    process.exit(1);
  }

  // ----------------------------------------------------------------
  // Graceful shutdown
  // ----------------------------------------------------------------
  const shutdown = async (signal: string): Promise<void> => {
    app.log.info({ msg: `Received ${signal} — shutting down gracefully` });
    try {
      // 1. Stop accepting new connections
      await app.close();
      // 2. Drain DB pool
      await closePool();
      // 3. Close Redis connection
      await closeRedis();
      app.log.info('Shutdown complete');
      process.exit(0);
    } catch (err) {
      app.log.error({ msg: 'Error during shutdown', error: String(err) });
      process.exit(1);
    }
  };

  process.once('SIGTERM', () => { void shutdown('SIGTERM'); });
  process.once('SIGINT',  () => { void shutdown('SIGINT');  });

  // ----------------------------------------------------------------
  // Listen
  // ----------------------------------------------------------------
  try {
    await app.listen({ port, host });
    app.log.info({
      msg: `auth-service listening`,
      port,
      host,
      env: nodeEnv,
    });
  } catch (err) {
    app.log.error({ msg: 'Failed to start server', error: String(err) });
    process.exit(1);
  }
}

void main();
