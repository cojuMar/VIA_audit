import { useQuery } from '@tanstack/react-query'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { AlertTriangle, Calendar, FileText, GitBranch, Clock } from 'lucide-react'
import { api } from '../api'
import type { Vendor, MonitoringEvent, VendorContract } from '../types'

interface TPRMDashboardProps {
  tenantId: string
  onVendorSelect: (vendorId: string) => void
}

const TIER_COLORS: Record<Vendor['risk_tier'], string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#22c55e',
  unrated: '#9ca3af',
}

const SEVERITY_BADGE: Record<MonitoringEvent['severity'], string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-green-100 text-green-700',
  info: 'bg-blue-100 text-blue-700',
}

function daysUntil(dateStr: string): number {
  const now = new Date()
  const target = new Date(dateStr)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

export function TPRMDashboard({ tenantId, onVendorSelect }: TPRMDashboardProps) {
  const { data: vendors = [], isLoading: loadingVendors } = useQuery({
    queryKey: ['vendors', tenantId],
    queryFn: () => api.getVendors(tenantId),
  })

  const { data: recentAlerts = [], isLoading: loadingAlerts } = useQuery({
    queryKey: ['all-monitoring', tenantId],
    queryFn: () => api.getAllMonitoringEvents(tenantId, { limit: 10 }),
  })

  const { data: expiringContracts = [], isLoading: loadingContracts } = useQuery({
    queryKey: ['expiring-contracts', tenantId],
    queryFn: () => api.getExpiringContracts(tenantId, 90),
  })

  const { data: reviewCalendar = [], isLoading: loadingCalendar } = useQuery({
    queryKey: ['review-calendar', tenantId],
    queryFn: () => api.getReviewCalendar(tenantId),
  })

  // Risk distribution pie data
  const tierCounts = (['critical', 'high', 'medium', 'low', 'unrated'] as Vendor['risk_tier'][]).map(tier => ({
    name: tier.charAt(0).toUpperCase() + tier.slice(1),
    value: vendors.filter(v => v.risk_tier === tier).length,
    fill: TIER_COLORS[tier],
  })).filter(d => d.value > 0)

  // Fourth-party sub-processor summary by tier (derived from vendor data — simplified)
  const fourthPartySummary = vendors.reduce<Record<string, number>>((acc, v) => {
    acc[v.risk_tier] = (acc[v.risk_tier] ?? 0) + 1
    return acc
  }, {})

  const isLoading = loadingVendors || loadingAlerts || loadingContracts || loadingCalendar

  if (isLoading) {
    return <div className="flex items-center justify-center h-48 text-gray-400 text-sm">Loading portfolio dashboard...</div>
  }

  const overdueReviews = reviewCalendar.filter(r => r.is_overdue)
  const upcomingReviews = reviewCalendar.filter(r => !r.is_overdue)

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Portfolio Overview</h2>
        <p className="text-sm text-gray-500">{vendors.length} vendors tracked</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Risk Distribution */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Risk Distribution</h3>
          {tierCounts.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-sm">No vendors</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={tierCounts}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={70}
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                >
                  {tierCounts.map(entry => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent Monitoring Alerts */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-orange-500" />
            <h3 className="text-sm font-semibold text-gray-900">Recent Alerts</h3>
            <span className="text-xs text-gray-400 ml-auto">Last 10 critical/high</span>
          </div>
          {recentAlerts.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">No recent alerts</div>
          ) : (
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {recentAlerts.slice(0, 10).map(event => (
                <div key={event.id} className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors">
                  <span className={`text-xs font-medium px-1.5 py-0.5 rounded shrink-0 ${SEVERITY_BADGE[event.severity]}`}>
                    {event.severity.toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-gray-900 truncate">{event.title}</p>
                    <p className="text-xs text-gray-400">{new Date(event.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Contracts Expiring in 90 Days */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <div className="flex items-center gap-2 mb-3">
          <FileText className="w-4 h-4 text-amber-500" />
          <h3 className="text-sm font-semibold text-gray-900">Contracts Expiring Within 90 Days</h3>
        </div>
        {expiringContracts.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">No contracts expiring soon</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left text-gray-500 font-medium pb-2 pr-4">Contract</th>
                  <th className="text-left text-gray-500 font-medium pb-2 pr-4">Type</th>
                  <th className="text-left text-gray-500 font-medium pb-2 pr-4">Expiry</th>
                  <th className="text-left text-gray-500 font-medium pb-2">Days Left</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {expiringContracts.map((contract: VendorContract) => {
                  const days = contract.expiry_date ? daysUntil(contract.expiry_date) : null
                  return (
                    <tr key={contract.id} className="hover:bg-gray-50">
                      <td className="py-2 pr-4 font-medium text-gray-900">{contract.title}</td>
                      <td className="py-2 pr-4 text-gray-500">{contract.contract_type}</td>
                      <td className="py-2 pr-4 text-gray-500">
                        {contract.expiry_date ? new Date(contract.expiry_date).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-2">
                        {days !== null ? (
                          <span className={`font-medium ${days <= 30 ? 'text-red-600' : days <= 60 ? 'text-amber-600' : 'text-gray-600'}`}>
                            {days}d
                          </span>
                        ) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Vendor Review Calendar */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <Calendar className="w-4 h-4 text-blue-500" />
            <h3 className="text-sm font-semibold text-gray-900">Review Calendar</h3>
          </div>

          {overdueReviews.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium text-red-600 mb-1.5">Overdue</p>
              <div className="space-y-1.5">
                {overdueReviews.slice(0, 5).map(r => (
                  <div
                    key={r.vendor_id}
                    className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-red-50 border border-red-100 cursor-pointer hover:bg-red-100 transition-colors"
                    onClick={() => onVendorSelect(r.vendor_id)}
                  >
                    <span className="text-xs font-medium text-red-700">{r.vendor_name}</span>
                    <span className="text-xs text-red-500">{Math.abs(daysUntil(r.next_review_at))}d overdue</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {upcomingReviews.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1.5">Upcoming</p>
              <div className="space-y-1.5">
                {upcomingReviews.slice(0, 5).map(r => {
                  const days = daysUntil(r.next_review_at)
                  return (
                    <div
                      key={r.vendor_id}
                      className={`flex items-center justify-between px-3 py-1.5 rounded-lg border cursor-pointer transition-colors ${
                        days <= 30
                          ? 'bg-amber-50 border-amber-100 hover:bg-amber-100'
                          : 'bg-gray-50 border-gray-100 hover:bg-gray-100'
                      }`}
                      onClick={() => onVendorSelect(r.vendor_id)}
                    >
                      <span className={`text-xs font-medium ${days <= 30 ? 'text-amber-700' : 'text-gray-700'}`}>{r.vendor_name}</span>
                      <span className={`text-xs ${days <= 30 ? 'text-amber-500' : 'text-gray-400'}`}>in {days}d</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {reviewCalendar.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">No reviews scheduled</p>
          )}
        </div>

        {/* Fourth-Party Summary */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <GitBranch className="w-4 h-4 text-indigo-500" />
            <h3 className="text-sm font-semibold text-gray-900">Fourth-Party Graph Summary</h3>
          </div>
          <p className="text-xs text-gray-500 mb-3">Sub-processors by risk tier across all vendors</p>
          <div className="space-y-2">
            {Object.entries(fourthPartySummary).map(([tier, count]) => {
              const color = TIER_COLORS[tier as Vendor['risk_tier']] ?? '#9ca3af'
              return (
                <div key={tier} className="flex items-center gap-3">
                  <span className="w-20 text-xs text-gray-500 capitalize">{tier}</span>
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.min((count / Math.max(...Object.values(fourthPartySummary))) * 100, 100)}%`, backgroundColor: color }}
                    />
                  </div>
                  <span className="text-xs font-medium text-gray-700 w-6 text-right">{count}</span>
                </div>
              )
            })}
          </div>
          {Object.keys(fourthPartySummary).length === 0 && (
            <div className="flex items-center justify-center gap-2 h-20 text-gray-400 text-sm">
              <Clock className="w-4 h-4" />
              No fourth-party data
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
