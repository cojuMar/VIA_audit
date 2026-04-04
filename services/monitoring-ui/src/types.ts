export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type FindingStatus = 'open' | 'acknowledged' | 'resolved' | 'false_positive';
export type FindingType =
  | 'payroll_outlier'
  | 'payroll_ghost'
  | 'payroll_benford'
  | 'duplicate_invoice'
  | 'invoice_split'
  | 'card_policy'
  | 'sod_conflict'
  | 'cloud_s3_public'
  | 'cloud_sg_open'
  | 'cloud_mfa_disabled'
  | string;

export interface MonitoringFinding {
  id: string;
  run_id: string;
  rule_id: string;
  finding_type: FindingType;
  severity: Severity;
  title: string;
  description: string;
  entity_type: string | null;
  entity_id: string | null;
  entity_name: string | null;
  evidence: Record<string, unknown>;
  risk_score: number | null;
  status: FindingStatus;
  detected_at: string;
}

export interface FindingsSummary {
  total: number;
  by_severity: { critical: number; high: number; medium: number; low: number; info: number };
  by_type: Record<string, number>;
  open_count: number;
  last_run_at: string | null;
}

export interface TrendDataPoint {
  date: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface MonitoringRule {
  id: string;
  rule_key: string;
  category: 'payroll' | 'ap' | 'card' | 'sod' | 'cloud';
  display_name: string;
  description: string;
  severity_default: Severity;
  is_active: boolean;
}

export interface TenantRuleConfig {
  rule_key: string;
  is_enabled: boolean;
  schedule_cron: string;
  last_run_at: string | null;
  next_run_at: string | null;
  config_overrides: Record<string, unknown>;
}

export interface SoDRule {
  id: string;
  rule_key: string;
  display_name: string;
  role_a: string;
  role_b: string;
  severity: Severity;
  framework_references: string[];
}

export interface SoDViolation {
  id: string;
  sod_rule_id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  role_a_detail: string;
  role_b_detail: string;
  department: string | null;
  risk_score: number | null;
  detected_at: string;
}

export interface MonitoringRun {
  id: string;
  rule_id: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'completed' | 'failed';
  records_processed: number | null;
  findings_count: number;
  error_message: string | null;
}

export interface AnalysisRequest {
  type: 'payroll' | 'invoices' | 'card-spend' | 'sod' | 'cloud-config';
  data: unknown[];
}
