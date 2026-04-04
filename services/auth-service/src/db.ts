/**
 * PostgreSQL connection pool with row-level tenant isolation.
 *
 * Every application query MUST use `withTenantContext` so that
 * PostgreSQL's row-level security policies receive `app.tenant_id`.
 * The only exception is `queryNoTenant`, reserved for auth-service
 * bootstrap tables (jwt_rotation_keys, webauthn_credentials, users)
 * where the service authenticates before a tenant is known.
 */

import { Pool, PoolClient } from 'pg';
import { config } from './config.js';

// ---------------------------------------------------------------------------
// Pool singleton
// ---------------------------------------------------------------------------

let pool: Pool | null = null;

export function getPool(): Pool {
  if (pool !== null) return pool;

  pool = new Pool({
    connectionString: config.db.url,
    max: 20,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });

  pool.on('error', (err: Error) => {
    process.stderr.write(`[db] Unexpected pool error: ${err.message}\n`);
  });

  return pool;
}

// ---------------------------------------------------------------------------
// Tenant-scoped query helper (the standard path for all application queries)
// ---------------------------------------------------------------------------

/**
 * Acquires a client, wraps the callback in an explicit transaction, and
 * sets `app.tenant_id` for the duration of the transaction so that
 * PostgreSQL RLS policies can enforce tenant isolation.
 *
 * @param tenantId  The UUID of the tenant whose data is being accessed.
 * @param fn        Callback that receives the scoped PoolClient.
 */
export async function withTenantContext<T>(
  tenantId: string,
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await getPool().connect();
  try {
    await client.query('BEGIN');
    // Use parameterised query — never string interpolation — to prevent
    // any possibility of SQL injection via a crafted tenantId.
    await client.query('SET LOCAL app.tenant_id = $1', [tenantId]);
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK').catch((rollbackErr: Error) => {
      process.stderr.write(
        `[db] Rollback failed after error: ${rollbackErr.message}\n`
      );
    });
    throw err;
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
// Platform-level query helper (no tenant context)
// ---------------------------------------------------------------------------

/**
 * Executes a query without tenant context.
 *
 * ONLY use for platform-level tables:
 *   - jwt_rotation_keys
 *   - webauthn_credentials (during authentication before a JWT exists)
 *   - users (during login before a JWT is issued)
 *
 * Do NOT use for any tenant-owned data.
 */
export async function queryNoTenant<T extends object = Record<string, unknown>>(
  sql: string,
  params: unknown[]
): Promise<import('pg').QueryResult<T>> {
  return getPool().query<T>(sql, params);
}

// ---------------------------------------------------------------------------
// Health check helper (used by GET /health)
// ---------------------------------------------------------------------------

/**
 * Returns true if the pool can successfully ping the database.
 * Used only for the health endpoint — not for application queries.
 */
export async function checkDbConnection(): Promise<boolean> {
  try {
    await getPool().query('SELECT 1');
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------

/**
 * Drains in-flight queries and closes all pool connections.
 * Call during SIGTERM/SIGINT handling.
 */
export async function closePool(): Promise<void> {
  if (pool !== null) {
    await pool.end();
    pool = null;
  }
}
