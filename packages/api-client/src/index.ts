/**
 * @via/api-client — shared axios factory for every VIA UI.
 *
 * Replaces the 13 hand-rolled `src/api.ts` files. One client, one tenant
 * header pattern (`X-Tenant-ID`, canonical casing), one error pipeline.
 *
 * Usage:
 *
 *     import { createApiClient, setTenantId } from '@via/api-client';
 *
 *     setTenantId('tenant-uuid-...');
 *     const api = createApiClient();
 *     const { data } = await api.get('/risks');
 *
 * Wire `onError` to your toast hook to surface 5xx / network failures
 * uniformly across every module.
 */
import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
} from 'axios';

// Module-scoped tenant id; set once at app boot from auth context.
let _tenantId = 'default';

/** Set the tenant id sent in `X-Tenant-ID` on every subsequent request. */
export function setTenantId(id: string): void {
  _tenantId = id;
}

/** Read the current tenant id (mostly useful in tests). */
export function getTenantId(): string {
  return _tenantId;
}

export interface ApiClientOptions {
  /** Defaults to '/api'. Override per-module if a service is fronted differently. */
  baseURL?: string;
  /** Header casing — canonical is 'X-Tenant-ID'. Don't override unless you must. */
  tenantHeader?: string;
  /** Surface 5xx + network errors. Wire to a toast hook for uniform UX. */
  onError?: (err: AxiosError) => void;
  /** Extra axios config merged in. */
  axiosConfig?: AxiosRequestConfig;
}

/**
 * Build an axios instance with the canonical interceptors:
 *   - Request: inject `X-Tenant-ID`.
 *   - Response: invoke `onError` for 5xx / network failures, then re-throw.
 */
export function createApiClient(opts: ApiClientOptions = {}): AxiosInstance {
  const {
    baseURL = '/api',
    tenantHeader = 'X-Tenant-ID',
    onError,
    axiosConfig = {},
  } = opts;

  const client = axios.create({ baseURL, ...axiosConfig });

  client.interceptors.request.use((config) => {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)[tenantHeader] = _tenantId;
    return config;
  });

  client.interceptors.response.use(
    (resp) => resp,
    (err: AxiosError) => {
      // Surface server-side / network problems but never swallow them.
      const status = err.response?.status;
      if (!status || status >= 500) {
        try {
          onError?.(err);
        } catch {
          /* a broken error handler must never mask the original error */
        }
      }
      return Promise.reject(err);
    },
  );

  return client;
}

/** Convenience type re-export so consumers don't need to depend on axios directly. */
export type { AxiosError, AxiosInstance, AxiosRequestConfig };
