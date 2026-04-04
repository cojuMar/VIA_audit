import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Cloud,
  Server,
  Users,
  Database,
  DollarSign,
  Cpu,
  Package,
  Plus,
  AlertTriangle,
  Mail,
  Calendar,
} from 'lucide-react'
import { api } from '../api'
import type { Vendor } from '../types'
import { VendorIntakeForm } from './VendorIntakeForm'

interface VendorCatalogProps {
  tenantId: string
  onVendorSelect: (vendorId: string) => void
}

const TYPE_ICONS: Record<Vendor['vendor_type'], React.ReactNode> = {
  saas: <Cloud className="w-4 h-4" />,
  infrastructure: <Server className="w-4 h-4" />,
  professional_services: <Users className="w-4 h-4" />,
  data_processor: <Database className="w-4 h-4" />,
  financial: <DollarSign className="w-4 h-4" />,
  hardware: <Cpu className="w-4 h-4" />,
  other: <Package className="w-4 h-4" />,
}

const TYPE_LABELS: Record<Vendor['vendor_type'], string> = {
  saas: 'SaaS',
  infrastructure: 'Infrastructure',
  professional_services: 'Professional Services',
  data_processor: 'Data Processor',
  financial: 'Financial',
  hardware: 'Hardware',
  other: 'Other',
}

const RISK_TIER_STYLES: Record<Vendor['risk_tier'], string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-green-100 text-green-700 border-green-200',
  unrated: 'bg-gray-100 text-gray-600 border-gray-200',
}

const RISK_TIER_BAR: Record<Vendor['risk_tier'], string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-green-500',
  unrated: 'bg-gray-400',
}

const STATUS_STYLES: Record<Vendor['status'], string> = {
  active: 'bg-green-50 text-green-700',
  inactive: 'bg-gray-50 text-gray-500',
  under_review: 'bg-blue-50 text-blue-700',
  offboarded: 'bg-red-50 text-red-500',
}

type RiskFilter = Vendor['risk_tier'] | 'all'
type StatusFilter = 'active' | 'under_review' | 'offboarded' | 'all'

function daysUntil(dateStr: string): number {
  const now = new Date()
  const target = new Date(dateStr)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

export function VendorCatalog({ tenantId, onVendorSelect }: VendorCatalogProps) {
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [showIntakeForm, setShowIntakeForm] = useState(false)
  const queryClient = useQueryClient()

  const { data: vendors = [], isLoading } = useQuery({
    queryKey: ['vendors', tenantId],
    queryFn: () => api.getVendors(tenantId),
  })

  const filtered = vendors.filter(v => {
    const matchesSearch =
      v.name.toLowerCase().includes(search.toLowerCase()) ||
      (v.primary_contact_email ?? '').toLowerCase().includes(search.toLowerCase())
    const matchesRisk = riskFilter === 'all' || v.risk_tier === riskFilter
    const matchesStatus = statusFilter === 'all' || v.status === statusFilter
    return matchesSearch && matchesRisk && matchesStatus
  })

  const totalCritical = vendors.filter(v => v.risk_tier === 'critical').length
  const totalHigh = vendors.filter(v => v.risk_tier === 'high').length
  const overdueReviews = vendors.filter(v => {
    if (!v.next_review_at) return false
    return daysUntil(v.next_review_at) < 0
  }).length

  function handleVendorCreated(vendorId: string) {
    setShowIntakeForm(false)
    void queryClient.invalidateQueries({ queryKey: ['vendors', tenantId] })
    onVendorSelect(vendorId)
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading vendor catalog...</div>
  }

  return (
    <div className="space-y-5">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Total Vendors', value: vendors.length, color: 'text-gray-900' },
          { label: 'Critical', value: totalCritical, color: 'text-red-600' },
          { label: 'High', value: totalHigh, color: 'text-orange-600' },
          { label: 'Overdue Reviews', value: overdueReviews, color: 'text-red-600' },
        ].map(stat => (
          <div key={stat.label} className="bg-white rounded-xl border border-gray-200 px-4 py-3 shadow-sm">
            <p className="text-xs text-gray-500">{stat.label}</p>
            <p className={`text-2xl font-bold mt-0.5 ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Header + search */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap flex-1">
          <input
            type="text"
            placeholder="Search vendors..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {/* Risk tier chips */}
          <div className="flex gap-1.5 flex-wrap">
            {(['all', 'critical', 'high', 'medium', 'low', 'unrated'] as RiskFilter[]).map(tier => (
              <button
                key={tier}
                onClick={() => setRiskFilter(tier)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  riskFilter === tier
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                {tier === 'all' ? 'All Tiers' : tier.charAt(0).toUpperCase() + tier.slice(1)}
              </button>
            ))}
          </div>
          {/* Status chips */}
          <div className="flex gap-1.5 flex-wrap">
            {(['all', 'active', 'under_review', 'offboarded'] as StatusFilter[]).map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  statusFilter === s
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                {s === 'all' ? 'All Status' : s === 'under_review' ? 'Under Review' : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={() => setShowIntakeForm(true)}
          className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Vendor
        </button>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Package className="w-12 h-12 text-gray-300 mb-3" />
          <p className="text-gray-500 font-medium">
            {vendors.length === 0 ? 'No vendors yet' : 'No vendors match your filters'}
          </p>
          {vendors.length === 0 && (
            <button
              onClick={() => setShowIntakeForm(true)}
              className="mt-4 flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add your first vendor
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(vendor => {
            const score = vendor.inherent_risk_score ?? 0
            const reviewDays = vendor.next_review_at ? daysUntil(vendor.next_review_at) : null
            const reviewOverdue = reviewDays !== null && reviewDays < 0
            const reviewSoon = reviewDays !== null && reviewDays >= 0 && reviewDays <= 30

            return (
              <div
                key={vendor.id}
                className="bg-white rounded-xl border border-gray-200 shadow-sm hover:border-blue-300 hover:shadow-md transition-all flex flex-col"
              >
                <div className="p-4 space-y-3 flex-1">
                  {/* Name + type */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-gray-400 shrink-0">{TYPE_ICONS[vendor.vendor_type]}</span>
                      <h3 className="text-sm font-semibold text-gray-900 truncate">{vendor.name}</h3>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${STATUS_STYLES[vendor.status]}`}>
                      {vendor.status === 'under_review' ? 'Under Review' : vendor.status.charAt(0).toUpperCase() + vendor.status.slice(1)}
                    </span>
                  </div>

                  <p className="text-xs text-gray-400">{TYPE_LABELS[vendor.vendor_type]}</p>

                  {/* Risk tier badge */}
                  <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${RISK_TIER_STYLES[vendor.risk_tier]}`}>
                    {vendor.risk_tier === 'critical' && <AlertTriangle className="w-3 h-3" />}
                    {vendor.risk_tier.charAt(0).toUpperCase() + vendor.risk_tier.slice(1)} Risk
                  </span>

                  {/* Data sensitivity badges */}
                  <div className="flex gap-1.5 flex-wrap">
                    {vendor.processes_pii && (
                      <span className="text-xs bg-blue-100 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded font-medium">PII</span>
                    )}
                    {vendor.processes_phi && (
                      <span className="text-xs bg-red-100 text-red-700 border border-red-200 px-1.5 py-0.5 rounded font-medium">PHI</span>
                    )}
                    {vendor.processes_pci && (
                      <span className="text-xs bg-purple-100 text-purple-700 border border-purple-200 px-1.5 py-0.5 rounded font-medium">PCI</span>
                    )}
                    {vendor.uses_ai && (
                      <span className="text-xs bg-indigo-100 text-indigo-700 border border-indigo-200 px-1.5 py-0.5 rounded font-medium">AI</span>
                    )}
                  </div>

                  {/* Inherent risk score progress bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>Inherent Risk Score</span>
                      <span className="font-medium">{score.toFixed(1)} / 10</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${RISK_TIER_BAR[vendor.risk_tier]}`}
                        style={{ width: `${Math.min((score / 10) * 100, 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Contact */}
                  {vendor.primary_contact_email && (
                    <div className="flex items-center gap-1.5 text-xs text-gray-400 truncate">
                      <Mail className="w-3 h-3 shrink-0" />
                      <span className="truncate">{vendor.primary_contact_email}</span>
                    </div>
                  )}

                  {/* Next review date */}
                  {vendor.next_review_at && (
                    <div className={`flex items-center gap-1.5 text-xs font-medium ${
                      reviewOverdue ? 'text-red-600' : reviewSoon ? 'text-amber-600' : 'text-gray-400'
                    }`}>
                      <Calendar className="w-3 h-3 shrink-0" />
                      {reviewOverdue
                        ? `Review overdue by ${Math.abs(reviewDays!)} day${Math.abs(reviewDays!) !== 1 ? 's' : ''}`
                        : reviewSoon
                        ? `Review due in ${reviewDays} day${reviewDays !== 1 ? 's' : ''}`
                        : `Next review: ${new Date(vendor.next_review_at).toLocaleDateString()}`}
                    </div>
                  )}
                </div>

                {/* View Details */}
                <div className="px-4 pb-4">
                  <button
                    onClick={() => onVendorSelect(vendor.id)}
                    className="w-full text-center text-xs font-medium text-blue-600 border border-blue-200 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    View Details
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Intake Form Modal */}
      {showIntakeForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <VendorIntakeForm
              tenantId={tenantId}
              onComplete={handleVendorCreated}
              onCancel={() => setShowIntakeForm(false)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
