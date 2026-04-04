export type EngagementStatus = 'planning' | 'fieldwork' | 'review' | 'complete' | 'cancelled';
export type PBCRequestStatus = 'open' | 'in_progress' | 'fulfilled' | 'not_applicable' | 'overdue';
export type IssueSeverity = 'critical' | 'high' | 'medium' | 'low' | 'informational';
export type IssueStatus = 'open' | 'management_response_pending' | 'in_remediation' | 'resolved' | 'closed' | 'risk_accepted';
export type WorkpaperStatus = 'draft' | 'in_review' | 'reviewed' | 'final' | 'superseded';

export interface AuditEngagement {
  id: string;
  engagement_name: string;
  engagement_type: string;
  fiscal_year: number | null;
  period_start: string | null;
  period_end: string | null;
  lead_auditor: string | null;
  status: EngagementStatus;
  description: string | null;
  created_at: string;
}

export interface PBCRequestList {
  id: string;
  engagement_id: string;
  list_name: string;
  description: string | null;
  due_date: string | null;
  status: string;
}

export interface PBCRequest {
  id: string;
  list_id: string;
  request_number: number;
  title: string;
  description: string;
  category: string | null;
  priority: 'high' | 'medium' | 'low';
  assigned_to: string | null;
  due_date: string | null;
  status: PBCRequestStatus;
  framework_control_ref: string | null;
  fulfillments?: PBCFulfillment[];
}

export interface PBCFulfillment {
  id: string;
  request_id: string;
  submitted_by: string;
  response_text: string | null;
  file_name: string | null;
  submission_notes: string | null;
  submitted_at: string;
}

export interface AuditIssue {
  id: string;
  engagement_id: string;
  issue_number: number;
  title: string;
  description: string;
  finding_type: string;
  severity: IssueSeverity;
  status: IssueStatus;
  control_reference: string | null;
  framework_references: string[];
  root_cause: string | null;
  management_owner: string | null;
  target_remediation_date: string | null;
  actual_remediation_date: string | null;
  responses?: IssueResponse[];
}

export interface IssueResponse {
  id: string;
  issue_id: string;
  response_type: string;
  response_text: string;
  submitted_by: string;
  new_status: string | null;
  file_name: string | null;
  responded_at: string;
}

export interface WorkpaperTemplate {
  id: string;
  template_key: string;
  title: string;
  description: string | null;
  template_type: string;
  sections: WorkpaperTemplateSection[];
  framework_references: string[];
}

export interface WorkpaperTemplateSection {
  section_key: string;
  title: string;
  instructions: string;
  fields: WorkpaperField[];
}

export interface WorkpaperField {
  key: string;
  type: 'text' | 'textarea' | 'number' | 'select' | 'date' | 'risk_table';
  label: string;
  options?: string[];
}

export interface Workpaper {
  id: string;
  engagement_id: string;
  template_id: string | null;
  title: string;
  wp_reference: string | null;
  workpaper_type: string;
  preparer: string | null;
  reviewer: string | null;
  status: WorkpaperStatus;
  review_notes: string | null;
  finalized_at: string | null;
  sections?: WorkpaperSection[];
}

export interface WorkpaperSection {
  id: string;
  section_key: string;
  title: string;
  content: Record<string, unknown>;
  sort_order: number;
  is_complete: boolean;
}

export interface EngagementDashboard {
  engagement: AuditEngagement;
  pbc_summary: { total: number; open: number; fulfilled: number; completion_pct: number };
  issue_summary: { total: number; by_severity: Record<string, number>; open_count: number };
  workpaper_summary: { total: number; draft: number; in_review: number; final: number; completion_pct: number };
}
