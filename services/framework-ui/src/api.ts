import type { ComplianceFramework, FrameworkControl, ComplianceScore, GapItem, CalendarEvent, CrosswalkPair } from './types'

const BASE = '/api'

export const api = {
  // Framework catalog
  getFrameworks: (): Promise<ComplianceFramework[]> =>
    fetch(`${BASE}/frameworks`).then(r => r.json()),

  getFramework: (slug: string): Promise<ComplianceFramework & { controls: FrameworkControl[] }> =>
    fetch(`${BASE}/frameworks/${slug}`).then(r => r.json()),

  // Tenant framework activation
  getTenantFrameworks: (tenantId: string): Promise<ComplianceFramework[]> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks`, { headers: { 'X-Tenant-ID': tenantId } }).then(r => r.json()),

  activateFramework: (tenantId: string, slug: string): Promise<void> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks/${slug}/activate`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => r.json()),

  deactivateFramework: (tenantId: string, slug: string): Promise<void> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks/${slug}`, {
      method: 'DELETE',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => r.json()),

  // Scores
  getScores: (tenantId: string): Promise<ComplianceScore[]> =>
    fetch(`${BASE}/tenants/${tenantId}/score`, { headers: { 'X-Tenant-ID': tenantId } }).then(r => r.json()),

  refreshScores: (tenantId: string): Promise<ComplianceScore[]> =>
    fetch(`${BASE}/tenants/${tenantId}/score/refresh`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => r.json()),

  // Gaps
  getGaps: (tenantId: string): Promise<GapItem[]> =>
    fetch(`${BASE}/tenants/${tenantId}/gaps`, { headers: { 'X-Tenant-ID': tenantId } }).then(r => r.json()),

  // Calendar
  getCalendar: (tenantId: string): Promise<CalendarEvent[]> =>
    fetch(`${BASE}/tenants/${tenantId}/calendar`, { headers: { 'X-Tenant-ID': tenantId } }).then(r => r.json()),

  // Crosswalk
  getCrosswalk: (tenantId: string): Promise<{ pairs: CrosswalkPair[] }> =>
    fetch(`${BASE}/tenants/${tenantId}/crosswalk`, { headers: { 'X-Tenant-ID': tenantId } }).then(r => r.json()),
}
