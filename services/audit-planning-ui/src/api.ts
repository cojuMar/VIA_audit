import axios from 'axios';

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get('tenantId') || localStorage.getItem('via_tenant_id') || 'demo-tenant';
}

const api = axios.create({ baseURL: '/api' });

api.interceptors.request.use((cfg) => {
  cfg.headers['X-Tenant-ID'] = getTenantId();
  return cfg;
});

// Entity / Universe
export const fetchEntityTypes = () => api.get('/entity-types').then((r) => r.data);
export const fetchEntities = (params?: object) => api.get('/entities', { params }).then((r) => r.data);
export const createEntity = (data: object) => api.post('/entities', data).then((r) => r.data);
export const updateEntity = (id: string, data: object) => api.put(`/entities/${id}`, data).then((r) => r.data);
export const fetchUniverseCoverage = (plan_year: number) =>
  api.get('/universe/coverage', { params: { plan_year } }).then((r) => r.data);

// Plans
export const fetchPlans = () => api.get('/plans').then((r) => r.data);
export const createPlan = (data: object) => api.post('/plans', data).then((r) => r.data);
export const fetchPlan = (id: string) => api.get(`/plans/${id}`).then((r) => r.data);
export const fetchPlanSummary = (id: string) => api.get(`/plans/${id}/summary`).then((r) => r.data);
export const approvePlan = (id: string, approved_by: string) =>
  api.post(`/plans/${id}/approve`, { approved_by }).then((r) => r.data);
export const autoPopulatePlan = (id: string, risk_threshold = 7.0) =>
  api.post(`/plans/${id}/auto-populate`, { risk_threshold }).then((r) => r.data);

// Plan items
export const createPlanItem = (data: object) => api.post('/plan-items', data).then((r) => r.data);
export const updatePlanItem = (id: string, data: object) =>
  api.put(`/plan-items/${id}`, data).then((r) => r.data);

// Engagements
export const fetchEngagements = (params?: object) => api.get('/engagements', { params }).then((r) => r.data);
export const createEngagement = (data: object) => api.post('/engagements', data).then((r) => r.data);
export const fetchEngagement = (id: string) => api.get(`/engagements/${id}`).then((r) => r.data);
export const updateEngagement = (id: string, data: object) =>
  api.put(`/engagements/${id}`, data).then((r) => r.data);
export const transitionEngagement = (id: string, new_status: string, notes?: string) =>
  api.post(`/engagements/${id}/transition`, { new_status, notes }).then((r) => r.data);
export const fetchGantt = (plan_id?: string) =>
  api.get('/gantt', { params: plan_id ? { plan_id } : {} }).then((r) => r.data);

// Time tracking
export const logHours = (data: object) => api.post('/time-entries', data).then((r) => r.data);
export const fetchTimeEntries = (params?: object) =>
  api.get('/time-entries', { params }).then((r) => r.data);
export const fetchEngagementHours = (id: string) =>
  api.get(`/engagements/${id}/hours`).then((r) => r.data);
export const fetchUtilization = (start_date: string, end_date: string) =>
  api.get('/utilization', { params: { start_date, end_date } }).then((r) => r.data);
export const fetchBudgetStatus = (plan_id: string) =>
  api.get(`/plans/${plan_id}/budget-status`).then((r) => r.data);

// Milestones
export const createMilestone = (data: object) => api.post('/milestones', data).then((r) => r.data);
export const completeMilestone = (id: string, completed_date?: string) =>
  api.post(`/milestones/${id}/complete`, { completed_date }).then((r) => r.data);
export const fetchEngagementMilestones = (eng_id: string) =>
  api.get(`/engagements/${eng_id}/milestones`).then((r) => r.data);
export const seedMilestones = (eng_id: string) =>
  api.post(`/engagements/${eng_id}/milestones/seed`).then((r) => r.data);
export const fetchOverdueMilestones = () => api.get('/milestones/overdue').then((r) => r.data);

// Resources
export const assignResource = (data: object) => api.post('/resources', data).then((r) => r.data);
export const fetchEngagementResources = (eng_id: string) =>
  api.get(`/engagements/${eng_id}/resources`).then((r) => r.data);
export const fetchAuditorSchedule = (params: object) =>
  api.get('/resources/schedule', { params }).then((r) => r.data);
export const fetchTeamAvailability = (params: object) =>
  api.get('/resources/availability', { params }).then((r) => r.data);

// AI
export const aiSuggestScope = (entity_id: string) =>
  api.post('/ai/suggest-scope', { entity_id, include_risk_context: true }).then((r) => r.data);
export const aiGenerateProgram = (engagement_id: string) =>
  api.post('/ai/generate-program', { engagement_id }).then((r) => r.data);
export const aiPrioritizeUniverse = (limit = 20) =>
  api.post('/ai/prioritize-universe', { limit }).then((r) => r.data);
