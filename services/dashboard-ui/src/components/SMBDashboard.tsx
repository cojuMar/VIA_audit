import { useEffect, useState } from 'react'
import { Database, CheckSquare, Clock } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../api'
import type { EvidenceRecord, AuditHubItem, Framework } from '../types'

interface SMBDashboardProps {
  framework: Framework
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-gray-100 text-gray-600',
}

export function SMBDashboard({ framework }: SMBDashboardProps) {
  const [records, setRecords] = useState<EvidenceRecord[]>([])
  const [hubItems, setHubItems] = useState<AuditHubItem[]>([])
  const [totalRecords, setTotalRecords] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getEvidenceLocker({ days: 30, limit: 20 }),
      api.getAuditHub(framework),
    ]).then(([ev, hub]) => {
      setRecords(ev.records)
      setTotalRecords(ev.total)
      setHubItems(hub)
    }).catch(console.error).finally(() => setLoading(false))
  }, [framework])

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">SMB Dashboard</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Evidence Locker */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
            <Database size={16} className="text-blue-600" />
            <h2 className="text-sm font-semibold text-gray-700">Evidence Locker</h2>
            <span className="ml-auto text-xs text-gray-400">{totalRecords.toLocaleString()} records</span>
          </div>
          <div className="divide-y divide-gray-50">
            {records.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-8">No evidence records found.</p>
            )}
            {records.map(rec => (
              <div key={rec.evidence_id} className="px-5 py-3 hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{rec.event_type}</p>
                    <p className="text-xs text-gray-500">{rec.source_system} · #{rec.chain_sequence}</p>
                  </div>
                  <span className={clsx(
                    'shrink-0 text-xs px-2 py-0.5 rounded-full font-medium',
                    rec.outcome === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                  )}>
                    {rec.outcome}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(rec.event_timestamp).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Audit Hub */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
            <CheckSquare size={16} className="text-purple-600" />
            <h2 className="text-sm font-semibold text-gray-700">Audit Hub</h2>
            <span className="ml-auto text-xs text-gray-400">{hubItems.length} open items</span>
          </div>
          <div className="divide-y divide-gray-50">
            {hubItems.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-8">No open audit items.</p>
            )}
            {hubItems.map(item => (
              <div key={item.item_id} className="px-5 py-3 hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{item.title}</p>
                    <p className="text-xs text-gray-500">{item.framework} · {item.control_id}</p>
                  </div>
                  <span className={clsx('shrink-0 text-xs px-2 py-0.5 rounded-full font-medium', PRIORITY_COLORS[item.priority])}>
                    {item.priority}
                  </span>
                </div>
                {item.due_date && (
                  <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                    <Clock size={10} />
                    Due {new Date(item.due_date).toLocaleDateString()}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
