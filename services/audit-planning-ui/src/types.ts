export interface AuditEntityType {
  id: string;
  type_key: string;
  display_name: string;
  description: string;
  icon: string;
}

export interface AuditEntity {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  entity_type_id?: string;
  entity_type?: AuditEntityType;
  owner_name?: string;
  owner_email?: string;
  department?: string;
  risk_score: number;
  last_audit_date?: string;
  next_audit_due?: string;
  audit_frequency_months: number;
  is_in_universe: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface AuditPlan {
  id: string;
  tenant_id: string;
  plan_year: number;
  title: string;
  description?: string;
  status: string;
  total_budget_hours: number;
  approved_by?: string;
  approved_at?: string;
  item_count?: number;
  created_at: string;
  updated_at: string;
}

export interface PlanItem {
  id: string;
  plan_id: string;
  audit_entity_id?: string;
  title: string;
  audit_type: string;
  priority: string;
  planned_start_date?: string;
  planned_end_date?: string;
  budget_hours: number;
  assigned_lead?: string;
  status: string;
  rationale?: string;
  created_at: string;
}

export interface Engagement {
  id: string;
  plan_item_id?: string;
  title: string;
  engagement_code?: string;
  audit_type: string;
  status: string;
  scope?: string;
  objectives?: string;
  planned_start_date?: string;
  planned_end_date?: string;
  actual_start_date?: string;
  actual_end_date?: string;
  budget_hours: number;
  lead_auditor?: string;
  team_members: string[];
  engagement_manager?: string;
  total_logged_hours?: number;
  milestones?: Milestone[];
  resources?: ResourceAssignment[];
  created_at: string;
  updated_at: string;
}

export interface TimeEntry {
  id: string;
  engagement_id: string;
  auditor_name: string;
  auditor_email?: string;
  entry_date: string;
  hours: number;
  activity_type: string;
  description?: string;
  is_billable: boolean;
  created_at: string;
}

export interface Milestone {
  id: string;
  engagement_id: string;
  title: string;
  milestone_type: string;
  due_date: string;
  completed_date?: string;
  status: string;
  owner?: string;
  notes?: string;
  days_until_due?: number;
}

export interface ResourceAssignment {
  id: string;
  engagement_id: string;
  auditor_name: string;
  auditor_email: string;
  role: string;
  allocated_hours: number;
  start_date?: string;
  end_date?: string;
  is_active: boolean;
  actual_hours?: number;
}

export interface UniverseCoverage {
  total_entities: number;
  entities_with_audits: number;
  coverage_pct: number;
  high_risk_unaudited: AuditEntity[];
}

export interface PlanSummary {
  plan: AuditPlan;
  items_by_priority: Record<string, number>;
  items_by_status: Record<string, number>;
  budget_total: number;
  items_by_type: Record<string, number>;
}

export interface EngagementHours {
  total_hours: number;
  budget_hours: number;
  variance: number;
  variance_pct: number;
  by_activity: Record<string, number>;
  by_auditor: Array<{ name: string; email: string; hours: number }>;
  daily_trend: Array<{ date: string; hours: number }>;
}

export interface GanttItem {
  id: string;
  title: string;
  code?: string;
  start?: string;
  end?: string;
  status: string;
  milestones: Array<{ title: string; due: string; done: boolean }>;
}
