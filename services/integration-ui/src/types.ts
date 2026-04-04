export type ConnectorCategory = 'erp' | 'hris' | 'itsm' | 'cloud' | 'identity' | 'security' | 'collaboration' | 'source_control' | 'crm' | 'custom';
export type AuthType = 'oauth2' | 'api_key' | 'basic' | 'webhook' | 'service_account' | 'none';
export type IntegrationStatus = 'pending' | 'active' | 'error' | 'paused' | 'disabled';

export interface ConnectorDefinition {
  id: string;
  connector_key: string;
  display_name: string;
  category: ConnectorCategory;
  auth_type: AuthType;
  description: string | null;
  supported_data_types: string[];
  is_active: boolean;
}

export interface TenantIntegration {
  id: string;
  connector_id: string;
  integration_name: string;
  status: IntegrationStatus;
  sync_schedule: string;
  last_sync_at: string | null;
  last_sync_status: 'success' | 'partial' | 'failed' | null;
  last_sync_record_count: number | null;
  error_message: string | null;
  webhook_url: string | null;
  connector?: ConnectorDefinition;
}

export interface SyncLog {
  id: string;
  integration_id: string;
  sync_type: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'success' | 'partial' | 'failed';
  records_fetched: number | null;
  records_processed: number | null;
  data_types_synced: string[];
  error_summary: string | null;
}

export interface IntegrationRecord {
  id: string;
  data_type: string;
  source_record_id: string;
  source_system: string;
  normalized_data: Record<string, unknown>;
  ingested_at: string;
}

export interface FieldMappingTemplate {
  connector_key: string;
  data_type: string;
  source_field: string;
  target_field: string;
  transform_fn: string | null;
  is_required: boolean;
}

export interface IntegrationStats {
  total_syncs: number;
  last_sync: string | null;
  success_rate_pct: number;
  total_records: number;
  last_7_days_syncs: number;
}

export interface DashboardSummary {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  last_sync_errors: number;
}
