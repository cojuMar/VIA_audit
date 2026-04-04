export type RiskStatus = 'open' | 'in_treatment' | 'accepted' | 'closed' | 'transferred';
export type TreatmentType = 'mitigate' | 'accept' | 'transfer' | 'avoid';
export type AppetiteLevel = 'zero' | 'low' | 'moderate' | 'high' | 'very_high';
export type IndicatorStatus = 'green' | 'amber' | 'red' | 'unknown';

export interface RiskCategory {
  id: string;
  category_key: string;
  display_name: string;
  sort_order: number;
}

export interface Risk {
  id: string;
  risk_id: string;
  title: string;
  description: string;
  category_id: string;
  category_name?: string;
  category_key?: string;
  owner: string | null;
  department: string | null;
  status: RiskStatus;
  inherent_likelihood: number;
  inherent_impact: number;
  inherent_score: number;
  residual_likelihood: number | null;
  residual_impact: number | null;
  residual_score: number | null;
  target_likelihood: number | null;
  target_impact: number | null;
  framework_control_refs: string[];
  source: string;
  identified_date: string;
  review_date: string | null;
  closed_date: string | null;
}

export interface RiskRegister {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  score_distribution: { critical: number; high: number; medium: number; low: number };
  above_appetite: number;
  overdue_review: number;
}

export interface RiskTreatment {
  id: string;
  risk_id: string;
  treatment_type: TreatmentType;
  title: string;
  description: string;
  owner: string | null;
  status: string;
  target_date: string | null;
  completed_date: string | null;
  cost_estimate: number | null;
  effectiveness_rating: number | null;
}

export interface RiskAppetite {
  id: string;
  category_id: string;
  category_name: string;
  appetite_level: AppetiteLevel;
  max_acceptable_score: number;
  description: string | null;
  approved_by: string | null;
  effective_date: string;
}

export interface RiskIndicator {
  id: string;
  risk_id: string;
  indicator_name: string;
  metric_type: 'kri' | 'kpi' | 'kci';
  threshold_green: number | null;
  threshold_amber: number | null;
  threshold_red: number | null;
  current_value: number | null;
  current_status: IndicatorStatus;
  last_updated_at: string | null;
  data_source: string | null;
}

export interface HeatmapPoint {
  risk_id: string;
  title: string;
  inherent_likelihood: number;
  inherent_impact: number;
  residual_likelihood: number | null;
  residual_impact: number | null;
  category: string;
  owner: string | null;
  status: string;
}
