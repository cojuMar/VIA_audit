import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RadialBarChart, RadialBar, ResponsiveContainer } from 'recharts'
import { RefreshCw, CheckCircle } from 'lucide-react'
import { api } from '../api'
import type { ComplianceScore } from '../types'

interface ComplianceScoreCardProps {
  tenantId: string
}

function scoreColor(score: number): string {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#f59e0b'
  return '#ef4444'
}

function ScoreGauge({ score }: { score: number }) {
  const color = scoreColor(score)
  const data = [{ value: score, fill: color }]

  return (
    <div className="relative w-28 h-28 mx-auto">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="65%"
          outerRadius="100%"
          startAngle={220}
          endAngle={-40}
          data={data}
          barSize={10}
        >
          <RadialBar
            dataKey="value"
            cornerRadius={5}
            background={{ fill: '#f3f4f6' }}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>{Math.round(score)}%</span>
      </div>
    </div>
  )
}

export function ComplianceScoreCard({ tenantId }: ComplianceScoreCardProps) {
  const [refreshing, setRefreshing] = useState(false)
  const queryClient = useQueryClient()

  const { data: scores = [], isLoading } = useQuery({
    queryKey: ['scores', tenantId],
    queryFn: () => api.getScores(tenantId),
  })

  const refreshMutation = useMutation({
    mutationFn: () => {
      setRefreshing(true)
      return api.refreshScores(tenantId)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['scores', tenantId], data)
      setRefreshing(false)
    },
    onError: () => setRefreshing(false),
  })

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading compliance scores...</div>
  }

  if (scores.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-400">
        <CheckCircle className="w-12 h-12 text-gray-300" />
        <p className="text-sm">Activate frameworks to see your compliance score</p>
      </div>
    )
  }

  // Weighted aggregate
  const totalControls = scores.reduce((sum, s) => sum + s.total_controls, 0)
  const aggregateScore = totalControls > 0
    ? scores.reduce((sum, s) => sum + s.score_pct * s.total_controls, 0) / totalControls
    : 0

  return (
    <div className="space-y-6">
      {/* Header with aggregate */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Compliance Scores</h2>
          <p className="text-sm text-gray-500">
            Overall aggregate: <span className="font-semibold" style={{ color: scoreColor(aggregateScore) }}>{Math.round(aggregateScore)}%</span>
            {' '}across {scores.length} framework{scores.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh Scores
        </button>
      </div>

      {/* Score Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {scores.map((score: ComplianceScore) => (
          <div key={score.framework_id} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 leading-tight">{score.framework_name}</h3>
              <p className="text-xs text-gray-400 mt-0.5">{score.slug}</p>
            </div>

            <ScoreGauge score={score.score_pct} />

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-green-50 rounded-lg p-2">
                <p className="text-lg font-bold text-green-600">{score.passing_controls}</p>
                <p className="text-xs text-green-500">Passing</p>
              </div>
              <div className="bg-red-50 rounded-lg p-2">
                <p className="text-lg font-bold text-red-500">{score.failing_controls}</p>
                <p className="text-xs text-red-400">Failing</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <p className="text-lg font-bold text-gray-500">{score.not_started_controls}</p>
                <p className="text-xs text-gray-400">Not Started</p>
              </div>
            </div>

            <p className="text-xs text-gray-400 text-center">
              Last computed: {new Date(score.computed_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
