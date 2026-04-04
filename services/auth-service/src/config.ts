/**
 * Configuration module — reads from environment variables at startup.
 * Throws if required variables are missing, so the process fails fast
 * rather than encountering undefined values at runtime.
 */

function requireEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === '') {
    throw new Error(`Required environment variable "${name}" is not set`);
  }
  return value;
}

function optionalEnv(name: string, defaultValue: string): string {
  const value = process.env[name];
  return value !== undefined && value !== '' ? value : defaultValue;
}

function optionalEnvInt(name: string, defaultValue: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return defaultValue;
  const parsed = parseInt(raw, 10);
  if (isNaN(parsed)) {
    throw new Error(`Environment variable "${name}" must be an integer, got "${raw}"`);
  }
  return parsed;
}

const nodeEnv = optionalEnv('NODE_ENV', 'development');

// Vault token is required in production; in development a placeholder is allowed.
const vaultToken =
  nodeEnv === 'production'
    ? requireEnv('VAULT_TOKEN')
    : optionalEnv('VAULT_TOKEN', 'dev-root-token');

export const config = {
  db: {
    url: requireEnv('DATABASE_URL'),
  },
  redis: {
    url: optionalEnv('REDIS_URL', 'redis://localhost:6379'),
  },
  vault: {
    addr: optionalEnv('VAULT_ADDR', 'http://localhost:8200'),
    token: vaultToken,
  },
  jwt: {
    issuer: requireEnv('JWT_ISSUER'),
    audience: requireEnv('JWT_AUDIENCE'),
    /** Access tokens live for 1 hour */
    accessTokenTtlSeconds: 3600,
    /** Refresh tokens live for 7 days */
    refreshTokenTtlSeconds: 86400 * 7,
  },
  webauthn: {
    rpName: optionalEnv('WEBAUTHN_RP_NAME', 'Aegis Platform'),
    rpId: optionalEnv('WEBAUTHN_RP_ID', 'localhost'),
    origin: optionalEnv('WEBAUTHN_ORIGIN', 'http://localhost:3000'),
  },
  server: {
    port: optionalEnvInt('PORT', 3001),
    host: optionalEnv('HOST', '0.0.0.0'),
    nodeEnv,
  },
} as const;

export type Config = typeof config;
