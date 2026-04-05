import type { ComplianceFramework, FrameworkControl, ComplianceScore, GapItem, CalendarEvent, CrosswalkPair } from './types'

const BASE = '/api'

/** Throw a descriptive error for non-2xx responses so TanStack Query
 *  enters its error state instead of resolving the error JSON as data.
 *  This prevents "c.map is not a function" crashes when the server
 *  returns a 400/500 error object instead of the expected array. */
async function checkedJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.error) message += `: ${body.error}`
      else if (body?.detail) message += `: ${body.detail}`
    } catch {
      // ignore json parse failure on error body
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const api = {
  // Framework catalog
  getFrameworks: (): Promise<ComplianceFramework[]> =>
    fetch(`${BASE}/frameworks`).then(r => checkedJson<ComplianceFramework[]>(r)),

  getFramework: (slug: string): Promise<ComplianceFramework & { controls: FrameworkControl[] }> =>
    fetch(`${BASE}/frameworks/${slug}`).then(r => checkedJson<ComplianceFramework & { controls: FrameworkControl[] }>(r)),

  // Tenant framework activation
  getTenantFrameworks: (tenantId: string): Promise<ComplianceFramework[]> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks`, { headers: { 'X-Tenant-ID': tenantId } })
      .then(r => checkedJson<ComplianceFramework[]>(r)),

  activateFramework: (tenantId: string, slug: string): Promise<void> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks/${slug}/activate`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => checkedJson<void>(r)),

  deactivateFramework: (tenantId: string, slug: string): Promise<void> =>
    fetch(`${BASE}/tenants/${tenantId}/frameworks/${slug}`, {
      method: 'DELETE',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => checkedJson<void>(r)),

  // Scores
  getScores: (tenantId: string): Promise<ComplianceScore[]> =>
    fetch(`${BASE}/tenants/${tenantId}/score`, { headers: { 'X-Tenant-ID': tenantId } })
      .then(r => checkedJson<ComplianceScore[]>(r)),

  refreshScores: (tenantId: string): Promise<ComplianceScore[]> =>
    fetch(`${BASE}/tenants/${tenantId}/score/refresh`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId },
    }).then(r => checkedJson<ComplianceScore[]>(r)),

  // Gaps
  getGaps: (tenantId: string): Promise<GapItem[]> =>
    fetch(`${BASE}/tenants/${tenantId}/gaps`, { headers: { 'X-Tenant-ID': tenantId } })
      .then(r => checkedJson<GapItem[]>(r)),

  // Calendar
  getCalendar: (tenantId: string): Promise<CalendarEvent[]> =>
    fetch(`${BASE}/tenants/${tenantId}/calendar`, { headers: { 'X-Tenant-ID': tenantId } })
      .then(r => checkedJson<CalendarEvent[]>(r)),

  // Crosswalk
  getCrosswalk: (tenantId: string): Promise<{ pairs: CrosswalkPair[] }> =>
    fetch(`${BASE}/tenants/${tenantId}/crosswalk`, { headers: { 'X-Tenant-ID': tenantId } })
      .then(r => checkedJson<{ pairs: CrosswalkPair[] }>(r)),
}
