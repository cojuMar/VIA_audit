import type { WhiteLabelConfig, HealthScore, Gauge, EvidenceRecord, AuditHubItem, ClientSummary, AnomalyFeedItem } from './types'

const BASE = '/api'

function headers(): Record<string, string> {
  const token = sessionStorage.getItem('aegis_token') || 'dev-token'
  const tenantId = sessionStorage.getItem('aegis_tenant_id') || ''
  const userId = sessionStorage.getItem('aegis_user_id') || ''
  return {
    'Authorization': `Bearer ${token}`,
    'X-Tenant-ID': tenantId,
    'X-User-ID': userId,
    'Content-Type': 'application/json',
  }
}

async function get<T>(path: string, params?: Record<string, string | number | boolean>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  }
  const res = await fetch(url.toString(), { headers: headers() })
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

export const api = {
  getWhiteLabel: () => get<WhiteLabelConfig>('/config/white-label'),
  getDashboardConfig: () => get<{ mode: string; default_framework: string }>('/config/dashboard'),

  // Firm Mode
  getFirmClients: () => get<ClientSummary[]>('/firm/clients'),
  getPortfolio: (framework: string) => get<{ clients: ClientSummary[]; avg_health_score: number | null; clients_at_risk: number; critical_issues_total: number }>('/firm/portfolio', { framework }),
  getRiskHeatmap: (framework: string, days: number) => get<{ data: Array<{ tenant_id: string; label: string; categories: Array<{ category: string; avg_risk: number; count: number }> }> }>('/firm/risk-heatmap', { framework, days }),

  // SMB Mode
  getEvidenceLocker: (params: { days?: number; limit?: number; offset?: number; event_type?: string }) =>
    get<{ total: number; records: EvidenceRecord[] }>('/smb/evidence-locker', params as Record<string, string | number>),
  getAuditHub: (framework?: string) => get<AuditHubItem[]>('/smb/audit-hub', framework ? { framework } : undefined),

  // Autonomous Mode
  getHealthScore: (framework: string) => get<HealthScore>('/autonomous/health-score', { framework }),
  getHealthTrend: (framework: string, days: number) => get<{ data: HealthScore[] }>('/autonomous/health-trend', { framework, days }),
  getGauges: (framework: string) => get<{ gauges: Gauge[] }>('/autonomous/gauges', { framework }),
  getAnomalyFeed: (limit?: number) => get<AnomalyFeedItem[]>('/autonomous/anomaly-feed', limit ? { limit } : undefined),
}
