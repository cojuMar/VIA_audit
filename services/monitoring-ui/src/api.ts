import axios from 'axios';
import type {
  FindingsSummary,
  MonitoringFinding,
  TrendDataPoint,
  MonitoringRule,
  TenantRuleConfig,
  SoDRule,
  SoDViolation,
  MonitoringRun,
} from './types';

const client = axios.create({
  baseURL: '/api',
});

function tenantHeaders(tenantId: string) {
  return { headers: { 'X-Tenant-ID': tenantId } };
}

export const getFindingsSummary = async (tenantId: string): Promise<FindingsSummary> => {
  const { data } = await client.get<FindingsSummary>('/findings/summary', tenantHeaders(tenantId));
  return data;
};

export const getFindings = async (
  tenantId: string,
  params?: {
    severity?: string;
    finding_type?: string;
    status?: string;
    limit?: number;
  }
): Promise<MonitoringFinding[]> => {
  const { data } = await client.get<{ findings: MonitoringFinding[]; count: number }>('/findings', {
    ...tenantHeaders(tenantId),
    params,
  });
  return Array.isArray(data) ? data : (data?.findings ?? []);
};

export const getFindingsTrend = async (
  tenantId: string,
  days = 30
): Promise<TrendDataPoint[]> => {
  const { data } = await client.get<{ trend: TrendDataPoint[] } | TrendDataPoint[]>('/findings/trend', {
    ...tenantHeaders(tenantId),
    params: { days },
  });
  return Array.isArray(data) ? data : ((data as { trend: TrendDataPoint[] })?.trend ?? []);
};

export const getRules = async (tenantId: string): Promise<MonitoringRule[]> => {
  const { data } = await client.get<{ rules: MonitoringRule[] } | MonitoringRule[]>('/rules', tenantHeaders(tenantId));
  return Array.isArray(data) ? data : ((data as { rules: MonitoringRule[] })?.rules ?? []);
};

export const getTenantConfig = async (tenantId: string): Promise<TenantRuleConfig[]> => {
  const { data } = await client.get<{ config: TenantRuleConfig[] } | TenantRuleConfig[]>('/config', tenantHeaders(tenantId));
  return Array.isArray(data) ? data : ((data as { config: TenantRuleConfig[] })?.config ?? []);
};

export const updateRuleConfig = async (
  tenantId: string,
  ruleKey: string,
  config: Partial<TenantRuleConfig>
): Promise<TenantRuleConfig> => {
  const { data } = await client.patch<TenantRuleConfig>(
    `/config/${ruleKey}`,
    config,
    tenantHeaders(tenantId)
  );
  return data;
};

export const getSoDRules = async (tenantId: string): Promise<SoDRule[]> => {
  const { data } = await client.get<SoDRule[]>('/sod/rules', tenantHeaders(tenantId));
  return data;
};

export const getSoDViolations = async (tenantId: string): Promise<SoDViolation[]> => {
  const { data } = await client.get<SoDViolation[]>('/sod/violations', tenantHeaders(tenantId));
  return data;
};

export const getSoDSummary = async (
  tenantId: string
): Promise<{ total: number; by_severity: Record<string, number>; unique_users_affected: number }> => {
  const { data } = await client.get('/sod/summary', tenantHeaders(tenantId));
  return data;
};

export const getCloudSnapshots = async (tenantId: string): Promise<unknown[]> => {
  const { data } = await client.get('/cloud/snapshots', tenantHeaders(tenantId));
  return data;
};

export const getCloudSummary = async (tenantId: string): Promise<unknown> => {
  const { data } = await client.get('/cloud/summary', tenantHeaders(tenantId));
  return data;
};

export const getRuns = async (
  tenantId: string,
  params?: { rule_key?: string; limit?: number }
): Promise<MonitoringRun[]> => {
  const { data } = await client.get<MonitoringRun[]>('/runs', {
    ...tenantHeaders(tenantId),
    params,
  });
  return data;
};

export const runAnalysis = async (
  tenantId: string,
  endpoint: string,
  data: unknown[]
): Promise<{ run_id: string; findings_count: number; findings: MonitoringFinding[] }> => {
  const response = await client.post(
    `/analyze/${endpoint}`,
    { data },
    tenantHeaders(tenantId)
  );
  return response.data;
};
