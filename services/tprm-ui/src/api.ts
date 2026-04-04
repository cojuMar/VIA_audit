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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
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
    return request<Vendor[]>(`/tenants/${tenantId}/vendors`)
  },

  // Get a single vendor
  getVendor(tenantId: string, vendorId: string): Promise<Vendor> {
    return request<Vendor>(`/tenants/${tenantId}/vendors/${vendorId}`)
  },

  // Create a vendor via the intake form
  createVendor(tenantId: string, form: VendorIntakeForm): Promise<Vendor> {
    return request<Vendor>(`/tenants/${tenantId}/vendors`, {
      method: 'POST',
      body: JSON.stringify(form),
    })
  },

  // Update vendor fields
  updateVendor(tenantId: string, vendorId: string, patch: Partial<Vendor>): Promise<Vendor> {
    return request<Vendor>(`/tenants/${tenantId}/vendors/${vendorId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  },

  // Delete (offboard) a vendor
  deleteVendor(tenantId: string, vendorId: string): Promise<void> {
    return request<void>(`/tenants/${tenantId}/vendors/${vendorId}`, { method: 'DELETE' })
  },

  // Risk score history snapshots
  getVendorRiskHistory(tenantId: string, vendorId: string): Promise<Array<{ recorded_at: string; score: number; tier: string }>> {
    return request(`/tenants/${tenantId}/vendors/${vendorId}/risk-history`)
  },

  // ── Questionnaires ─────────────────────────────────────────────────────────

  // List available questionnaire templates
  getQuestionnaireTemplates(): Promise<QuestionnaireTemplate[]> {
    return request<QuestionnaireTemplate[]>('/questionnaire-templates')
  },

  // List questionnaires for a vendor
  getVendorQuestionnaires(tenantId: string, vendorId: string): Promise<VendorQuestionnaire[]> {
    return request<VendorQuestionnaire[]>(`/tenants/${tenantId}/vendors/${vendorId}/questionnaires`)
  },

  // Send a questionnaire to a vendor
  sendQuestionnaire(tenantId: string, vendorId: string, templateSlug: string): Promise<VendorQuestionnaire> {
    return request<VendorQuestionnaire>(`/tenants/${tenantId}/vendors/${vendorId}/questionnaires`, {
      method: 'POST',
      body: JSON.stringify({ template_slug: templateSlug }),
    })
  },

  // Get a single questionnaire
  getQuestionnaire(tenantId: string, vendorId: string, questionnaireId: string): Promise<VendorQuestionnaire> {
    return request<VendorQuestionnaire>(
      `/tenants/${tenantId}/vendors/${vendorId}/questionnaires/${questionnaireId}`,
    )
  },

  // ── Documents ──────────────────────────────────────────────────────────────

  // List documents for a vendor
  getVendorDocuments(tenantId: string, vendorId: string): Promise<VendorDocument[]> {
    return request<VendorDocument[]>(`/tenants/${tenantId}/vendors/${vendorId}/documents`)
  },

  // Upload a document (multipart/form-data)
  uploadDocument(tenantId: string, vendorId: string, file: File, documentType: string): Promise<VendorDocument> {
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', documentType)
    return request<VendorDocument>(`/tenants/${tenantId}/vendors/${vendorId}/documents`, {
      method: 'POST',
      headers: {},           // let browser set Content-Type with boundary
      body: form,
    })
  },

  // Delete a document
  deleteDocument(tenantId: string, vendorId: string, documentId: string): Promise<void> {
    return request<void>(
      `/tenants/${tenantId}/vendors/${vendorId}/documents/${documentId}`,
      { method: 'DELETE' },
    )
  },

  // ── Monitoring ─────────────────────────────────────────────────────────────

  // Get monitoring events for a vendor
  getMonitoringEvents(tenantId: string, vendorId: string): Promise<MonitoringEvent[]> {
    return request<MonitoringEvent[]>(`/tenants/${tenantId}/vendors/${vendorId}/monitoring`)
  },

  // Get monitoring events across all vendors (portfolio-level)
  getAllMonitoringEvents(tenantId: string, params?: { severity?: string; limit?: number }): Promise<MonitoringEvent[]> {
    const qs = new URLSearchParams()
    if (params?.severity) qs.set('severity', params.severity)
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<MonitoringEvent[]>(`/tenants/${tenantId}/monitoring${query}`)
  },

  // Trigger an on-demand monitoring check for a vendor
  runMonitoringCheck(tenantId: string, vendorId: string): Promise<{ triggered: boolean }> {
    return request<{ triggered: boolean }>(
      `/tenants/${tenantId}/vendors/${vendorId}/monitoring/check`,
      { method: 'POST' },
    )
  },

  // ── Contracts ──────────────────────────────────────────────────────────────

  // List contracts for a vendor
  getVendorContracts(tenantId: string, vendorId: string): Promise<VendorContract[]> {
    return request<VendorContract[]>(`/tenants/${tenantId}/vendors/${vendorId}/contracts`)
  },

  // Get contracts expiring soon across all vendors (portfolio-level)
  getExpiringContracts(tenantId: string, days = 90): Promise<VendorContract[]> {
    return request<VendorContract[]>(`/tenants/${tenantId}/contracts/expiring?days=${days}`)
  },

  // Create a contract for a vendor
  createContract(tenantId: string, vendorId: string, contract: Omit<VendorContract, 'id' | 'vendor_id'>): Promise<VendorContract> {
    return request<VendorContract>(`/tenants/${tenantId}/vendors/${vendorId}/contracts`, {
      method: 'POST',
      body: JSON.stringify(contract),
    })
  },

  // Update a contract
  updateContract(tenantId: string, vendorId: string, contractId: string, patch: Partial<VendorContract>): Promise<VendorContract> {
    return request<VendorContract>(
      `/tenants/${tenantId}/vendors/${vendorId}/contracts/${contractId}`,
      { method: 'PATCH', body: JSON.stringify(patch) },
    )
  },

  // Delete a contract
  deleteContract(tenantId: string, vendorId: string, contractId: string): Promise<void> {
    return request<void>(
      `/tenants/${tenantId}/vendors/${vendorId}/contracts/${contractId}`,
      { method: 'DELETE' },
    )
  },

  // ── Fourth-Party ───────────────────────────────────────────────────────────

  // Get the fourth-party sub-processor graph for a vendor
  getFourthPartyGraph(tenantId: string, vendorId: string): Promise<FourthPartyGraph> {
    return request<FourthPartyGraph>(
      `/tenants/${tenantId}/vendors/${vendorId}/fourth-party`,
    )
  },

  // Sync sub-processors from vendor's published profile
  syncFourthParty(tenantId: string, vendorId: string): Promise<FourthPartyGraph> {
    return request<FourthPartyGraph>(
      `/tenants/${tenantId}/vendors/${vendorId}/fourth-party/sync`,
      { method: 'POST' },
    )
  },

  // ── Portfolio ──────────────────────────────────────────────────────────────

  // Get overdue + due-soon review calendar entries
  getReviewCalendar(tenantId: string): Promise<Array<{ vendor_id: string; vendor_name: string; next_review_at: string; is_overdue: boolean }>> {
    return request(`/tenants/${tenantId}/review-calendar`)
  },
}
