export interface TemplateType {
  id: string;
  type_key: string;
  display_name: string;
  icon: string;
}

export interface TemplateQuestion {
  id: string;
  section_name: string;
  sequence_number: number;
  question_text: string;
  question_type: string;
  options: string[];
  is_required: boolean;
  requires_photo_if?: string;
  requires_comment_if?: string;
  risk_weight: number;
}

export interface TemplateSection {
  name: string;
  questions: TemplateQuestion[];
}

export interface AuditTemplate {
  id: string;
  template_key: string;
  display_name: string;
  description?: string;
  icon?: string;
  estimated_duration_minutes: number;
  requires_photo_evidence: boolean;
  requires_signature: boolean;
  requires_gps: boolean;
  section_count: number;
  question_count: number;
  sections: TemplateSection[];
}

export interface Assignment {
  id: string;
  template_id: string;
  template_name?: string;
  assigned_to_email: string;
  location_name: string;
  location_address?: string;
  scheduled_date: string;
  due_date: string;
  priority: string;
  status: string;
  notes?: string;
}

export interface FieldAudit {
  id: string;
  assignment_id?: string;
  template_id: string;
  auditor_email: string;
  auditor_name?: string;
  location_name: string;
  status: string;
  started_at: string;
  completed_at?: string;
  submitted_at?: string;
  device_id?: string;
  gps_latitude?: number;
  gps_longitude?: number;
  overall_score?: number;
  risk_level?: string;
  total_findings: number;
  notes?: string;
  // Local-only fields (not in DB)
  _localOnly?: boolean;  // true if created offline, not yet synced
  _pendingSync?: boolean;
}

export interface ResponsePayload {
  question_id: string;
  response_value?: string;
  numeric_response?: number;
  boolean_response?: boolean;
  gps_latitude?: number;
  gps_longitude?: number;
  comment?: string;
  is_finding: boolean;
  finding_severity?: string;
  photo_references: string[];
  client_answered_at?: string;
  sync_id: string;  // client-generated UUID
}

export interface AuditPhoto {
  id: string;
  field_audit_id: string;
  minio_object_key: string;
  original_filename?: string;
  caption?: string;
  gps_latitude?: number;
  gps_longitude?: number;
  taken_at?: string;
  sync_id?: string;
  // Local-only
  _localDataUrl?: string;  // base64 data URL for offline display
}

export interface SyncStatus {
  pendingAudits: number;
  pendingResponses: number;
  pendingPhotos: number;
  lastSyncAt?: string;
  isOnline: boolean;
  isSyncing: boolean;
}

export interface AuditSummary {
  audit: FieldAudit;
  response_count: number;
  finding_count: number;
  findings_by_severity: Record<string, number>;
  section_scores: Array<{ section_name: string; score_pct: number; finding_count: number }>;
  photos: AuditPhoto[];
}

export interface Finding {
  question_id: string;
  question_text: string;
  section_name: string;
  response_value?: string;
  numeric_response?: number;
  boolean_response?: boolean;
  comment?: string;
  finding_severity: string;
  photo_references: string[];
}
