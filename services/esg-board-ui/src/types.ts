export interface ESGFramework {
  id: string;
  framework_key: string;
  display_name: string;
  description: string;
  category: string;
  version?: string;
  issuing_body?: string;
  is_mandatory: boolean;
}

export interface ESGMetricDefinition {
  id: string;
  framework_id?: string;
  metric_key: string;
  display_name: string;
  description?: string;
  category: 'environmental' | 'social' | 'governance';
  subcategory?: string;
  unit: string;
  data_type: string;
  lower_is_better: boolean;
  is_required: boolean;
  disclosure_reference?: string;
  framework?: ESGFramework;
}

export interface ESGDisclosure {
  id: string;
  tenant_id: string;
  metric_definition_id: string;
  reporting_period: string;
  period_type: string;
  numeric_value?: number;
  text_value?: string;
  boolean_value?: boolean;
  currency_value?: number;
  currency_code: string;
  notes?: string;
  data_source?: string;
  assurance_level?: string;
  assured_by?: string;
  submitted_by?: string;
  created_at: string;
  metric?: ESGMetricDefinition;
}

export interface ESGTarget {
  id: string;
  metric_definition_id: string;
  target_year: number;
  baseline_year?: number;
  baseline_value?: number;
  target_value: number;
  target_type: string;
  description?: string;
  science_based: boolean;
  framework_alignment: string[];
  status: string;
  metric?: ESGMetricDefinition;
}

export interface TargetProgress extends ESGTarget {
  latest_value?: number;
  progress_pct?: number;
  on_track: boolean;
}

export interface ESGScorecard {
  reporting_period: string;
  environmental: { coverage_pct: number; metrics: ScorecardMetric[] };
  social: { coverage_pct: number; metrics: ScorecardMetric[] };
  governance: { coverage_pct: number; metrics: ScorecardMetric[] };
  overall_coverage_pct: number;
  total_metrics: number;
  disclosed_metrics: number;
}

export interface ScorecardMetric {
  metric_key: string;
  display_name: string;
  unit: string;
  latest_value?: number | string;
  is_required: boolean;
  has_disclosure: boolean;
  assurance_level?: string;
}

export interface BoardCommittee {
  id: string;
  name: string;
  committee_type: string;
  charter?: string;
  members: string[];
  chair?: string;
  quorum_requirement: number;
  meeting_frequency: string;
  is_active: boolean;
  meeting_count?: number;
}

export interface BoardMeeting {
  id: string;
  committee_id?: string;
  committee_name?: string;
  title: string;
  meeting_type: string;
  scheduled_date: string;
  actual_date?: string;
  location?: string;
  virtual_link?: string;
  status: string;
  quorum_met?: boolean;
  attendees: string[];
  minutes_text?: string;
  minutes_approved: boolean;
  agenda_items?: AgendaItem[];
  agenda_item_count?: number;
  created_at: string;
  updated_at: string;
}

export interface AgendaItem {
  id: string;
  meeting_id: string;
  sequence_number: number;
  title: string;
  item_type: string;
  description?: string;
  presenter?: string;
  duration_minutes: number;
  status: string;
  decision?: string;
  action_items: string[];
}

export interface BoardPackage {
  id: string;
  meeting_id?: string;
  title: string;
  package_type: string;
  reporting_period?: string;
  status: string;
  prepared_by?: string;
  approved_by?: string;
  distributed_at?: string;
  recipient_list: string[];
  executive_summary?: string;
  ai_generated_summary?: string;
  items?: PackageItem[];
  item_count?: number;
  created_at: string;
}

export interface PackageItem {
  id: string;
  package_id: string;
  sequence_number: number;
  section_title: string;
  content_type: string;
  content_data: Record<string, unknown>;
  source_service?: string;
  is_confidential: boolean;
  created_at: string;
}

export interface TrendDataPoint {
  reporting_period: string;
  value: number;
  data_source?: string;
  assurance_level?: string;
}
