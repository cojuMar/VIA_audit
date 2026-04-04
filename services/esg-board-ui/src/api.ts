import axios from 'axios';

export function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get('tenantId') ?? localStorage.getItem('aegis_tenant_id') ?? '';
}

const api = axios.create({
  baseURL: '/api',
});

api.interceptors.request.use((config) => {
  const tenantId = getTenantId();
  if (tenantId) {
    config.headers['X-Tenant-ID'] = tenantId;
  }
  return config;
});

// ─── ESG ─────────────────────────────────────────────────────────────────────

export const fetchFrameworks = (category?: string) =>
  api.get('/esg/frameworks', { params: category ? { category } : undefined }).then((r) => r.data);

export const fetchMetricDefinitions = (params?: object) =>
  api.get('/esg/metric-definitions', { params }).then((r) => r.data);

export const submitDisclosure = (data: object) =>
  api.post('/esg/disclosures', data).then((r) => r.data);

export const fetchDisclosures = (params?: object) =>
  api.get('/esg/disclosures', { params }).then((r) => r.data);

export const fetchScorecard = (reporting_period: string) =>
  api.get('/esg/scorecard', { params: { reporting_period } }).then((r) => r.data);

export const fetchTrendData = (metric_id: string, periods?: number) =>
  api.get('/esg/trend', { params: { metric_id, periods } }).then((r) => r.data);

export const upsertTarget = (data: object) =>
  api.post('/esg/targets', data).then((r) => r.data);

export const fetchTargets = (params?: object) =>
  api.get('/esg/targets', { params }).then((r) => r.data);

export const fetchTargetProgress = (target_year: number) =>
  api.get('/esg/targets/progress', { params: { target_year } }).then((r) => r.data);

// ─── Board ────────────────────────────────────────────────────────────────────

export const createCommittee = (data: object) =>
  api.post('/board/committees', data).then((r) => r.data);

export const fetchCommittees = (active_only?: boolean) =>
  api.get('/board/committees', { params: active_only !== undefined ? { active_only } : undefined }).then((r) => r.data);

export const updateCommittee = (id: string, data: object) =>
  api.put(`/board/committees/${id}`, data).then((r) => r.data);

export const createMeeting = (data: object) =>
  api.post('/board/meetings', data).then((r) => r.data);

export const fetchMeetings = (params?: object) =>
  api.get('/board/meetings', { params }).then((r) => r.data);

export const fetchMeeting = (id: string) =>
  api.get(`/board/meetings/${id}`).then((r) => r.data);

export const updateMeeting = (id: string, data: object) =>
  api.put(`/board/meetings/${id}`, data).then((r) => r.data);

export const completeMeeting = (id: string, data: object) =>
  api.post(`/board/meetings/${id}/complete`, data).then((r) => r.data);

export const approveMinutes = (id: string) =>
  api.post(`/board/meetings/${id}/approve-minutes`).then((r) => r.data);

export const fetchBoardCalendar = (year: number) =>
  api.get('/board/calendar', { params: { year } }).then((r) => r.data);

export const addAgendaItem = (data: object) =>
  api.post('/board/agenda-items', data).then((r) => r.data);

export const updateAgendaItem = (id: string, data: object) =>
  api.put(`/board/agenda-items/${id}`, data).then((r) => r.data);

// ─── Packages ─────────────────────────────────────────────────────────────────

export const createPackage = (data: object) =>
  api.post('/board/packages', data).then((r) => r.data);

export const fetchPackages = (params?: object) =>
  api.get('/board/packages', { params }).then((r) => r.data);

export const fetchPackage = (id: string) =>
  api.get(`/board/packages/${id}`).then((r) => r.data);

export const buildESGPackage = (data: object) =>
  api.post('/board/packages/build/esg', data).then((r) => r.data);

export const buildAuditCommitteePackage = (data: object) =>
  api.post('/board/packages/build/audit-committee', data).then((r) => r.data);

// ─── AI ───────────────────────────────────────────────────────────────────────

export const aiESGNarrative = (reporting_period: string) =>
  api.post('/ai/esg-narrative', { reporting_period }).then((r) => r.data);

export const aiBoardPackSummary = (package_id: string) =>
  api.post('/ai/board-pack-summary', { package_id }).then((r) => r.data);

export const aiMaterialityAssessment = (data: object) =>
  api.post('/ai/materiality-assessment', data).then((r) => r.data);

export const aiSuggestTargets = (reporting_period: string) =>
  api.post('/ai/suggest-targets', { reporting_period }).then((r) => r.data);
