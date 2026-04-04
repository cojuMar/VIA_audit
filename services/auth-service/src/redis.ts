/**
 * Redis client singleton (ioredis).
 *
 * Using a module-level singleton avoids spawning multiple connections.
 * All modules should import `getRedis()` rather than creating their
 * own client instances.
 */

import Redis from 'ioredis';
import { config } from './config.js';

let client: Redis | null = null;

export function getRedis(): Redis {
  if (client !== null) return client;

  client = new Redis(config.redis.url, {
    // Automatically reconnect up to 10 times with exponential back-off.
    retryStrategy(times) {
      if (times > 10) return null; // stop retrying
      return Math.min(times * 100, 3000);
    },
    lazyConnect: false,
    enableOfflineQueue: true,
    maxRetriesPerRequest: 3,
  });

  client.on('error', (err: Error) => {
    process.stderr.write(`[redis] Client error: ${err.message}\n`);
  });

  client.on('connect', () => {
    process.stderr.write('[redis] Connected\n');
  });

  return client;
}

/**
 * Checks that Redis responds to PING.
 * Used by the health endpoint only.
 */
export async function checkRedisConnection(): Promise<boolean> {
  try {
    const pong = await getRedis().ping();
    return pong === 'PONG';
  } catch {
    return false;
  }
}

/**
 * Gracefully close the Redis connection.
 * Call during SIGTERM/SIGINT handling.
 */
export async function closeRedis(): Promise<void> {
  if (client !== null) {
    await client.quit();
    client = null;
  }
}
