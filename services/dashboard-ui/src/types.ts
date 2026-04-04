export type Mode = 'firm' | 'smb' | 'autonomous'
export type Framework = 'soc2' | 'iso27001' | 'pci_dss' | 'custom'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface WhiteLabelConfig {
  firm_name: string
  logo_url?: string
  primary_color: string
  secondary_color: string
  accent_color: string
  font_family: string
}

export interface HealthScore {
  overall_score: number
  snapshot_time?: string
  dimensions: {
    access_control: number
    data_integrity: number
    anomaly_rate: number
    evidence_freshness: number
    narrative_quality: number
  }
  open_issues: number
  critical_issues: number
}

export interface Gauge {
  id: string
  label: string
  value: number
  unit: string
  thresholds: { warning: number; critical: number }
}

export interface EvidenceRecord {
  evidence_id: string
  source_system: string
  event_type: string
  entity_type: string
  outcome: string
  event_timestamp: string
  ingested_at: string
  chain_sequence: number
}

export interface AuditHubItem {
  item_id: string
  framework: string
  control_id: string
  title: string
  description?: string
  status: 'open' | 'in_progress' | 'resolved' | 'waived'
  priority: 'low' | 'medium' | 'high' | 'critical'
  due_date?: string
  evidence_count: number
}

export interface ClientSummary {
  client_tenant_id: string
  client_alias?: string
  tenant_name: string
  overall_score?: number
  open_issues?: number
  critical_issues?: number
}

export interface AnomalyFeedItem {
  anomaly_id: string
  dri_score: number
  risk_level: RiskLevel
  vae_score: number
  isolation_score: number
  benford_risk: number
  scored_at: string
  event_type: string
  entity_type: string
  source_system: string
  false_positive: boolean
}
