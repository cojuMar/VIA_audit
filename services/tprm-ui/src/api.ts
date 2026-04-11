import type {
  Vendor,
  VendorIntakeForm,
  QuestionnaireTemplate,
  VendorQuestionnaire,
  VendorDocument,
  MonitoringEvent,
  VendorContract,
  FourthPartyGraph,
} from './types'

const BASE = '/api'

async function request<T>(path: string, tenantId: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-ID': tenantId,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ── Vendors ──────────────────────────────────────────────────────────────────

export const api = {
  // List all vendors for a tenant
  getVendors(tenantId: string): Promise<Vendor[]> {
    return request<Vendor[]>('/vendors', tenantId)
  },

  // Get a single vendor
  getVendor(tenantId: string, vendorId: string): Promise<Vendor> {
    return request<Vendor>(`/vendors/${vendorId}`, tenantId)
  },

  // Create a vendor via the intake form
  createVendor(tenantId: string, form: VendorIntakeForm): Promise<Vendor> {
    return request<Vendor>('/vendors', tenantId, {
      method: 'POST',
      body: JSON.stringify(form),
    })
  },

  // Update vendor fields
  updateVendor(tenantId: string, vendorId: string, patch: Partial<Vendor>): Promise<Vendor> {
    return request<Vendor>(`/vendors/${vendorId}`, tenantId, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  },

  // Delete (offboard) a vendor
  deleteVendor(tenantId: string, vendorId: string): Promise<void> {
    return request<void>(`/vendors/${vendorId}`, tenantId, { method: 'DELETE' })
  },

  // Risk score history snapshots
  getVendorRiskHistory(tenantId: string, vendorId: string): Promise<Array<{ recorded_at: string; score: number; tier: string }>> {
    return request(`/vendors/${vendorId}/risk-score`, tenantId)
  },

  // ── Questionnaires ─────────────────────────────────────────────────────────

  // List available questionnaire templates
  getQuestionnaireTemplates(tenantId: string): Promise<QuestionnaireTemplate[]> {
    return request<QuestionnaireTemplate[]>('/questionnaires/templates', tenantId)
  },

  // List questionnaires for a vendor
  getVendorQuestionnaires(tenantId: string, vendorId: string): Promise<VendorQuestionnaire[]> {
    return request<VendorQuestionnaire[]>(`/vendors/${vendorId}/questionnaires`, tenantId)
  },

  // Send a questionnaire to a vendor
  sendQuestionnaire(tenantId: string, vendorId: string, templateSlug: string): Promise<VendorQuestionnaire> {
    return request<VendorQuestionnaire>(`/vendors/${vendorId}/questionnaires`, tenantId, {
      method: 'POST',
      body: JSON.stringify({ template_slug: templateSlug }),
    })
  },

  // Get a single questionnaire
  getQuestionnaire(tenantId: string, _vendorId: string, questionnaireId: string): Promise<VendorQuestionnaire> {
    return request<VendorQuestionnaire>(`/questionnaires/${questionnaireId}`, tenantId)
  },

  // ── Documents ──────────────────────────────────────────────────────────────

  // List documents for a vendor
  getVendorDocuments(tenantId: string, vendorId: string): Promise<VendorDocument[]> {
    return request<VendorDocument[]>(`/vendors/${vendorId}/documents`, tenantId)
  },

  // Upload a document (multipart/form-data)
  uploadDocument(tenantId: string, vendorId: string, file: File, documentType: string): Promise<VendorDocument> {
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', documentType)
    return request<VendorDocument>(`/vendors/${vendorId}/documents`, tenantId, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId },  // let browser set Content-Type with boundary
      body: form,
    })
  },

  // Delete a document
  deleteDocument(tenantId: string, _vendorId: string, documentId: string): Promise<void> {
    return request<void>(`/documents/${documentId}`, tenantId, { method: 'DELETE' })
  },

  // ── Monitoring ─────────────────────────────────────────────────────────────

  // Get monitoring events for a vendor
  getMonitoringEvents(tenantId: string, vendorId: string): Promise<MonitoringEvent[]> {
    return request<MonitoringEvent[]>(`/vendors/${vendorId}/monitoring-events`, tenantId)
  },

  // Get monitoring events across all vendors (portfolio-level)
  getAllMonitoringEvents(tenantId: string, params?: { severity?: string; limit?: number }): Promise<MonitoringEvent[]> {
    const qs = new URLSearchParams()
    if (params?.severity) qs.set('severity', params.severity)
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<MonitoringEvent[]>(`/monitoring/alerts${query}`, tenantId)
  },

  // Trigger an on-demand monitoring check for a vendor
  runMonitoringCheck(tenantId: string, vendorId: string): Promise<{ triggered: boolean }> {
    return request<{ triggered: boolean }>(
      `/vendors/${vendorId}/monitoring/run`,
      tenantId,
      { method: 'POST' },
    )
  },

  // ── Contracts ──────────────────────────────────────────────────────────────

  // List contracts for a vendor
  getVendorContracts(tenantId: string, vendorId: string): Promise<VendorContract[]> {
    return request<VendorContract[]>(`/vendors/${vendorId}/contracts`, tenantId)
  },

  // Get contracts expiring soon across all vendors (portfolio-level)
  getExpiringContracts(tenantId: string, days = 90): Promise<VendorContract[]> {
    return request<VendorContract[]>(`/contracts/expiring?days=${days}`, tenantId)
  },

  // Create a contract for a vendor
  createContract(tenantId: string, vendorId: string, contract: Omit<VendorContract, 'id' | 'vendor_id'>): Promise<VendorContract> {
    return request<VendorContract>(`/vendors/${vendorId}/contracts`, tenantId, {
      method: 'POST',
      body: JSON.stringify(contract),
    })
  },

  // Update a contract
  updateContract(tenantId: string, vendorId: string, contractId: string, patch: Partial<VendorContract>): Promise<VendorContract> {
    return request<VendorContract>(
      `/vendors/${vendorId}/contracts/${contractId}`,
      tenantId,
      { method: 'PATCH', body: JSON.stringify(patch) },
    )
  },

  // Delete a contract
  deleteContract(tenantId: string, vendorId: string, contractId: string): Promise<void> {
    return request<void>(
      `/vendors/${vendorId}/contracts/${contractId}`,
      tenantId,
      { method: 'DELETE' },
    )
  },

  // ── Fourth-Party ───────────────────────────────────────────────────────────

  // Get the fourth-party sub-processor graph for a vendor
  getFourthPartyGraph(tenantId: string, vendorId: string): Promise<FourthPartyGraph> {
    return request<FourthPartyGraph>(`/vendors/${vendorId}/fourth-party`, tenantId)
  },

  // Sync sub-processors from vendor's published profile
  syncFourthParty(tenantId: string, vendorId: string): Promise<FourthPartyGraph> {
    return request<FourthPartyGraph>(
      `/vendors/${vendorId}/fourth-party/sync`,
      tenantId,
      { method: 'POST' },
    )
  },

  // ── Portfolio ──────────────────────────────────────────────────────────────

  // Get vendors with reviews expiring soon
  getReviewCalendar(tenantId: string): Promise<Array<{ vendor_id: string; vendor_name: string; next_review_at: string; is_overdue: boolean }>> {
    return request('/vendors/expiring-reviews', tenantId)
  },
}
