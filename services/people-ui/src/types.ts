export interface Employee {
  id: string;
  employee_id: string;
  full_name: string;
  email: string;
  department: string | null;
  job_title: string | null;
  job_role: string;
  manager_id: string | null;
  hire_date: string | null;
  employment_status: 'active' | 'on_leave' | 'terminated';
}

export interface HRPolicy {
  id: string;
  policy_key: string;
  title: string;
  description: string | null;
  category: string;
  applies_to_roles: string[];
  current_version: string;
  acknowledgment_required: boolean;
  acknowledgment_frequency_days: number;
  is_active: boolean;
}

export interface PolicyAckStatus {
  policy_id: string;
  title: string;
  required: boolean;
  acknowledged: boolean;
  acknowledged_at: string | null;
  is_overdue: boolean;
  days_until_due: number | null;
}

export interface TrainingCourse {
  id: string;
  course_key: string;
  title: string;
  category: string;
  duration_minutes: number | null;
  passing_score_pct: number;
  recurrence_days: number | null;
  provider: string;
  is_active: boolean;
}

export interface TrainingAssignment {
  id: string;
  course_id: string;
  employee_id: string;
  due_date: string | null;
  status: 'assigned' | 'in_progress' | 'completed' | 'overdue' | 'waived';
  reminder_sent_count: number;
  course?: TrainingCourse;
}

export interface BackgroundCheck {
  id: string;
  employee_id: string;
  check_type: string;
  provider: string;
  status: 'pending' | 'in_progress' | 'passed' | 'failed' | 'expired' | 'cancelled';
  initiated_at: string;
  completed_at: string | null;
  expiry_date: string | null;
  adjudication: 'clear' | 'review' | 'adverse_action' | null;
}

export interface EmployeeComplianceScore {
  employee_id: string;
  full_name: string;
  overall_score: number;
  policy_score: number;
  training_score: number;
  background_check_score: number;
  status: 'compliant' | 'at_risk' | 'non_compliant';
  open_items: number;
  details: Record<string, unknown>;
}

export interface OrgComplianceSummary {
  overall_score: number;
  compliant_count: number;
  at_risk_count: number;
  non_compliant_count: number;
  total_employees: number;
  compliance_rate_pct: number;
  by_department: Array<{dept: string; score: number; employee_count: number}>;
  top_issues: Array<{issue_type: string; count: number; description: string}>;
}

export interface Escalation {
  id: string;
  escalation_type: string;
  employee_id: string;
  reference_type: string | null;
  days_overdue: number | null;
  resolved: boolean;
  escalated_at: string;
  message: string | null;
}
