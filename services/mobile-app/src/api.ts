import axios from 'axios';

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get('tenantId') ?? localStorage.getItem('aegis_tenant_id') ?? '';
}

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const tenantId = getTenantId();
  if (tenantId) {
    config.headers['X-Tenant-ID'] = tenantId;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('Unauthorized — check tenant ID');
    }
    return Promise.reject(error);
  }
);

export default api;

// Templates
export const fetchTemplates = () => api.get('/templates').then((r) => r.data);
export const fetchTemplate = (id: string) => api.get(`/templates/${id}`).then((r) => r.data);

// Assignments
export const fetchAssignments = (params?: object) =>
  api.get('/assignments', { params }).then((r) => r.data);

// Audits
export const createAudit = (data: object) => api.post('/audits', data).then((r) => r.data);
export const fetchAudits = (params?: object) => api.get('/audits', { params }).then((r) => r.data);
export const fetchAudit = (id: string) => api.get(`/audits/${id}`).then((r) => r.data);
export const submitAudit = (id: string, data?: object) =>
  api.post(`/audits/${id}/submit`, data ?? {}).then((r) => r.data);
export const fetchAuditSummary = (id: string) =>
  api.get(`/audits/${id}/summary`).then((r) => r.data);

// Responses
export const addResponse = (audit_id: string, data: object) =>
  api.post(`/audits/${audit_id}/responses`, data).then((r) => r.data);
export const addResponsesBatch = (audit_id: string, responses: object[]) =>
  api.post(`/audits/${audit_id}/responses/batch`, { responses }).then((r) => r.data);

// Photos
export const uploadPhoto = (audit_id: string, formData: FormData) =>
  api
    .post(`/audits/${audit_id}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);
export const fetchPhotos = (audit_id: string) =>
  api.get(`/audits/${audit_id}/photos`).then((r) => r.data);

// Sync
export const syncUpload = (data: object) => api.post('/sync/upload', data).then((r) => r.data);
export const syncDownload = (params: object) =>
  api.get('/sync/download', { params }).then((r) => r.data);

// AI
export const aiGenerateFindingsReport = (audit_id: string) =>
  api.post('/ai/findings-report', { audit_id }).then((r) => r.data);
export const aiPrioritizeFindings = (audit_id: string) =>
  api.post('/ai/prioritize-findings', { audit_id }).then((r) => r.data);
