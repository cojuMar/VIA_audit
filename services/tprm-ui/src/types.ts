export interface Vendor {
  id: string
  name: string
  website?: string
  description?: string
  vendor_type: 'saas' | 'infrastructure' | 'professional_services' | 'data_processor' | 'financial' | 'hardware' | 'other'
  risk_tier: 'critical' | 'high' | 'medium' | 'low' | 'unrated'
  status: 'active' | 'inactive' | 'under_review' | 'offboarded'
  primary_contact_name?: string
  primary_contact_email?: string
  data_types_processed: string[]
  processes_pii: boolean
  processes_phi: boolean
  processes_pci: boolean
  uses_ai: boolean
  inherent_risk_score?: number
  residual_risk_score?: number
  next_review_at?: string
  created_at: string
}

export interface VendorIntakeForm {
  name: string
  vendor_type: Vendor['vendor_type']
  website?: string
  description?: string
  primary_contact_name?: string
  primary_contact_email?: string
  data_types_processed: string[]
  integrations_depth: 'none' | 'read_only' | 'read_write' | 'admin' | 'core_infrastructure'
  processes_pii: boolean
  processes_phi: boolean
  processes_pci: boolean
  uses_ai: boolean
  sub_processors: string[]
}

export interface QuestionnaireTemplate {
  slug: string
  name: string
  version: string
  description: string
  question_count: number
  estimated_minutes: number
}

export interface VendorQuestionnaire {
  id: string
  vendor_id: string
  template_slug: string
  status: 'draft' | 'sent' | 'in_progress' | 'completed' | 'expired'
  sent_at?: string
  due_date?: string
  completed_at?: string
  ai_score?: number
  ai_summary?: string
}

export interface VendorDocument {
  id: string
  vendor_id: string
  document_type: string
  filename: string
  file_size_bytes?: number
  upload_at: string
  expiry_date?: string
  analysis_status: 'pending' | 'analyzing' | 'completed' | 'failed'
  ai_analysis?: {
    gaps: string[]
    score: number
    summary: string
    certifications_found: string[]
  }
}

export interface MonitoringEvent {
  id: string
  vendor_id: string
  event_source: string
  event_type: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  title: string
  description?: string
  source_url?: string
  created_at: string
}

export interface VendorContract {
  id: string
  vendor_id: string
  contract_type: string
  title: string
  effective_date?: string
  expiry_date?: string
  auto_renews: boolean
  renewal_notice_days: number
  contract_value?: number
  currency: string
  sla_commitments: Record<string, unknown>
}

export interface FourthPartyGraph {
  [vendorName: string]: Array<{
    name: string
    risk_tier: string
    is_verified: boolean
  }>
}
