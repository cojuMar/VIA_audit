import axios from 'axios';
import type {
  Conversation,
  Message,
  ChatResponse,
  ReportRequest,
  Report,
  AgentTool,
  ConversationStats,
  FeedbackCreate,
} from './types';

const BASE = '/api';

function client(tenantId: string) {
  return axios.create({
    baseURL: BASE,
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-ID': tenantId,
    },
  });
}

export async function sendMessage(
  tenantId: string,
  message: string,
  conversationId?: string | null
): Promise<ChatResponse> {
  const { data } = await client(tenantId).post<ChatResponse>('/chat', {
    message,
    conversation_id: conversationId ?? null,
  });
  return data;
}

export async function listConversations(tenantId: string): Promise<Conversation[]> {
  const { data } = await client(tenantId).get<Conversation[]>('/conversations');
  return data;
}

export async function getConversation(
  tenantId: string,
  convId: string
): Promise<{ conversation: Conversation; messages: Message[] }> {
  const { data } = await client(tenantId).get(`/conversations/${convId}`);
  return data;
}

export async function archiveConversation(
  tenantId: string,
  convId: string
): Promise<void> {
  await client(tenantId).patch(`/conversations/${convId}`, { status: 'archived' });
}

export async function updateConversationTitle(
  tenantId: string,
  convId: string,
  title: string
): Promise<Conversation> {
  const { data } = await client(tenantId).patch<Conversation>(`/conversations/${convId}`, {
    title,
  });
  return data;
}

export async function getConversationStats(tenantId: string): Promise<ConversationStats> {
  const { data } = await client(tenantId).get<ConversationStats>('/stats');
  return data;
}

export async function generateReport(
  tenantId: string,
  request: ReportRequest
): Promise<Report> {
  const { data } = await client(tenantId).post<Report>('/reports', request);
  return data;
}

export async function listReports(tenantId: string, reportType?: string): Promise<Report[]> {
  const params = reportType ? { report_type: reportType } : {};
  const { data } = await client(tenantId).get<Report[]>('/reports', { params });
  return data;
}

export async function getReport(tenantId: string, reportId: string): Promise<Report> {
  const { data } = await client(tenantId).get<Report>(`/reports/${reportId}`);
  return data;
}

export async function listTools(tenantId: string): Promise<AgentTool[]> {
  const { data } = await client(tenantId).get<AgentTool[]>('/tools');
  return data;
}

export async function submitFeedback(
  tenantId: string,
  feedback: FeedbackCreate
): Promise<void> {
  await client(tenantId).post('/feedback', feedback);
}

export async function checkHealth(tenantId: string): Promise<{ status: string; model?: string }> {
  const { data } = await client(tenantId).get('/health');
  return data;
}
