import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Cloud,
  Server,
  Users,
  Database,
  DollarSign,
  Cpu,
  Package,
  FileText,
  Shield,
  Activity,
  FileCheck,
  GitBranch,
  UploadCloud,
  PlusCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  Clock,
  ExternalLink,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { api } from '../api'
import type { Vendor, VendorQuestionnaire, VendorDocument, MonitoringEvent, VendorContract } from '../types'

interface VendorRiskDashboardProps {
  tenantId: string
  vendorId: string
  onBack: () => void
}

type Tab = 'overview' | 'questionnaires' | 'documents' | 'monitoring' | 'contracts' | 'fourth-party'

const TYPE_ICONS: Record<Vendor['vendor_type'], React.ReactNode> = {
  saas: <Cloud className="w-4 h-4" />,
  infrastructure: <Server className="w-4 h-4" />,
  professional_services: <Users className="w-4 h-4" />,
  data_processor: <Database className="w-4 h-4" />,
  financial: <DollarSign className="w-4 h-4" />,
  hardware: <Cpu className="w-4 h-4" />,
  other: <Package className="w-4 h-4" />,
}

const RISK_TIER_STYLES: Record<Vendor['risk_tier'], string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-green-100 text-green-700 border-green-200',
  unrated: 'bg-gray-100 text-gray-600 border-gray-200',
}

const SEVERITY_BORDER: Record<MonitoringEvent['severity'], string> = {
  critical: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-amber-500',
  low: 'border-l-green-500',
  info: 'border-l-blue-500',
}

const SEVERITY_BG: Record<MonitoringEvent['severity'], string> = {
  critical: 'bg-red-50',
  high: 'bg-orange-50',
  medium: 'bg-amber-50',
  low: 'bg-green-50',
  info: 'bg-blue-50',
}

const SEVERITY_BADGE: Record<MonitoringEvent['severity'], string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-green-100 text-green-700',
  info: 'bg-blue-100 text-blue-700',
}

const Q_STATUS_STYLES: Record<VendorQuestionnaire['status'], string> = {
  draft: 'bg-gray-100 text-gray-600',
  sent: 'bg-blue-100 text-blue-700',
  in_progress: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  expired: 'bg-red-100 text-red-600',
}

const ANALYSIS_STYLES: Record<VendorDocument['analysis_status'], string> = {
  pending: 'bg-gray-100 text-gray-500',
  analyzing: 'bg-blue-100 text-blue-600',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-600',
}

function daysUntil(dateStr: string): number {
  const now = new Date()
  const target = new Date(dateStr)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function ScoreGauge({ score, tier }: { score: number; tier: Vendor['risk_tier'] }) {
  const pct = Math.min((score / 10) * 100, 100)
  const colors: Record<Vendor['risk_tier'], string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#f59e0b',
    low: '#22c55e',
    unrated: '#9ca3af',
  }
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative inline-flex items-center justify-center w-20 h-20 rounded-full"
        style={{ background: `conic-gradient(${colors[tier]} ${pct}%, #e5e7eb ${pct}%)` }}
      >
        <div className="absolute inset-2 bg-white rounded-full flex flex-col items-center justify-center">
          <span className="text-lg font-bold text-gray-900">{score.toFixed(1)}</span>
          <span className="text-xs text-gray-400 leading-none">/10</span>
        </div>
      </div>
    </div>
  )
}

export function VendorRiskDashboard({ tenantId, vendorId, onBack }: VendorRiskDashboardProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [expandedQId, setExpandedQId] = useState<string | null>(null)
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null)
  const [showTemplateDropdown, setShowTemplateDropdown] = useState(false)
  const [sendingTemplate, setSendingTemplate] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadDocType, setUploadDocType] = useState('security_assessment')
  const queryClient = useQueryClient()

  const { data: vendor, isLoading: loadingVendor } = useQuery({
    queryKey: ['vendor', tenantId, vendorId],
    queryFn: () => api.getVendor(tenantId, vendorId),
  })

  const { data: riskHistory = [] } = useQuery({
    queryKey: ['vendor-risk-history', tenantId, vendorId],
    queryFn: () => api.getVendorRiskHistory(tenantId, vendorId),
    enabled: activeTab === 'overview',
  })

  const { data: questionnaires = [] } = useQuery({
    queryKey: ['vendor-questionnaires', tenantId, vendorId],
    queryFn: () => api.getVendorQuestionnaires(tenantId, vendorId),
    enabled: activeTab === 'questionnaires',
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: () => api.getQuestionnaireTemplates(),
    enabled: activeTab === 'questionnaires',
  })

  const { data: documents = [] } = useQuery({
    queryKey: ['vendor-documents', tenantId, vendorId],
    queryFn: () => api.getVendorDocuments(tenantId, vendorId),
    enabled: activeTab === 'documents',
  })

  const { data: monitoringEvents = [] } = useQuery({
    queryKey: ['vendor-monitoring', tenantId, vendorId],
    queryFn: () => api.getMonitoringEvents(tenantId, vendorId),
    enabled: activeTab === 'monitoring',
  })

  const { data: contracts = [] } = useQuery({
    queryKey: ['vendor-contracts', tenantId, vendorId],
    queryFn: () => api.getVendorContracts(tenantId, vendorId),
    enabled: activeTab === 'contracts',
  })

  const { data: fourthParty } = useQuery({
    queryKey: ['vendor-fourth-party', tenantId, vendorId],
    queryFn: () => api.getFourthPartyGraph(tenantId, vendorId),
    enabled: activeTab === 'fourth-party',
  })

  const sendQuestionnaireMutation = useMutation({
    mutationFn: (templateSlug: string) => api.sendQuestionnaire(tenantId, vendorId, templateSlug),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vendor-questionnaires', tenantId, vendorId] })
      setShowTemplateDropdown(false)
      setSendingTemplate(null)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ file, docType }: { file: File; docType: string }) =>
      api.uploadDocument(tenantId, vendorId, file, docType),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vendor-documents', tenantId, vendorId] })
    },
  })

  const monitoringCheckMutation = useMutation({
    mutationFn: () => api.runMonitoringCheck(tenantId, vendorId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vendor-monitoring', tenantId, vendorId] })
    },
  })

  const syncFourthPartyMutation = useMutation({
    mutationFn: () => api.syncFourthParty(tenantId, vendorId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vendor-fourth-party', tenantId, vendorId] })
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate({ file, docType: uploadDocType })
  }

  if (loadingVendor || !vendor) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading vendor...</div>
  }

  const scoreHistoryData = (riskHistory ?? []).map(r => ({
    date: new Date(r.recorded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    score: r.score,
  }))

  const TABS: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
    { id: 'overview', label: 'Overview', icon: <Shield className="w-4 h-4" /> },
    { id: 'questionnaires', label: 'Questionnaires', icon: <FileCheck className="w-4 h-4" /> },
    { id: 'documents', label: 'Documents', icon: <FileText className="w-4 h-4" /> },
    { id: 'monitoring', label: 'Monitoring', icon: <Activity className="w-4 h-4" /> },
    { id: 'contracts', label: 'Contracts', icon: <FileText className="w-4 h-4" /> },
    { id: 'fourth-party', label: 'Fourth-Party', icon: <GitBranch className="w-4 h-4" /> },
  ]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={onBack}
          className="mt-1 p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-gray-900">{vendor.name}</h1>
            <span className="flex items-center gap-1.5 text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full border border-gray-200">
              {TYPE_ICONS[vendor.vendor_type]}
              {vendor.vendor_type.replace(/_/g, ' ')}
            </span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${RISK_TIER_STYLES[vendor.risk_tier]}`}>
              {vendor.risk_tier.charAt(0).toUpperCase() + vendor.risk_tier.slice(1)} Risk
            </span>
            <span className="text-xs text-gray-500 bg-gray-50 border border-gray-200 px-2 py-0.5 rounded-full">
              {vendor.status === 'under_review' ? 'Under Review' : vendor.status.charAt(0).toUpperCase() + vendor.status.slice(1)}
            </span>
          </div>
          {vendor.website && (
            <a href={vendor.website} target="_blank" rel="noopener noreferrer"
              className="text-xs text-blue-500 hover:underline flex items-center gap-1 mt-0.5">
              {vendor.website} <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
        {vendor.inherent_risk_score !== undefined && (
          <ScoreGauge score={vendor.inherent_risk_score} tier={vendor.risk_tier} />
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0 -mb-px overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Overview ── */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          {/* Quick actions */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveTab('questionnaires')}
              className="flex items-center gap-1.5 text-xs font-medium border border-blue-200 text-blue-600 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors"
            >
              <FileCheck className="w-3.5 h-3.5" />
              Send Questionnaire
            </button>
            <button
              onClick={() => { setActiveTab('documents'); fileInputRef.current?.click() }}
              className="flex items-center gap-1.5 text-xs font-medium border border-indigo-200 text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              Upload Document
            </button>
            <button
              onClick={() => setActiveTab('contracts')}
              className="flex items-center gap-1.5 text-xs font-medium border border-green-200 text-green-600 bg-green-50 hover:bg-green-100 px-3 py-1.5 rounded-lg transition-colors"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              Add Contract
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Risk score history */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Risk Score History</h3>
              {scoreHistoryData.length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={scoreHistoryData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="score" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-32 text-gray-400 text-sm">No score history yet</div>
              )}
            </div>

            {/* Data sensitivity */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm space-y-3">
              <h3 className="text-sm font-semibold text-gray-900">Data Sensitivity</h3>
              <div className="flex flex-wrap gap-2">
                {vendor.processes_pii && (
                  <div className="flex items-center gap-1.5 text-sm bg-blue-50 text-blue-700 border border-blue-200 px-3 py-1.5 rounded-lg font-medium">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    Processes PII
                  </div>
                )}
                {vendor.processes_phi && (
                  <div className="flex items-center gap-1.5 text-sm bg-red-50 text-red-700 border border-red-200 px-3 py-1.5 rounded-lg font-medium">
                    <span className="w-2 h-2 rounded-full bg-red-500" />
                    Processes PHI
                  </div>
                )}
                {vendor.processes_pci && (
                  <div className="flex items-center gap-1.5 text-sm bg-purple-50 text-purple-700 border border-purple-200 px-3 py-1.5 rounded-lg font-medium">
                    <span className="w-2 h-2 rounded-full bg-purple-500" />
                    Processes PCI
                  </div>
                )}
                {vendor.uses_ai && (
                  <div className="flex items-center gap-1.5 text-sm bg-indigo-50 text-indigo-700 border border-indigo-200 px-3 py-1.5 rounded-lg font-medium">
                    <span className="w-2 h-2 rounded-full bg-indigo-500" />
                    Uses AI
                  </div>
                )}
              </div>
              {(vendor.data_types_processed ?? []).length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Data types processed</p>
                  <div className="flex flex-wrap gap-1">
                    {(vendor.data_types_processed ?? []).map(dt => (
                      <span key={dt} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{dt}</span>
                    ))}
                  </div>
                </div>
              )}
              {vendor.residual_risk_score !== undefined && (
                <div className="pt-2 border-t border-gray-100">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Residual Risk Score</span>
                    <span className="font-semibold text-gray-900">{vendor.residual_risk_score.toFixed(1)} / 10</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Questionnaires ── */}
      {activeTab === 'questionnaires' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Questionnaires</h3>
            <div className="relative">
              <button
                onClick={() => setShowTemplateDropdown(p => !p)}
                className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
              >
                <PlusCircle className="w-4 h-4" />
                Send New Questionnaire
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
              {showTemplateDropdown && (
                <div className="absolute right-0 mt-1 w-72 bg-white border border-gray-200 rounded-xl shadow-lg z-20">
                  {templates.length === 0 ? (
                    <p className="px-4 py-3 text-sm text-gray-400">No templates available</p>
                  ) : (
                    templates.map(t => (
                      <button
                        key={t.slug}
                        onClick={() => {
                          setSendingTemplate(t.slug)
                          sendQuestionnaireMutation.mutate(t.slug)
                        }}
                        disabled={sendingTemplate === t.slug}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-0 disabled:opacity-50"
                      >
                        <p className="text-sm font-medium text-gray-900">{t.name}</p>
                        <p className="text-xs text-gray-500">{t.question_count} questions · ~{t.estimated_minutes} min</p>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {questionnaires.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No questionnaires sent yet</div>
          ) : (
            <div className="space-y-3">
              {questionnaires.map(q => {
                const isExpanded = expandedQId === q.id
                return (
                  <div key={q.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors"
                      onClick={() => setExpandedQId(isExpanded ? null : q.id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${Q_STATUS_STYLES[q.status]}`}>
                          {q.status.replace('_', ' ')}
                        </span>
                        <span className="text-sm font-medium text-gray-900 truncate">{q.template_slug}</span>
                        {q.ai_score !== undefined && (
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                            q.ai_score >= 7 ? 'bg-green-100 text-green-700' :
                            q.ai_score >= 4 ? 'bg-amber-100 text-amber-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            AI: {q.ai_score.toFixed(1)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-400 shrink-0">
                        {q.completed_at && <span>Completed {new Date(q.completed_at).toLocaleDateString()}</span>}
                        {q.due_date && !q.completed_at && <span>Due {new Date(q.due_date).toLocaleDateString()}</span>}
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </div>
                    </div>
                    {isExpanded && q.ai_summary && (
                      <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                        <p className="text-xs font-medium text-gray-500 mb-1">AI Summary</p>
                        <p className="text-sm text-gray-700">{q.ai_summary}</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Documents ── */}
      {activeTab === 'documents' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Documents</h3>
          </div>

          {/* Drag-and-drop upload area */}
          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center hover:border-blue-400 transition-colors cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              const file = e.dataTransfer.files[0]
              if (file) uploadMutation.mutate({ file, docType: uploadDocType })
            }}
          >
            <UploadCloud className="w-8 h-8 text-gray-400 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-600">Drop a document here or click to upload</p>
            <p className="text-xs text-gray-400 mt-1">SOC 2, ISO 27001, Pen Test, Privacy Policy, DPA, etc.</p>
            <div className="mt-3 flex items-center justify-center gap-2">
              <label className="text-xs text-gray-500">Type:</label>
              <select
                value={uploadDocType}
                onChange={e => { e.stopPropagation(); setUploadDocType(e.target.value) }}
                onClick={e => e.stopPropagation()}
                className="text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                {['security_assessment', 'soc2_report', 'iso27001_cert', 'pen_test', 'privacy_policy', 'dpa', 'other'].map(t => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))}
              </select>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.doc,.docx,.txt"
              onChange={handleFileChange}
            />
          </div>

          {uploadMutation.isPending && (
            <div className="text-center text-sm text-blue-600 animate-pulse">Uploading and analyzing...</div>
          )}

          {documents.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No documents uploaded yet</div>
          ) : (
            <div className="space-y-3">
              {documents.map(doc => {
                const isExpanded = expandedDocId === doc.id
                const expired = doc.expiry_date && daysUntil(doc.expiry_date) < 0
                const expiringSoon = doc.expiry_date && !expired && daysUntil(doc.expiry_date) <= 30

                return (
                  <div key={doc.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors"
                      onClick={() => setExpandedDocId(isExpanded ? null : doc.id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText className="w-5 h-5 text-gray-400 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
                          <p className="text-xs text-gray-400">
                            {doc.document_type.replace(/_/g, ' ')} · {doc.file_size_bytes ? formatBytes(doc.file_size_bytes) : ''} · Uploaded {new Date(doc.upload_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {doc.expiry_date && (
                          <span className={`text-xs font-medium ${expired ? 'text-red-600' : expiringSoon ? 'text-amber-600' : 'text-gray-400'}`}>
                            {expired ? 'Expired' : `Expires ${new Date(doc.expiry_date).toLocaleDateString()}`}
                          </span>
                        )}
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ANALYSIS_STYLES[doc.analysis_status]}`}>
                          {doc.analysis_status}
                        </span>
                        {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                      </div>
                    </div>
                    {isExpanded && doc.ai_analysis && (
                      <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-gray-500">AI Analysis</p>
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                            doc.ai_analysis.score >= 7 ? 'bg-green-100 text-green-700' :
                            doc.ai_analysis.score >= 4 ? 'bg-amber-100 text-amber-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            Score: {doc.ai_analysis.score.toFixed(1)}
                          </span>
                        </div>
                        <p className="text-sm text-gray-700">{doc.ai_analysis.summary}</p>
                        {(doc.ai_analysis.certifications_found ?? []).length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {(doc.ai_analysis.certifications_found ?? []).map(c => (
                              <span key={c} className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded">
                                <CheckCircle className="w-3 h-3 inline mr-1" />{c}
                              </span>
                            ))}
                          </div>
                        )}
                        {(doc.ai_analysis.gaps ?? []).length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-red-600 mb-1">Gaps identified</p>
                            <ul className="space-y-1">
                              {(doc.ai_analysis.gaps ?? []).map((gap, i) => (
                                <li key={i} className="text-xs text-gray-700 flex items-start gap-1.5">
                                  <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0 mt-0.5" />
                                  {gap}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Monitoring ── */}
      {activeTab === 'monitoring' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Monitoring Events</h3>
            <button
              onClick={() => monitoringCheckMutation.mutate()}
              disabled={monitoringCheckMutation.isPending}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${monitoringCheckMutation.isPending ? 'animate-spin' : ''}`} />
              Run Monitoring Check
            </button>
          </div>

          {monitoringEvents.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No monitoring events</div>
          ) : (
            <div className="space-y-3">
              {[...monitoringEvents]
                .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                .map(event => (
                  <div key={event.id} className={`border-l-4 rounded-xl border border-gray-200 shadow-sm overflow-hidden ${SEVERITY_BORDER[event.severity]} ${SEVERITY_BG[event.severity]}`}>
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 min-w-0">
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${SEVERITY_BADGE[event.severity]}`}>
                            {event.severity.toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900">{event.title}</p>
                            {event.description && <p className="text-xs text-gray-600 mt-0.5">{event.description}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs bg-white border border-gray-200 px-2 py-0.5 rounded font-medium text-gray-600">
                            {event.event_source}
                          </span>
                          <span className="text-xs text-gray-400">
                            {new Date(event.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                      {event.source_url && (
                        <a href={event.source_url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline mt-1.5">
                          View source <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      {/* ── Contracts ── */}
      {activeTab === 'contracts' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Contracts</h3>
            <button className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors">
              <PlusCircle className="w-4 h-4" />
              Add Contract
            </button>
          </div>

          {contracts.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No contracts recorded</div>
          ) : (
            <div className="space-y-3">
              {contracts.map(contract => {
                const daysLeft = contract.expiry_date ? daysUntil(contract.expiry_date) : null
                const expiringSoon = daysLeft !== null && daysLeft >= 0 && daysLeft <= 30
                const expired = daysLeft !== null && daysLeft < 0

                return (
                  <div key={contract.id} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{contract.title}</p>
                        <p className="text-xs text-gray-500">{contract.contract_type}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {contract.auto_renews && (
                          <span className="text-xs bg-blue-50 text-blue-600 border border-blue-200 px-2 py-0.5 rounded font-medium">
                            Auto-renews
                          </span>
                        )}
                        {daysLeft !== null && (
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                            expired ? 'bg-red-100 text-red-700' :
                            expiringSoon ? 'bg-amber-100 text-amber-700' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {expired ? `Expired ${Math.abs(daysLeft)}d ago` :
                             expiringSoon ? `Expires in ${daysLeft}d` :
                             `${daysLeft}d remaining`}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                      {contract.effective_date && (
                        <div>
                          <p className="text-gray-400">Effective</p>
                          <p className="font-medium text-gray-700">{new Date(contract.effective_date).toLocaleDateString()}</p>
                        </div>
                      )}
                      {contract.expiry_date && (
                        <div>
                          <p className="text-gray-400">Expires</p>
                          <p className={`font-medium ${expired ? 'text-red-600' : expiringSoon ? 'text-amber-600' : 'text-gray-700'}`}>
                            {new Date(contract.expiry_date).toLocaleDateString()}
                          </p>
                        </div>
                      )}
                      {contract.contract_value !== undefined && (
                        <div>
                          <p className="text-gray-400">Value</p>
                          <p className="font-medium text-gray-700">
                            {contract.contract_value.toLocaleString()} {contract.currency}
                          </p>
                        </div>
                      )}
                      {contract.renewal_notice_days > 0 && (
                        <div>
                          <p className="text-gray-400">Renewal Notice</p>
                          <p className="font-medium text-gray-700">{contract.renewal_notice_days} days</p>
                        </div>
                      )}
                    </div>

                    {Object.keys(contract.sla_commitments).length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-gray-500 mb-1">SLA Commitments</p>
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(contract.sla_commitments).map(([key, val]) => (
                            <span key={key} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                              {key}: {String(val)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Fourth-Party ── */}
      {activeTab === 'fourth-party' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Fourth-Party Sub-processors</h3>
            <button
              onClick={() => syncFourthPartyMutation.mutate()}
              disabled={syncFourthPartyMutation.isPending}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncFourthPartyMutation.isPending ? 'animate-spin' : ''}`} />
              Sync from Vendor Profile
            </button>
          </div>

          {!fourthParty || Object.keys(fourthParty).length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">No fourth-party data available</div>
          ) : (
            <div className="space-y-4">
              {Object.entries(fourthParty).map(([vendorName, subProcessors]) => (
                <div key={vendorName} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <GitBranch className="w-4 h-4 text-gray-400" />
                    <p className="text-sm font-semibold text-gray-900">{vendorName}</p>
                    <span className="text-xs text-gray-400">→ {subProcessors.length} sub-processor{subProcessors.length !== 1 ? 's' : ''}</span>
                  </div>
                  <div className="space-y-2 pl-6">
                    {subProcessors.map(sp => {
                      const spTier = sp.risk_tier as Vendor['risk_tier']
                      return (
                        <div key={sp.name} className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                            <span className="text-sm text-gray-700">{sp.name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${RISK_TIER_STYLES[spTier] ?? RISK_TIER_STYLES.unrated}`}>
                              {sp.risk_tier}
                            </span>
                            {sp.is_verified ? (
                              <span className="text-xs flex items-center gap-1 text-green-600">
                                <CheckCircle className="w-3 h-3" /> Verified
                              </span>
                            ) : (
                              <span className="text-xs flex items-center gap-1 text-gray-400">
                                <Clock className="w-3 h-3" /> Unverified
                              </span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Close dropdown on outside click */}
      {showTemplateDropdown && (
        <div className="fixed inset-0 z-10" onClick={() => setShowTemplateDropdown(false)} />
      )}
    </div>
  )
}

