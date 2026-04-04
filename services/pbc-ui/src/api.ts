import axios from 'axios';
import type {
  AuditEngagement,
  PBCRequestList,
  PBCRequest,
  PBCFulfillment,
  AuditIssue,
  IssueResponse,
  WorkpaperTemplate,
  Workpaper,
  WorkpaperSection,
  EngagementDashboard,
} from './types';

const http = axios.create({ baseURL: '/api' });

function tenantHeaders(tenantId: string) {
  return { headers: { 'x-tenant-id': tenantId } };
}

// ── Engagements ──────────────────────────────────────────────────────────────

export async function listEngagements(tenantId: string): Promise<AuditEngagement[]> {
  const res = await http.get('/engagements', tenantHeaders(tenantId));
  return res.data;
}

export async function getEngagement(tenantId: string, id: string): Promise<AuditEngagement> {
  const res = await http.get(`/engagements/${id}`, tenantHeaders(tenantId));
  return res.data;
}

export interface EngagementCreate {
  engagement_name: string;
  engagement_type: string;
  fiscal_year?: number | null;
  period_start?: string | null;
  period_end?: string | null;
  lead_auditor?: string | null;
  description?: string | null;
}

export async function createEngagement(tenantId: string, data: EngagementCreate): Promise<AuditEngagement> {
  const res = await http.post('/engagements', data, tenantHeaders(tenantId));
  return res.data;
}

export async function updateEngagementStatus(tenantId: string, id: string, status: string): Promise<AuditEngagement> {
  const res = await http.patch(`/engagements/${id}/status`, { status }, tenantHeaders(tenantId));
  return res.data;
}

export async function getEngagementDashboard(tenantId: string, id: string): Promise<EngagementDashboard> {
  const res = await http.get(`/engagements/${id}/dashboard`, tenantHeaders(tenantId));
  return res.data;
}

// ── PBC Lists ─────────────────────────────────────────────────────────────────

export async function listPBCLists(tenantId: string, engagementId: string): Promise<PBCRequestList[]> {
  const res = await http.get(`/engagements/${engagementId}/pbc-lists`, tenantHeaders(tenantId));
  return res.data;
}

export interface PBCListCreate {
  list_name: string;
  description?: string | null;
  due_date?: string | null;
}

export async function createPBCList(tenantId: string, engagementId: string, data: PBCListCreate): Promise<PBCRequestList> {
  const res = await http.post(`/engagements/${engagementId}/pbc-lists`, data, tenantHeaders(tenantId));
  return res.data;
}

// ── PBC Requests ──────────────────────────────────────────────────────────────

export async function listPBCRequests(tenantId: string, listId: string): Promise<PBCRequest[]> {
  const res = await http.get(`/pbc-lists/${listId}/requests`, tenantHeaders(tenantId));
  return res.data;
}

export interface PBCRequestCreate {
  title: string;
  description: string;
  category?: string | null;
  priority?: 'high' | 'medium' | 'low';
  assigned_to?: string | null;
  due_date?: string | null;
  framework_control_ref?: string | null;
}

export async function createPBCRequest(tenantId: string, listId: string, data: PBCRequestCreate): Promise<PBCRequest> {
  const res = await http.post(`/pbc-lists/${listId}/requests`, data, tenantHeaders(tenantId));
  return res.data;
}

export async function bulkCreatePBCRequests(tenantId: string, listId: string, requests: PBCRequestCreate[]): Promise<PBCRequest[]> {
  const res = await http.post(`/pbc-lists/${listId}/requests/bulk`, { requests }, tenantHeaders(tenantId));
  return res.data;
}

export async function updatePBCRequestStatus(tenantId: string, requestId: string, status: string): Promise<PBCRequest> {
  const res = await http.patch(`/pbc-requests/${requestId}/status`, { status }, tenantHeaders(tenantId));
  return res.data;
}

// ── PBC Fulfillments ──────────────────────────────────────────────────────────

export interface FulfillmentCreate {
  submitted_by: string;
  response_text?: string | null;
  submission_notes?: string | null;
  file?: File | null;
}

export async function fulfillPBCRequest(tenantId: string, requestId: string, data: FulfillmentCreate): Promise<PBCFulfillment> {
  const formData = new FormData();
  formData.append('submitted_by', data.submitted_by);
  if (data.response_text) formData.append('response_text', data.response_text);
  if (data.submission_notes) formData.append('submission_notes', data.submission_notes);
  if (data.file) formData.append('file', data.file);

  const res = await http.post(`/pbc-requests/${requestId}/fulfill`, formData, {
    headers: { 'x-tenant-id': tenantId, 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function exportPBCList(tenantId: string, listId: string): Promise<unknown> {
  const res = await http.get(`/pbc-lists/${listId}/export`, tenantHeaders(tenantId));
  return res.data;
}

// ── Issues ────────────────────────────────────────────────────────────────────

export async function listIssues(tenantId: string, engagementId: string): Promise<AuditIssue[]> {
  const res = await http.get(`/engagements/${engagementId}/issues`, tenantHeaders(tenantId));
  return res.data;
}

export async function getIssue(tenantId: string, issueId: string): Promise<AuditIssue> {
  const res = await http.get(`/issues/${issueId}`, tenantHeaders(tenantId));
  return res.data;
}

export interface IssueCreate {
  title: string;
  description: string;
  finding_type: string;
  severity: string;
  control_reference?: string | null;
  framework_references?: string[];
  root_cause?: string | null;
  management_owner?: string | null;
  target_remediation_date?: string | null;
}

export async function createIssue(tenantId: string, engagementId: string, data: IssueCreate): Promise<AuditIssue> {
  const res = await http.post(`/engagements/${engagementId}/issues`, data, tenantHeaders(tenantId));
  return res.data;
}

export interface IssueResponseCreate {
  response_type: string;
  response_text: string;
  submitted_by: string;
  new_status?: string | null;
  file?: File | null;
}

export async function addIssueResponse(tenantId: string, issueId: string, data: IssueResponseCreate): Promise<IssueResponse> {
  const formData = new FormData();
  formData.append('response_type', data.response_type);
  formData.append('response_text', data.response_text);
  formData.append('submitted_by', data.submitted_by);
  if (data.new_status) formData.append('new_status', data.new_status);
  if (data.file) formData.append('file', data.file);

  const res = await http.post(`/issues/${issueId}/responses`, formData, {
    headers: { 'x-tenant-id': tenantId, 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function exportIssueRegister(tenantId: string, engagementId: string): Promise<unknown> {
  const res = await http.get(`/engagements/${engagementId}/issues/export`, tenantHeaders(tenantId));
  return res.data;
}

// ── Workpaper Templates ───────────────────────────────────────────────────────

export async function listTemplates(tenantId: string): Promise<WorkpaperTemplate[]> {
  const res = await http.get('/workpaper-templates', tenantHeaders(tenantId));
  return res.data;
}

// ── Workpapers ────────────────────────────────────────────────────────────────

export async function listWorkpapers(tenantId: string, engagementId: string): Promise<Workpaper[]> {
  const res = await http.get(`/engagements/${engagementId}/workpapers`, tenantHeaders(tenantId));
  return res.data;
}

export async function getWorkpaper(tenantId: string, wpId: string): Promise<Workpaper> {
  const res = await http.get(`/workpapers/${wpId}`, tenantHeaders(tenantId));
  return res.data;
}

export interface WorkpaperCreate {
  title: string;
  template_id?: string | null;
  wp_reference?: string | null;
  workpaper_type?: string;
  preparer?: string | null;
  reviewer?: string | null;
}

export async function createWorkpaper(tenantId: string, engagementId: string, data: WorkpaperCreate): Promise<Workpaper> {
  const res = await http.post(`/engagements/${engagementId}/workpapers`, data, tenantHeaders(tenantId));
  return res.data;
}

export async function updateWorkpaperStatus(tenantId: string, wpId: string, status: string): Promise<Workpaper> {
  const res = await http.patch(`/workpapers/${wpId}/status`, { status }, tenantHeaders(tenantId));
  return res.data;
}

export async function updateWorkpaperSection(
  tenantId: string,
  wpId: string,
  sectionId: string,
  data: { content?: Record<string, unknown>; is_complete?: boolean }
): Promise<WorkpaperSection> {
  const res = await http.put(`/workpapers/${wpId}/sections/${sectionId}`, data, tenantHeaders(tenantId));
  return res.data;
}

export async function exportWorkpaper(tenantId: string, wpId: string): Promise<unknown> {
  const res = await http.get(`/workpapers/${wpId}/export`, tenantHeaders(tenantId));
  return res.data;
}

// ── AI Summary ────────────────────────────────────────────────────────────────

export async function generateAISummary(tenantId: string, engagementId: string): Promise<{ summary: string }> {
  const res = await http.post(`/engagements/${engagementId}/ai-summary`, {}, tenantHeaders(tenantId));
  return res.data;
}
