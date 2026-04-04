import { useEffect, useState } from 'react'
import { AlertTriangle, Users, TrendingDown } from 'lucide-react'
import { RiskHeatmap } from './RiskHeatmap'
import { api } from '../api'
import type { Framework } from '../types'

interface FirmDashboardProps {
  framework: Framework
}

export function FirmDashboard({ framework }: FirmDashboardProps) {
  const [portfolio, setPortfolio] = useState<{ avg_health_score: number | null; clients_at_risk: number; critical_issues_total: number; client_count: number } | null>(null)
  const [heatmapData, setHeatmapData] = useState<Array<{ tenant_id: string; label: string; categories: Array<{ category: string; avg_risk: number; count: number }> }>>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getPortfolio(framework),
      api.getRiskHeatmap(framework, 30),
    ]).then(([p, h]) => {
      setPortfolio(p)
      setHeatmapData(h.data)
    }).catch(console.error).finally(() => setLoading(false))
  }, [framework])

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading portfolio...</div>
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Firm Portfolio — {framework.toUpperCase().replace('_', ' ')}</h1>

      {/* Portfolio KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 rounded-lg"><Users size={20} className="text-blue-600" /></div>
            <div>
              <p className="text-xs text-gray-500 font-medium">Total Clients</p>
              <p className="text-2xl font-bold text-gray-900">{portfolio?.client_count ?? 0}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-50 rounded-lg"><TrendingDown size={20} className="text-amber-600" /></div>
            <div>
              <p className="text-xs text-gray-500 font-medium">Clients at Risk</p>
              <p className="text-2xl font-bold text-gray-900">{portfolio?.clients_at_risk ?? 0}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-50 rounded-lg"><AlertTriangle size={20} className="text-red-600" /></div>
            <div>
              <p className="text-xs text-gray-500 font-medium">Critical Issues</p>
              <p className="text-2xl font-bold text-red-600">{portfolio?.critical_issues_total ?? 0}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Risk Heatmap */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Risk Heatmap — Last 30 Days</h2>
        <RiskHeatmap data={heatmapData} />
      </div>
    </div>
  )
}
