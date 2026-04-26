/**
 * Build a URL to a sibling module UI.
 *
 * In dev, modules are reachable directly on `http://localhost:<port>` (the
 * Vite dev server for each UI). In prod they're served from
 * `${VITE_MODULE_BASE_URL}/<module-id>` (a single fronted host with path
 * routing — typically nginx in front of all UIs).
 *
 * This replaces the 6+ hardcoded `http://localhost:${port}` strings that
 * baked dev URLs into the prod bundle.
 */
import type { Module } from './modules';

const RAW_BASE = (import.meta as ImportMeta & {
  env?: { VITE_MODULE_BASE_URL?: string };
}).env?.VITE_MODULE_BASE_URL;

const BASE = (RAW_BASE ?? '').replace(/\/+$/, '');

/** Path used when routing through the prod gateway (e.g. nginx). */
const MODULE_PATH: Record<string, string> = {
  framework:        '/framework',
  tprm:             '/tprm',
  'trust-portal':   '/trust-portal',
  monitoring:       '/monitoring',
  people:           '/people',
  pbc:              '/pbc',
  integration:      '/integration',
  'ai-agent':       '/ai-agent',
  risk:             '/risk',
  'audit-planning': '/audit-planning',
  esg:              '/esg',
  mobile:           '/mobile',
};

export function moduleUrl(mod: Pick<Module, 'id' | 'port'>, qs?: string): string {
  const query = qs ? (qs.startsWith('?') ? qs : `?${qs}`) : '';
  if (BASE) {
    const path = MODULE_PATH[mod.id] ?? `/${mod.id}`;
    return `${BASE}${path}${query}`;
  }
  // Dev fallback — direct to the per-module Vite dev server.
  return `http://localhost:${mod.port}/${query}`;
}

/** Used by useModuleHealth to ping each module without hard-coding localhost. */
export function moduleHealthUrl(mod: Pick<Module, 'id' | 'port'>): string {
  return moduleUrl(mod);
}

/** Convenience for the "Open Risk Dashboard" CTA — looks up the risk port. */
export function moduleUrlById(
  modules: Module[],
  id: string,
  qs?: string,
): string | null {
  const mod = modules.find((m) => m.id === id);
  return mod ? moduleUrl(mod, qs) : null;
}
