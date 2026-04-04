import { useEffect, useState, useRef } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { DynamicGauge } from './DynamicGauge'
import { clsx } from 'clsx'
import { api } from '../api'
import type { Gauge, AnomalyFeedItem, Framework } from '../types'

interface AutonomousDashboardProps {
  framework: Framework
}

const RISK_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-green-100 text-green-700 border-green-200',
}

export function AutonomousDashboard({ framework }: AutonomousDashboardProps) {
  const [gauges, setGauges] = useState<Gauge[]>([])
  const [trend, setTrend] = useState<Array<{ snapshot_time: string; overall_score: number }>>([])
  const [anomalies, setAnomalies] = useState<AnomalyFeedItem[]>([])
  const [loading, setLoading] = useState(true)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getGauges(framework),
      api.getHealthTrend(framework, 30),
      api.getAnomalyFeed(20),
    ]).then(([g, t, a]) => {
      setGauges(g.gauges)
      setTrend(t.data as Array<{ snapshot_time: string; overall_score: number }>)
      setAnomalies(a as AnomalyFeedItem[])
    }).catch(console.error).finally(() => setLoading(false))

    // WebSocket for real-time updates
    const wsUrl = (import.meta.env.VITE_WS_URL as string) || 'ws://localhost:3009/ws'
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'health_score_update') {
          // Refresh gauges on update
          api.getGauges(framework).then(g => setGauges(g.gauges)).catch(() => {})
        }
      } catch { /* ignore */ }
    }
    wsRef.current = ws
    return () => ws.close()
  }, [framework])

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading autonomous dashboard...</div>
  }

  const trendData = trend.map(d => ({
    time: new Date(d.snapshot_time).toLocaleDateString(),
    score: Math.round(d.overall_score * 100),
  }))

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Autonomous Mode — {framework.toUpperCase().replace('_', ' ')}</h1>

      {/* Dynamic Gauges */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {gauges.map(gauge => (
          <DynamicGauge key={gauge.id} gauge={gauge} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Health Trend */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Health Score Trend (30d)</h2>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={v => `${v}%`} />
                <Tooltip formatter={(v) => [`${v}%`, 'Health Score']} />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#1a56db"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-sm text-gray-400">
              No trend data yet — snapshots are taken every 15 minutes.
            </div>
          )}
        </div>

        {/* Anomaly Feed */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Live Anomaly Feed</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
            {anomalies.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-8">No anomalies detected.</p>
            )}
            {anomalies.map(a => (
              <div key={a.anomaly_id} className={clsx('px-4 py-3 border-l-4', {
                'border-red-500': a.risk_level === 'critical',
                'border-orange-400': a.risk_level === 'high',
                'border-amber-300': a.risk_level === 'medium',
                'border-green-400': a.risk_level === 'low',
              })}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-gray-800 truncate">{a.event_type}</p>
                  <span className={clsx('shrink-0 text-xs px-2 py-0.5 rounded-full border font-medium', RISK_COLORS[a.risk_level])}>
                    {a.risk_level}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">
                  DRI: {(a.dri_score * 100).toFixed(0)}% · {a.source_system}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
