export interface ComplianceFramework {
  id: string
  slug: string
  name: string
  version: string
  category: 'security' | 'privacy' | 'financial' | 'operational' | 'sustainability' | 'ai' | 'sector-specific'
  description: string
  issuing_body: string
  is_active: boolean
  metadata: {
    renewal_period_days?: number
    filing_required?: boolean
    cost_tier?: 'low' | 'medium' | 'high'
    geographic_scope?: string
  }
}

export interface FrameworkControl {
  id: string
  framework_id: string
  control_id: string
  domain: string
  title: string
  description: string
  evidence_types: string[]
  testing_frequency: string
  is_key_control: boolean
}

export interface ComplianceScore {
  framework_id: string
  framework_name: string
  slug: string
  score_pct: number
  passing_controls: number
  failing_controls: number
  not_started_controls: number
  total_controls: number
  computed_at: string
}

export interface GapItem {
  framework_control_id: string
  control_id: string
  control_title: string
  domain: string
  gap_severity: 'critical' | 'high' | 'medium' | 'low'
  gap_description: string
  remediation_steps?: string
}

export interface CalendarEvent {
  framework_id: string
  framework_name: string
  event_type: 'filing_deadline' | 'cert_renewal' | 'control_review' | 'periodic_activity' | 'audit_window'
  title: string
  due_date: string
  description?: string
  is_completed: boolean
  days_until_due: number
}

export interface CrosswalkPair {
  framework_a: string
  framework_b: string
  crosswalk_control_pairs: number
}
