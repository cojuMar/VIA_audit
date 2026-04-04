import axios from 'axios';
import type {
  PortalConfig,
  ComplianceBadge,
  PortalDocument,
  NDAAcceptance,
  ChatSession,
  ChatMessage,
  DeflectionRequest,
  DeflectionResult,
  AccessLogEvent,
  AccessLogStats,
} from './types';

const publicClient = axios.create({ baseURL: '/api/portal' });
const adminClient = axios.create({ baseURL: '/api/admin/portal' });

// ── Public API ──────────────────────────────────────────────────────────────

export const getPortalPublic = async (slug: string): Promise<{ config: PortalConfig; badges: ComplianceBadge[] }> => {
  const res = await publicClient.get(`/${slug}`);
  return res.data;
};

export const getDocuments = async (slug: string, ndaEmail?: string): Promise<PortalDocument[]> => {
  const res = await publicClient.get(`/${slug}/documents`, {
    params: ndaEmail ? { nda_email: ndaEmail } : undefined,
  });
  return res.data;
};

export const signNDA = async (slug: string, data: NDAAcceptance, ip?: string): Promise<{ success: boolean }> => {
  const res = await publicClient.post(`/${slug}/nda`, data, {
    headers: ip ? { 'X-Forwarded-For': ip } : undefined,
  });
  return res.data;
};

export const getDownloadUrl = async (slug: string, docId: string, ndaEmail: string): Promise<{ url: string }> => {
  const res = await publicClient.get(`/${slug}/documents/${docId}/download`, {
    params: { nda_email: ndaEmail },
  });
  return res.data;
};

export const createChatSession = async (slug: string, email?: string, company?: string): Promise<ChatSession> => {
  const res = await publicClient.post(`/${slug}/chat/session`, { email, company });
  return res.data;
};

export const sendChatMessage = async (
  slug: string,
  token: string,
  message: string
): Promise<ChatMessage> => {
  const res = await publicClient.post(`/${slug}/chat/message`, { message }, {
    headers: { 'X-Session-Token': token },
  });
  return res.data;
};

export const submitDeflection = async (slug: string, data: DeflectionRequest): Promise<DeflectionResult> => {
  const res = await publicClient.post(`/${slug}/deflection`, data);
  return res.data;
};

export const getDeflectionResult = async (slug: string, id: string): Promise<DeflectionResult> => {
  const res = await publicClient.get(`/${slug}/deflection/${id}`);
  return res.data;
};

// ── Admin API ────────────────────────────────────────────────────────────────

const withTenant = (tenantId: string) => ({ headers: { 'X-Tenant-ID': tenantId } });

export const getAdminConfig = async (tenantId: string): Promise<PortalConfig> => {
  const res = await adminClient.get('/config', withTenant(tenantId));
  return res.data;
};

export const upsertAdminConfig = async (tenantId: string, config: Partial<PortalConfig>): Promise<PortalConfig> => {
  const res = await adminClient.put('/config', config, withTenant(tenantId));
  return res.data;
};

export const getAdminDocuments = async (tenantId: string): Promise<PortalDocument[]> => {
  const res = await adminClient.get('/documents', withTenant(tenantId));
  return res.data;
};

export const uploadDocument = async (tenantId: string, formData: FormData): Promise<PortalDocument> => {
  const res = await adminClient.post('/documents', formData, {
    headers: {
      'X-Tenant-ID': tenantId,
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data;
};

export const deleteDocument = async (tenantId: string, docId: string): Promise<void> => {
  await adminClient.delete(`/documents/${docId}`, withTenant(tenantId));
};

export const getAccessLogs = async (
  tenantId: string,
  limit?: number,
  eventType?: string
): Promise<AccessLogEvent[]> => {
  const res = await adminClient.get('/logs', {
    ...withTenant(tenantId),
    params: { limit, event_type: eventType },
  });
  return res.data;
};

export const getAccessStats = async (tenantId: string): Promise<AccessLogStats> => {
  const res = await adminClient.get('/logs/stats', withTenant(tenantId));
  return res.data;
};

export const getNDAList = async (tenantId: string): Promise<NDAAcceptance[]> => {
  const res = await adminClient.get('/ndas', withTenant(tenantId));
  return res.data;
};

export const getNDAStats = async (tenantId: string): Promise<{
  total: number;
  last_7_days: number;
  unique_companies: number;
}> => {
  const res = await adminClient.get('/ndas/stats', withTenant(tenantId));
  return res.data;
};

export const getDeflections = async (tenantId: string): Promise<DeflectionResult[]> => {
  const res = await adminClient.get('/deflections', withTenant(tenantId));
  return res.data;
};
