export interface PortalConfig {
  id: string;
  slug: string;
  company_name: string;
  tagline: string | null;
  logo_url: string | null;
  primary_color: string;
  portal_enabled: boolean;
  require_nda: boolean;
  nda_version: string;
  show_compliance_scores: boolean;
  chatbot_enabled: boolean;
  chatbot_welcome_message: string | null;
  allowed_frameworks: string[];
}

export interface ComplianceBadge {
  framework_name: string;
  slug: string;
  score_pct: number;
  color: 'green' | 'amber' | 'red';
  badge_text: string;
}

export interface PortalDocument {
  id: string;
  display_name: string;
  description: string | null;
  document_type: string;
  requires_nda: boolean;
  is_visible: boolean;
  valid_until: string | null;
  file_size_bytes: number | null;
}

export interface NDAAcceptance {
  signatory_name: string;
  signatory_email: string;
  signatory_company: string | null;
  nda_version: string;
}

export interface ChatSession {
  id: string;
  session_token: string;
  message_count: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources: Array<{ title: string; score: number }>;
  sent_at?: string;
}

export interface DeflectionRequest {
  requester_name: string;
  requester_email: string;
  requester_company: string | null;
  questionnaire_type: string;
  questions: string[];
}

export interface DeflectionResult {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  deflection_mappings: Array<{
    question: string;
    ai_response: string;
    rag_evidence: Array<{ title: string; snippet: string }>;
  }>;
}

export interface AccessLogEvent {
  id: string;
  event_type: string;
  visitor_email: string | null;
  visitor_company: string | null;
  occurred_at: string;
  metadata: Record<string, unknown>;
}

export interface AccessLogStats {
  total_views: number;
  unique_visitors: number;
  document_downloads: number;
  chatbot_messages: number;
  ndas_signed: number;
  last_30_days: number;
}
