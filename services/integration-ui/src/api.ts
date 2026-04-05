import axios from 'axios';
import type {
  ConnectorDefinition,
  TenantIntegration,
  SyncLog,
  IntegrationRecord,
  FieldMappingTemplate,
  IntegrationStats,
  DashboardSummary,
} from './types';

const BASE = '/api';

function client(tenantId: string) {
  return axios.create({
    baseURL: BASE,
    headers: {
      'X-Tenant-ID': tenantId,
      'Content-Type': 'application/json',
    },
  });
}

// Connectors
export async function listConnectors(tenantId: string): Promise<ConnectorDefinition[]> {
  const { data } = await client(tenantId).get('/connectors');
  return Array.isArray(data) ? data : (data?.connectors ?? []);
}

export async function getConnector(tenantId: string, connectorId: string): Promise<ConnectorDefinition> {
  const { data } = await client(tenantId).get(`/connectors/${connectorId}`);
  return data;
}

// Integrations
export async function listIntegrations(tenantId: string): Promise<TenantIntegration[]> {
  const { data } = await client(tenantId).get('/integrations');
  return Array.isArray(data) ? data : (data?.integrations ?? []);
}

export async function getIntegration(tenantId: string, integrationId: string): Promise<TenantIntegration> {
  const { data } = await client(tenantId).get(`/integrations/${integrationId}`);
  return data;
}

export async function createIntegration(
  tenantId: string,
  payload: {
    connector_id: string;
    integration_name: string;
    sync_schedule: string;
    auth_config: Record<string, unknown>;
    selected_data_types: string[];
    field_mappings?: Array<{
      data_type: string;
      source_field: string;
      target_field: string;
      transform_fn?: string | null;
    }>;
  }
): Promise<TenantIntegration> {
  const { data } = await client(tenantId).post('/integrations', payload);
  return data;
}

export async function updateIntegration(
  tenantId: string,
  integrationId: string,
  payload: Partial<{
    integration_name: string;
    sync_schedule: string;
    status: string;
    auth_config: Record<string, unknown>;
  }>
): Promise<TenantIntegration> {
  const { data } = await client(tenantId).patch(`/integrations/${integrationId}`, payload);
  return data;
}

export async function deleteIntegration(tenantId: string, integrationId: string): Promise<void> {
  await client(tenantId).delete(`/integrations/${integrationId}`);
}

export async function triggerSync(
  tenantId: string,
  integrationId: string,
  options?: { save_results?: boolean }
): Promise<{ job_id: string; message: string }> {
  const { data } = await client(tenantId).post(`/integrations/${integrationId}/sync`, options ?? {});
  return data;
}

// Sync logs
export async function listSyncLogs(
  tenantId: string,
  integrationId: string,
  params?: { limit?: number; offset?: number }
): Promise<SyncLog[]> {
  const { data } = await client(tenantId).get(`/integrations/${integrationId}/sync-logs`, { params });
  return data;
}

// Records
export async function listRecords(
  tenantId: string,
  integrationId: string,
  params?: { data_type?: string; limit?: number; offset?: number }
): Promise<IntegrationRecord[]> {
  const { data } = await client(tenantId).get(`/integrations/${integrationId}/records`, { params });
  return data;
}

// Field mappings
export async function getFieldMappingTemplates(
  tenantId: string,
  connectorKey: string,
  dataType?: string
): Promise<FieldMappingTemplate[]> {
  const params = dataType ? { data_type: dataType } : undefined;
  const { data } = await client(tenantId).get(`/connectors/${connectorKey}/field-mappings`, { params });
  return data;
}

export async function updateFieldMappings(
  tenantId: string,
  integrationId: string,
  mappings: Array<{
    data_type: string;
    source_field: string;
    target_field: string;
    transform_fn?: string | null;
  }>
): Promise<void> {
  await client(tenantId).put(`/integrations/${integrationId}/field-mappings`, { mappings });
}

// Stats & dashboard
export async function getIntegrationStats(
  tenantId: string,
  integrationId: string
): Promise<IntegrationStats> {
  const { data } = await client(tenantId).get(`/integrations/${integrationId}/stats`);
  return data;
}

export async function getDashboardSummary(tenantId: string): Promise<DashboardSummary> {
  const { data } = await client(tenantId).get('/dashboard/summary');
  return data;
}
