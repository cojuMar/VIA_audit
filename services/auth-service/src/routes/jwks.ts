/**
 * JWKS endpoint — /.well-known/jwks.json
 *
 * Publishes the platform's public signing keys so downstream services
 * (pam-broker, tenant-registry, ML pipeline) can independently verify JWTs
 * without calling back to auth-service on every request.
 *
 * Security properties:
 *   - Never exposes private key material (enforced by node-jose JWKS export)
 *   - Sets a 1-hour Cache-Control to allow CDN/proxy caching
 *   - No authentication required (public endpoint by design)
 *   - Returns only the currently active key(s); retired keys are excluded
 */

import { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { getJWKS } from '../jwt.js';

export async function jwksRoutes(fastify: FastifyInstance): Promise<void> {
  /**
   * GET /.well-known/jwks.json
   *
   * Returns the JSON Web Key Set containing the platform's RSA public key(s).
   * Downstream services should cache this response for the duration of the
   * Cache-Control max-age and refresh when a token's `kid` is not found.
   */
  fastify.get(
    '/.well-known/jwks.json',
    {
      schema: {
        response: {
          200: {
            type: 'object',
            properties: {
              keys: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: {
                    kty: { type: 'string' },
                    use: { type: 'string' },
                    alg: { type: 'string' },
                    kid: { type: 'string' },
                    n:   { type: 'string' },
                    e:   { type: 'string' },
                  },
                  required: ['kty', 'use', 'alg', 'kid', 'n', 'e'],
                  // Explicitly forbid private key fields in the schema.
                  // Fastify's response serialiser will strip unknown fields,
                  // but this documents the contract.
                  additionalProperties: false,
                },
              },
            },
            required: ['keys'],
          },
        },
      },
    },
    async (_request: FastifyRequest, reply: FastifyReply) => {
      const jwks = await getJWKS();

      reply
        .header('Cache-Control', 'public, max-age=3600, stale-while-revalidate=300')
        .header('Content-Type', 'application/json')
        .send(jwks);
    }
  );
}
