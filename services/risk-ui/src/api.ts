import axios from 'axios';
import type {
  Risk,
  RiskRegister,
  RiskTreatment,
  RiskAppetite,
  RiskIndicator,
  HeatmapPoint,
  RiskCategory,
} from './types';

let _tenantId = 'default';

export function setTenantId(id: string) {
  _tenantId = id;
}

const client = axios.create({
  baseURL: '/api',
});

client.interceptors.request.use((config) => {
  config.headers['X-Tenant-ID'] = _tenantId;
  return config;
});

// ── Risk Categories ───────────────────────────────────────────────────────────
export async function fetchCategories(): Promise<RiskCategory[]> {
  const { data } = await client.get('/categories');
  const cats = Array.isArray(data) ? data : (data?.categories ?? []);
  // Backend returns `name` field; map to `display_name` for UI compatibility
  return cats.map((c: { id: string; category_key: string; name?: string; display_name?: string; sort_order?: number }) => ({
    id: c.id,
    category_key: c.category_key,
    display_name: c.display_name ?? c.name ?? c.category_key,
    sort_order: c.sort_order ?? 0,
  }));
}

// ── Risk Register ─────────────────────────────────────────────────────────────
export async function fetchRegisterSummary(): Promise<RiskRegister> {
  const { data } = await client.get('/risks/register');
  return data;
}

export async function fetchRisks(params?: Record<string, string>): Promise<Risk[]> {
  const { data } = await client.get('/risks', { params });
  return Array.isArray(data) ? data : (data?.risks ?? []);
}

export async function fetchRisk(id: string): Promise<Risk> {
  const { data } = await client.get(`/risks/${id}`);
  return data;
}

export async function createRisk(payload: Partial<Risk>): Promise<Risk> {
  const { data } = await client.post('/risks', payload);
  return data;
}

export async function updateRisk(id: string, payload: Partial<Risk>): Promise<Risk> {
  const { data } = await client.patch(`/risks/${id}`, payload);
  return data;
}

export async function closeRisk(id: string): Promise<Risk> {
  const { data } = await client.post(`/risks/${id}/close`);
  return data;
}

export async function importFromFindings(): Promise<{ imported: number }> {
  const { data } = await client.post('/auto-import/from-findings');
  return data;
}

// ── Heatmap ───────────────────────────────────────────────────────────────────
export async function fetchHeatmap(): Promise<HeatmapPoint[]> {
  const { data } = await client.get('/risks/heatmap');
  return Array.isArray(data) ? data : (data?.risks ?? data?.heatmap ?? []);
}

// ── Treatments ────────────────────────────────────────────────────────────────
export async function fetchTreatments(riskId?: string): Promise<RiskTreatment[]> {
  const params = riskId ? { risk_id: riskId } : undefined;
  const { data } = await client.get('/treatments', { params });
  return Array.isArray(data) ? data : (data?.treatments ?? []);
}

export async function createTreatment(payload: Partial<RiskTreatment>): Promise<RiskTreatment> {
  const { data } = await client.post('/treatments', payload);
  return data;
}

export async function updateTreatment(
  id: string,
  payload: Partial<RiskTreatment>
): Promise<RiskTreatment> {
  const { data } = await client.patch(`/treatments/${id}`, payload);
  return data;
}

export async function suggestTreatments(
  riskId: string
): Promise<{ suggestions: Array<{ title: string; description: string; treatment_type: string }> }> {
  const { data } = await client.post(`/ai/suggest-treatments/${riskId}`);
  return data;
}

// ── Indicators ────────────────────────────────────────────────────────────────
export async function fetchIndicators(riskId: string): Promise<RiskIndicator[]> {
  const { data } = await client.get(`/indicators?risk_id=${riskId}`);
  return Array.isArray(data) ? data : (data?.indicators ?? []);
}

export async function createIndicator(
  riskId: string,
  payload: Partial<RiskIndicator>
): Promise<RiskIndicator> {
  const { data } = await client.post(`/risks/${riskId}/indicators`, payload);
  return data;
}

export async function recordReading(
  indicatorId: string,
  value: number
): Promise<RiskIndicator> {
  const { data } = await client.post(`/indicators/${indicatorId}/readings`, { value });
  return data;
}

// ── Appetite ──────────────────────────────────────────────────────────────────
export async function fetchAppetites(): Promise<RiskAppetite[]> {
  const { data } = await client.get('/appetite');
  return Array.isArray(data) ? data : (data?.appetite ?? []);
}

export async function upsertAppetite(payload: Partial<RiskAppetite>): Promise<RiskAppetite> {
  const categoryKey = (payload as { category_key?: string }).category_key ?? payload.category_id;
  const { data } = await client.post(`/appetite/${categoryKey}`, payload);
  return data;
}

// ── AI Narrative ───────────────────────���──────────────────────────────────���───
export async function fetchAiNarrative(): Promise<{ narrative: string; generated_at: string }> {
  const { data } = await client.post('/ai/narrative');
  return data;
}

// ── Score History ─────────────────────────────────────────────────────────────
export async function fetchScoreHistory(
  riskId: string
): Promise<
  Array<{
    id: string;
    assessed_at: string;
    assessed_by: string | null;
    inherent_score: number;
    residual_score: number | null;
    notes: string | null;
  }>
> {
  try {
    const { data } = await client.get(`/risks/${riskId}/assessments`);
    return Array.isArray(data) ? data : (data?.assessments ?? data?.history ?? []);
  } catch {
    return [];
  }
}
