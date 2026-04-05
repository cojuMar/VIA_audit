import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Download, ChevronDown, ChevronRight, CheckCircle } from 'lucide-react'
import { api } from '../api'
import type { GapItem } from '../types'

interface GapAssessmentReportProps {
  tenantId: string
}

const SEVERITY_ORDER: Record<GapItem['gap_severity'], number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
}

const SEVERITY_COLORS: Record<GapItem['gap_severity'], string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-green-100 text-green-700 border-green-200',
}

const SEVERITY_BADGE_BG: Record<GapItem['gap_severity'], string> = {
  critical: 'bg-red-500 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-amber-400 text-white',
  low: 'bg-green-500 text-white',
}

function exportToCSV(gaps: GapItem[]) {
  const headers = ['Control ID', 'Domain', 'Title', 'Severity', 'Gap Description', 'Remediation Steps']
  const rows = gaps.map(g => [
    g.control_id,
    g.domain,
    g.control_title,
    g.gap_severity,
    g.gap_description,
    g.remediation_steps ?? '',
  ])
  const csv = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'gap-assessment.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function GapAssessmentReport({ tenantId }: GapAssessmentReportProps) {
  const [filterSeverity, setFilterSeverity] = useState<GapItem['gap_severity'] | 'all'>('all')
  const [filterDomain, setFilterDomain] = useState('all')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [runningAnalysis, setRunningAnalysis] = useState(false)

  const queryClient = useQueryClient()

  const { data: _gapsRaw = [], isLoading } = useQuery({
    queryKey: ['gaps', tenantId],
    queryFn: () => api.getGaps(tenantId),
  })
  // Guard against API returning a non-array (e.g. error object from a 400 response)
  const gaps: GapItem[] = Array.isArray(_gapsRaw) ? _gapsRaw : []

  const runAnalysisMutation = useMutation({
    mutationFn: async () => {
      setRunningAnalysis(true)
      // POST to gaps endpoint triggers reanalysis; then refetch
      await fetch(`/api/tenants/${tenantId}/gaps`, {
        method: 'POST',
        headers: { 'X-Tenant-ID': tenantId },
      })
      return api.getGaps(tenantId)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['gaps', tenantId], Array.isArray(data) ? data : [])
      setRunningAnalysis(false)
    },
    onError: () => setRunningAnalysis(false),
  })

  const domains = useMemo(() => {
    const set = new Set(gaps.map(g => g.domain))
    return Array.from(set).sort()
  }, [gaps])

  const filtered = useMemo(() => {
    return gaps
      .filter(g => filterSeverity === 'all' || g.gap_severity === filterSeverity)
      .filter(g => filterDomain === 'all' || g.domain === filterDomain)
      .sort((a, b) => SEVERITY_ORDER[a.gap_severity] - SEVERITY_ORDER[b.gap_severity])
  }, [gaps, filterSeverity, filterDomain])

  const counts = useMemo(() => ({
    critical: gaps.filter(g => g.gap_severity === 'critical').length,
    high: gaps.filter(g => g.gap_severity === 'high').length,
    medium: gaps.filter(g => g.gap_severity === 'medium').length,
    low: gaps.filter(g => g.gap_severity === 'low').length,
  }), [gaps])

  function toggleExpanded(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading gap analysis...</div>
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Gap Assessment Report</h2>
          <p className="text-sm text-gray-500">{gaps.length} total gaps identified</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => runAnalysisMutation.mutate()}
            disabled={runningAnalysis}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${runningAnalysis ? 'animate-spin' : ''}`} />
            Run Gap Analysis
          </button>
          <button
            onClick={() => exportToCSV(filtered)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Severity Summary */}
      <div className="flex flex-wrap gap-3">
        {(['critical', 'high', 'medium', 'low'] as const).map(sev => (
          <div
            key={sev}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border font-medium text-sm cursor-pointer transition-opacity ${SEVERITY_COLORS[sev]} ${filterSeverity === sev ? 'ring-2 ring-offset-1 ring-current' : ''}`}
            onClick={() => setFilterSeverity(prev => prev === sev ? 'all' : sev)}
          >
            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${SEVERITY_BADGE_BG[sev]}`}>
              {counts[sev]}
            </span>
            <span className="uppercase tracking-wide text-xs">{sev}</span>
          </div>
        ))}
        {filterSeverity !== 'all' && (
          <button
            onClick={() => setFilterSeverity('all')}
            className="text-xs text-gray-500 underline hover:text-gray-700"
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Domain filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500 font-medium">Domain:</span>
        {['all', ...domains].map(d => (
          <button
            key={d}
            onClick={() => setFilterDomain(d)}
            className={`text-xs px-2.5 py-1 rounded border transition-colors ${
              filterDomain === d
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
            }`}
          >
            {d === 'all' ? 'All Domains' : d}
          </button>
        ))}
      </div>

      {/* Empty state */}
      {gaps.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-400">
          <CheckCircle className="w-14 h-14 text-green-400" />
          <p className="text-base font-medium text-green-600">No gaps found! All controls are passing.</p>
        </div>
      )}

      {/* Table */}
      {filtered.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Severity</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Control ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Domain</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Title</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Gap Description</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(gap => {
                const isExpanded = expandedIds.has(gap.framework_control_id)
                return (
                  <>
                    <tr
                      key={gap.framework_control_id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => toggleExpanded(gap.framework_control_id)}
                    >
                      <td className="px-4 py-3">
                        <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-semibold uppercase ${SEVERITY_BADGE_BG[gap.gap_severity]}`}>
                          {gap.gap_severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{gap.control_id}</td>
                      <td className="px-4 py-3 text-xs text-gray-600">{gap.domain}</td>
                      <td className="px-4 py-3 text-xs font-medium text-gray-800 max-w-[180px]">
                        <div className="flex items-center gap-1">
                          {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
                          <span className="truncate">{gap.control_title}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 max-w-[240px]">
                        <span className="line-clamp-2">{gap.gap_description}</span>
                      </td>
                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        <button className="text-xs px-3 py-1 bg-blue-50 text-blue-600 border border-blue-200 rounded hover:bg-blue-100 transition-colors whitespace-nowrap">
                          Mark In Progress
                        </button>
                      </td>
                    </tr>
                    {isExpanded && gap.remediation_steps && (
                      <tr key={`${gap.framework_control_id}-expanded`} className="bg-amber-50">
                        <td colSpan={6} className="px-6 py-4">
                          <p className="text-xs font-semibold text-amber-700 mb-1">Remediation Steps</p>
                          <p className="text-sm text-gray-700 whitespace-pre-wrap">{gap.remediation_steps}</p>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {filtered.length === 0 && gaps.length > 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">
          No gaps match the current filters.
        </div>
      )}
    </div>
  )
}
