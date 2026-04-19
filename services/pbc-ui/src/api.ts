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
  const res = await http.get(`/pbc/lists?engagement_id=${engagementId}`, tenantHeaders(tenantId));
  return res.data;
}

export interface PBCListCreate {
  list_name: string;
  description?: string | null;
  due_date?: string | null;
}

export async function createPBCList(tenantId: string, engagementId: string, data: PBCListCreate): Promise<PBCRequestList> {
  const res = await http.post(`/pbc/lists`, { ...data, engagement_id: engagementId }, tenantHeaders(tenantId));
  return res.data;
}

// ── PBC Requests ──────────────────────────────────────────────────────────────

export async function listPBCRequests(tenantId: string, listId: string): Promise<PBCRequest[]> {
  const res = await http.get(`/pbc/lists/${listId}`, tenantHeaders(tenantId));
  // Backend returns { ...list, requests: [...] }
  return res.data.requests ?? [];
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
  const res = await http.post(`/pbc/lists/${listId}/requests`, { ...data, list_id: listId }, tenantHeaders(tenantId));
  return res.data;
}

export async function bulkCreatePBCRequests(tenantId: string, listId: string, requests: PBCRequestCreate[]): Promise<PBCRequest[]> {
  const payload = requests.map((r) => ({ ...r, list_id: listId }));
  const res = await http.post(`/pbc/lists/${listId}/requests/bulk`, payload, tenantHeaders(tenantId));
  return res.data;
}

export async function updatePBCRequestStatus(tenantId: string, requestId: string, status: string): Promise<PBCRequest> {
  if (status === 'not_applicable') {
    const res = await http.post(`/pbc/requests/${requestId}/na`, {}, tenantHeaders(tenantId));
    return res.data;
  }
  // No generic status PATCH on backend; return a no-op for other statuses
  const res = await http.get(`/pbc/requests/${requestId}/history`, tenantHeaders(tenantId));
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
  const jsonPayload = JSON.stringify({
    request_id: requestId,
    submitted_by: data.submitted_by,
    response_text: data.response_text ?? null,
    submission_notes: data.submission_notes ?? null,
  });
  formData.append('data', jsonPayload);
  if (data.file) formData.append('file', data.file);

  const res = await http.post(`/pbc/requests/${requestId}/fulfill`, formData, {
    headers: { 'x-tenant-id': tenantId, 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function exportPBCList(tenantId: string, listId: string): Promise<unknown> {
  const res = await http.get(`/export/pbc/${listId}`, tenantHeaders(tenantId));
  return res.data;
}

// ── Issues ────────────────────────────────────────────────────────────────────

export async function listIssues(tenantId: string, engagementId: string): Promise<AuditIssue[]> {
  const res = await http.get(`/issues?engagement_id=${engagementId}`, tenantHeaders(tenantId));
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
  const res = await http.post(`/issues`, { ...data, engagement_id: engagementId }, tenantHeaders(tenantId));
  return res.data;
}

export interface IssueResponseCreate {
  response_type: string;
  response_text: string;
  submitted_by: string;
  new_status?: string | null;
  file?: File | null;
}

export async function updateIssueStatus(
  tenantId: string,
  issueId: string,
  status: string,
  changedBy = 'kanban_board',
): Promise<AuditIssue> {
  const res = await http.patch(
    `/issues/${issueId}/status`,
    { status, changed_by: changedBy },
    tenantHeaders(tenantId),
  );
  return res.data;
}

export async function addIssueResponse(tenantId: string, issueId: string, data: IssueResponseCreate): Promise<IssueResponse> {
  const res = await http.post(`/issues/${issueId}/respond`, {
    issue_id: issueId,
    response_type: data.response_type,
    response_text: data.response_text,
    submitted_by: data.submitted_by,
    new_status: data.new_status ?? null,
  }, tenantHeaders(tenantId));
  return res.data;
}

export async function exportIssueRegister(tenantId: string, engagementId: string): Promise<unknown> {
  const res = await http.get(`/export/issues/${engagementId}`, tenantHeaders(tenantId));
  return res.data;
}

// ── Workpaper Templates ───────────────────────────────────────────────────────

export async function listTemplates(tenantId: string): Promise<WorkpaperTemplate[]> {
  const res = await http.get('/workpapers/templates', tenantHeaders(tenantId));
  return res.data;
}

// ── Workpapers ────────────────────────────────────────────────────────────────

export async function listWorkpapers(tenantId: string, engagementId: string): Promise<Workpaper[]> {
  const res = await http.get(`/workpapers?engagement_id=${engagementId}`, tenantHeaders(tenantId));
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
  const res = await http.post(`/workpapers`, { ...data, engagement_id: engagementId }, tenantHeaders(tenantId));
  return res.data;
}

export async function updateWorkpaperStatus(tenantId: string, wpId: string, status: string): Promise<Workpaper> {
  if (status === 'in_review') {
    const res = await http.post(`/workpapers/${wpId}/submit-review`, {}, tenantHeaders(tenantId));
    return res.data;
  }
  if (status === 'final') {
    const res = await http.post(`/workpapers/${wpId}/finalize`, {}, tenantHeaders(tenantId));
    return res.data;
  }
  // fallback: fetch current state
  const res = await http.get(`/workpapers/${wpId}`, tenantHeaders(tenantId));
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
  const res = await http.get(`/export/workpaper/${wpId}`, tenantHeaders(tenantId));
  return res.data;
}

// ── AI Summary ────────────────────────────────────────────────────────────────

export async function generateAISummary(tenantId: string, engagementId: string): Promise<{ summary: string }> {
  const res = await http.post(`/export/ai-summary/${engagementId}`, {}, tenantHeaders(tenantId));
  return res.data;
}
