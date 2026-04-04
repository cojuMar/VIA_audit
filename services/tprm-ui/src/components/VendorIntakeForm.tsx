import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Cloud,
  Server,
  Users,
  Database,
  DollarSign,
  Cpu,
  Package,
  X,
  ChevronRight,
  ChevronLeft,
  Plus,
  AlertTriangle,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { api } from '../api'
import type { VendorIntakeForm as VendorIntakeFormType, Vendor } from '../types'

interface VendorIntakeFormProps {
  tenantId: string
  onComplete: (vendorId: string) => void
  onCancel: () => void
}

const VENDOR_TYPES: Array<{ value: Vendor['vendor_type']; label: string; icon: React.ReactNode }> = [
  { value: 'saas', label: 'SaaS', icon: <Cloud className="w-4 h-4" /> },
  { value: 'infrastructure', label: 'Infrastructure', icon: <Server className="w-4 h-4" /> },
  { value: 'professional_services', label: 'Professional Services', icon: <Users className="w-4 h-4" /> },
  { value: 'data_processor', label: 'Data Processor', icon: <Database className="w-4 h-4" /> },
  { value: 'financial', label: 'Financial', icon: <DollarSign className="w-4 h-4" /> },
  { value: 'hardware', label: 'Hardware', icon: <Cpu className="w-4 h-4" /> },
  { value: 'other', label: 'Other', icon: <Package className="w-4 h-4" /> },
]

const INTEGRATION_DEPTHS: Array<{
  value: VendorIntakeFormType['integrations_depth']
  label: string
  desc: string
  riskDelta: number
}> = [
  { value: 'none', label: 'None', desc: 'No system integration', riskDelta: 0 },
  { value: 'read_only', label: 'Read-Only', desc: 'Can read data only', riskDelta: 1 },
  { value: 'read_write', label: 'Read-Write', desc: 'Can read and modify data', riskDelta: 2 },
  { value: 'admin', label: 'Admin', desc: 'Administrative access to systems', riskDelta: 3 },
  { value: 'core_infrastructure', label: 'Core Infrastructure', desc: 'Critical path dependency', riskDelta: 4 },
]

const DATA_TYPES = [
  'Financial Data',
  'PII',
  'PHI',
  'PCI Card Data',
  'Authentication Credentials',
  'IP / Source Code',
  'Employee Data',
  'Legal Data',
  'Other',
]

// ── Risk score rubric (mirrors vendor_intake.py) ──────────────────────────

interface ScoreFactors {
  integration_depth: number
  data_sensitivity: number
  pii: number
  phi: number
  pci: number
  ai_usage: number
  sub_processors: number
}

function computeRiskScore(form: VendorIntakeFormType): { total: number; factors: ScoreFactors; tier: Vendor['risk_tier'] } {
  const depthMap: Record<VendorIntakeFormType['integrations_depth'], number> = {
    none: 0,
    read_only: 1.0,
    read_write: 2.0,
    admin: 3.0,
    core_infrastructure: 4.0,
  }

  const factors: ScoreFactors = {
    integration_depth: depthMap[form.integrations_depth],
    data_sensitivity: Math.min(form.data_types_processed.length * 0.3, 2.0),
    pii: form.processes_pii ? 1.0 : 0,
    phi: form.processes_phi ? 1.5 : 0,
    pci: form.processes_pci ? 1.5 : 0,
    ai_usage: form.uses_ai ? 0.5 : 0,
    sub_processors: Math.min(form.sub_processors.length * 0.2, 1.0),
  }

  const total = Math.min(
    Object.values(factors).reduce((a, b) => a + b, 0),
    10,
  )

  let tier: Vendor['risk_tier']
  if (total >= 8) tier = 'critical'
  else if (total >= 6) tier = 'high'
  else if (total >= 4) tier = 'medium'
  else if (total > 0) tier = 'low'
  else tier = 'unrated'

  return { total, factors, tier }
}

function recommendedQuestionnaire(tier: Vendor['risk_tier']): string {
  if (tier === 'critical') return 'Full TPRM Assessment (SIG Core)'
  if (tier === 'high') return 'Abbreviated TPRM Assessment (SIG Lite)'
  if (tier === 'medium') return 'Security Questionnaire (Standard)'
  return 'Basic Vendor Profile'
}

const TIER_STYLES: Record<Vendor['risk_tier'], string> = {
  critical: 'bg-red-100 text-red-700 border-red-300',
  high: 'bg-orange-100 text-orange-700 border-orange-300',
  medium: 'bg-amber-100 text-amber-700 border-amber-300',
  low: 'bg-green-100 text-green-700 border-green-300',
  unrated: 'bg-gray-100 text-gray-600 border-gray-300',
}

const FACTOR_COLORS: Record<keyof ScoreFactors, string> = {
  integration_depth: '#3b82f6',
  data_sensitivity: '#8b5cf6',
  pii: '#06b6d4',
  phi: '#ef4444',
  pci: '#a855f7',
  ai_usage: '#6366f1',
  sub_processors: '#f59e0b',
}

const FACTOR_LABELS: Record<keyof ScoreFactors, string> = {
  integration_depth: 'Integration Depth',
  data_sensitivity: 'Data Sensitivity',
  pii: 'PII Processing',
  phi: 'PHI Processing',
  pci: 'PCI Processing',
  ai_usage: 'AI Usage',
  sub_processors: 'Sub-processors',
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center justify-between cursor-pointer gap-3">
      <span className="text-sm text-gray-700">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-gray-200'}`}
      >
        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4.5' : 'translate-x-0.5'}`} />
      </button>
    </label>
  )
}

const EMPTY_FORM: VendorIntakeFormType = {
  name: '',
  vendor_type: 'saas',
  website: '',
  description: '',
  primary_contact_name: '',
  primary_contact_email: '',
  data_types_processed: [],
  integrations_depth: 'none',
  processes_pii: false,
  processes_phi: false,
  processes_pci: false,
  uses_ai: false,
  sub_processors: [],
}

export function VendorIntakeForm({ tenantId, onComplete, onCancel }: VendorIntakeFormProps) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<VendorIntakeFormType>(EMPTY_FORM)
  const [subProcessorInput, setSubProcessorInput] = useState('')
  const [errors, setErrors] = useState<Partial<Record<keyof VendorIntakeFormType, string>>>({})

  const mutation = useMutation({
    mutationFn: () => api.createVendor(tenantId, form),
    onSuccess: vendor => onComplete(vendor.id),
  })

  const { total, factors, tier } = computeRiskScore(form)

  function update<K extends keyof VendorIntakeFormType>(key: K, value: VendorIntakeFormType[K]) {
    setForm(prev => ({ ...prev, [key]: value }))
    setErrors(prev => ({ ...prev, [key]: undefined }))
  }

  function validateStep1(): boolean {
    const errs: typeof errors = {}
    if (!form.name.trim()) errs.name = 'Vendor name is required'
    if (form.primary_contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.primary_contact_email)) {
      errs.primary_contact_email = 'Invalid email address'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  function nextStep() {
    if (step === 1 && !validateStep1()) return
    setStep(s => s + 1)
  }

  function toggleDataType(dt: string) {
    const current = form.data_types_processed
    update(
      'data_types_processed',
      current.includes(dt) ? current.filter(x => x !== dt) : [...current, dt],
    )
  }

  function addSubProcessor() {
    const val = subProcessorInput.trim()
    if (val && !form.sub_processors.includes(val)) {
      update('sub_processors', [...form.sub_processors, val])
    }
    setSubProcessorInput('')
  }

  function removeSubProcessor(sp: string) {
    update('sub_processors', form.sub_processors.filter(x => x !== sp))
  }

  const chartData = (Object.entries(factors) as Array<[keyof ScoreFactors, number]>)
    .filter(([, v]) => v > 0)
    .map(([key, value]) => ({ name: FACTOR_LABELS[key], value: parseFloat(value.toFixed(2)), color: FACTOR_COLORS[key] }))

  const STEPS = ['Basic Info', 'Data & Integration', 'Preview & Submit']

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Add New Vendor</h2>
          <p className="text-sm text-gray-500">Step {step} of 3 — {STEPS[step - 1]}</p>
        </div>
        <button onClick={onCancel} className="text-gray-400 hover:text-gray-600 transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Step indicators */}
      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold border-2 shrink-0 ${
              i + 1 < step ? 'bg-blue-600 border-blue-600 text-white' :
              i + 1 === step ? 'border-blue-600 text-blue-600 bg-blue-50' :
              'border-gray-200 text-gray-400'
            }`}>
              {i + 1 < step ? '✓' : i + 1}
            </div>
            <span className={`text-xs hidden sm:block ${i + 1 === step ? 'text-blue-600 font-medium' : 'text-gray-400'}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && <div className={`flex-1 h-px ${i + 1 < step ? 'bg-blue-300' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* Step 1: Basic Info */}
      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Vendor Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={e => update('name', e.target.value)}
              placeholder="Acme Corp"
              className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${errors.name ? 'border-red-400' : 'border-gray-200'}`}
            />
            {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Vendor Type</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {VENDOR_TYPES.map(vt => (
                <button
                  key={vt.value}
                  type="button"
                  onClick={() => update('vendor_type', vt.value)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
                    form.vendor_type === vt.value
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {vt.icon}
                  {vt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Website</label>
              <input
                type="url"
                value={form.website ?? ''}
                onChange={e => update('website', e.target.value)}
                placeholder="https://example.com"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Primary Contact Name</label>
              <input
                type="text"
                value={form.primary_contact_name ?? ''}
                onChange={e => update('primary_contact_name', e.target.value)}
                placeholder="Jane Smith"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Primary Contact Email</label>
            <input
              type="email"
              value={form.primary_contact_email ?? ''}
              onChange={e => update('primary_contact_email', e.target.value)}
              placeholder="security@vendor.com"
              className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${errors.primary_contact_email ? 'border-red-400' : 'border-gray-200'}`}
            />
            {errors.primary_contact_email && <p className="text-xs text-red-500 mt-1">{errors.primary_contact_email}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={form.description ?? ''}
              onChange={e => update('description', e.target.value)}
              rows={3}
              placeholder="Brief description of what this vendor provides..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Step 2: Data & Integration */}
      {step === 2 && (
        <div className="space-y-5">
          {/* Live score preview banner */}
          <div className={`flex items-center justify-between px-4 py-2 rounded-lg border text-sm font-medium ${TIER_STYLES[tier]}`}>
            <span>Live Risk Score</span>
            <span className="text-lg font-bold">{total.toFixed(1)} / 10 — {tier.charAt(0).toUpperCase() + tier.slice(1)}</span>
          </div>

          {/* Integration Depth */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Integration Depth</label>
            <div className="space-y-2">
              {INTEGRATION_DEPTHS.map(opt => (
                <label
                  key={opt.value}
                  className={`flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors ${
                    form.integrations_depth === opt.value
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="integrations_depth"
                      value={opt.value}
                      checked={form.integrations_depth === opt.value}
                      onChange={() => update('integrations_depth', opt.value)}
                      className="text-blue-600"
                    />
                    <div>
                      <p className="text-sm font-medium text-gray-800">{opt.label}</p>
                      <p className="text-xs text-gray-500">{opt.desc}</p>
                    </div>
                  </div>
                  {opt.riskDelta > 0 && (
                    <span className="text-xs text-orange-600 font-medium shrink-0">+{opt.riskDelta} risk</span>
                  )}
                </label>
              ))}
            </div>
          </div>

          {/* Data types */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Data Types Processed</label>
            <div className="flex flex-wrap gap-2">
              {DATA_TYPES.map(dt => (
                <button
                  key={dt}
                  type="button"
                  onClick={() => toggleDataType(dt)}
                  className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-colors ${
                    form.data_types_processed.includes(dt)
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                  }`}
                >
                  {dt}
                </button>
              ))}
            </div>
          </div>

          {/* Toggles */}
          <div className="space-y-3 border border-gray-100 rounded-xl p-4 bg-gray-50">
            <p className="text-sm font-medium text-gray-700 mb-1">Sensitive Data Processing</p>
            <Toggle checked={form.processes_pii} onChange={v => update('processes_pii', v)} label="Processes PII (Personally Identifiable Information)" />
            <Toggle checked={form.processes_phi} onChange={v => update('processes_phi', v)} label="Processes PHI (Protected Health Information)" />
            <Toggle checked={form.processes_pci} onChange={v => update('processes_pci', v)} label="Processes PCI Card Data" />
            <Toggle checked={form.uses_ai} onChange={v => update('uses_ai', v)} label="Uses AI / ML in their service" />
          </div>

          {/* Sub-processors */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Sub-processors</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={subProcessorInput}
                onChange={e => setSubProcessorInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSubProcessor() } }}
                placeholder="e.g. AWS, Stripe, Twilio"
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={addSubProcessor}
                className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm px-3 py-2 rounded-lg transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add
              </button>
            </div>
            {form.sub_processors.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {form.sub_processors.map(sp => (
                  <span key={sp} className="flex items-center gap-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2.5 py-1 rounded-full">
                    {sp}
                    <button onClick={() => removeSubProcessor(sp)} className="text-blue-400 hover:text-blue-600 ml-0.5">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Preview & Submit */}
      {step === 3 && (
        <div className="space-y-5">
          {/* Score gauge */}
          <div className="text-center">
            <div className="relative inline-flex flex-col items-center justify-center w-32 h-32 rounded-full border-8 border-gray-100 bg-white shadow-inner mx-auto">
              <span className="text-3xl font-bold text-gray-900">{total.toFixed(1)}</span>
              <span className="text-xs text-gray-400">out of 10</span>
            </div>
          </div>

          <div className="flex flex-col items-center gap-2">
            <span className={`inline-flex items-center gap-2 text-sm font-semibold px-4 py-1.5 rounded-full border ${TIER_STYLES[tier]}`}>
              {(tier === 'critical' || tier === 'high') && <AlertTriangle className="w-4 h-4" />}
              {tier.charAt(0).toUpperCase() + tier.slice(1)} Risk
            </span>
            <p className="text-sm text-gray-600 text-center">
              Recommended questionnaire: <span className="font-medium">{recommendedQuestionnaire(tier)}</span>
            </p>
          </div>

          {/* Score factor bar chart */}
          {chartData.length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Score Factor Breakdown</p>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 0, bottom: 0 }}>
                  <XAxis type="number" domain={[0, 4]} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(2)} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {chartData.map(entry => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Summary */}
          <div className="bg-gray-50 rounded-xl border border-gray-100 p-4 text-sm space-y-1.5">
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="font-medium text-gray-900">{form.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Type</span>
              <span className="font-medium text-gray-900">{VENDOR_TYPES.find(v => v.value === form.vendor_type)?.label}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Integration</span>
              <span className="font-medium text-gray-900">{INTEGRATION_DEPTHS.find(d => d.value === form.integrations_depth)?.label}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Data Types</span>
              <span className="font-medium text-gray-900">{form.data_types_processed.length === 0 ? 'None' : form.data_types_processed.join(', ')}</span>
            </div>
            {form.sub_processors.length > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-500">Sub-processors</span>
                <span className="font-medium text-gray-900">{form.sub_processors.join(', ')}</span>
              </div>
            )}
          </div>

          {mutation.isError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              Failed to create vendor. Please try again.
            </p>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-100">
        {step > 1 ? (
          <button
            onClick={() => setStep(s => s - 1)}
            className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Back
          </button>
        ) : (
          <button onClick={onCancel} className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            Cancel
          </button>
        )}

        {step < 3 ? (
          <button
            onClick={nextStep}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors"
          >
            {mutation.isPending ? 'Submitting...' : 'Create Vendor'}
          </button>
        )}
      </div>
    </div>
  )
}
