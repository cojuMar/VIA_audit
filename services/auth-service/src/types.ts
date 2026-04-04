/**
 * Shared domain types for the Aegis auth-service.
 * These types flow through JWT claims, DB models, and route handlers.
 */

// Re-export the AuthenticatorTransport type used by WebAuthn credentials.
// @simplewebauthn/server re-exports the W3C type from the TypeScript DOM lib.
export type { AuthenticatorTransport } from '@simplewebauthn/types';

// ---------------------------------------------------------------------------
// Enumerations (kept as union types for type safety without runtime overhead)
// ---------------------------------------------------------------------------

/** Deployment model for a tenant. */
export type TenantTier = 'smb_pool' | 'enterprise_silo';

/** RBAC roles carried inside JWTs and enforced by route preHandlers. */
export type UserRole =
  | 'admin'
  | 'auditor'
  | 'firm_partner'
  | 'smb_owner'
  | 'readonly';

/** Categories of privileged resources that can be requested via break-glass. */
export type ResourceType =
  | 'database_readonly'
  | 'database_infra'
  | 'api_readonly'
  | 'break_glass';

// ---------------------------------------------------------------------------
// JWT / Token models
// ---------------------------------------------------------------------------

/**
 * Claims embedded in every issued JWT.
 * Must stay serialisable — no class instances.
 */
export interface TenantClaims {
  /** user_id (UUID v4) */
  sub: string;
  /** Tenant UUID v4 */
  tenant_id: string;
  /** RBAC role */
  role: UserRole;
  /** Only present for firm_partner tokens — list of allowed client tenant IDs */
  client_access?: string[];
  /** Issued-at (Unix epoch seconds) */
  iat: number;
  /** Expiry (Unix epoch seconds) */
  exp: number;
  /** Unique token ID — used for revocation checks */
  jti: string;
}

// ---------------------------------------------------------------------------
// User model
// ---------------------------------------------------------------------------

export interface User {
  userId: string;
  tenantId: string;
  email: string;
  displayName: string;
  role: UserRole;
  isActive: boolean;
}

// ---------------------------------------------------------------------------
// WebAuthn / FIDO2 models
// ---------------------------------------------------------------------------

import type { AuthenticatorTransport as _AT } from '@simplewebauthn/types';

export interface WebAuthnCredential {
  credentialId: string;
  userId: string;
  tenantId: string;
  /** DER-encoded COSE public key stored as a Buffer */
  publicKey: Buffer;
  /** Monotonically increasing counter — detects cloned authenticators */
  signCount: number;
  transports?: _AT[];
  deviceName?: string;
}

// ---------------------------------------------------------------------------
// Break-glass / JIT access models
// ---------------------------------------------------------------------------

export interface AccessRequest {
  requestId: string;
  requestingUserId: string;
  tenantId: string;
  resourceType: ResourceType;
  justification: string;
  itsmTicketId?: string;
  requestedDurationSeconds: number;
}
