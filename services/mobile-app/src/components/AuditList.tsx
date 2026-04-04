import { useState, useEffect } from 'react';
import {
  ClipboardList,
  AlertCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ChevronRight,
  WifiOff,
} from 'lucide-react';
import { getAllAudits } from '../offline/db';
import { useSyncStatus } from '../offline/sync';
import type { FieldAudit } from '../types';

interface AuditListProps {
  tenantId: string;
  auditorEmail: string;
  onOpenAudit: (auditId: string) => void;
}

type TabKey = 'all' | 'in_progress' | 'submitted' | 'offline';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'submitted', label: 'Submitted' },
  { key: 'offline', label: 'Offline' },
];

const RISK_COLORS: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  in_progress: <Clock size={14} className="text-blue-500" />,
  completed: <CheckCircle2 size={14} className="text-green-500" />,
  submitted: <CheckCircle2 size={14} className="text-purple-500" />,
  pending: <Clock size={14} className="text-gray-400" />,
};

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export default function AuditList({ tenantId, auditorEmail, onOpenAudit }: AuditListProps) {
  const [audits, setAudits] = useState<FieldAudit[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>('all');
  const [loading, setLoading] = useState(true);
  const syncStatus = useSyncStatus(tenantId, auditorEmail);

  const loadAudits = async () => {
    setLoading(true);
    try {
      const all = await getAllAudits();
      const mine = all.filter((a) => a.auditor_email === auditorEmail);
      mine.sort(
        (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      );
      setAudits(mine);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auditorEmail]);

  const filtered = audits.filter((a) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'offline') return a._pendingSync === true;
    return a.status === activeTab;
  });

  const offlineCount = audits.filter((a) => a._pendingSync).length;

  const handleSyncAll = async () => {
    await syncStatus.triggerSync();
    await loadAudits();
  };

  return (
    <div className="min-h-screen bg-gray-50 pb-safe">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">My Audits</h1>
          {syncStatus.isOnline && (
            <button
              onClick={handleSyncAll}
              disabled={syncStatus.isSyncing}
              className="tap-target flex items-center gap-1.5 text-blue-600 text-sm font-medium px-2 disabled:opacity-50"
            >
              <RefreshCw
                size={16}
                className={syncStatus.isSyncing ? 'animate-spin' : ''}
              />
              {syncStatus.isSyncing ? 'Syncing…' : 'Sync All'}
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex mt-3 gap-1 overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium tap-target whitespace-nowrap ${
                activeTab === tab.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              {tab.label}
              {tab.key === 'offline' && offlineCount > 0 && (
                <span className="ml-1.5 bg-red-500 text-white text-xs rounded-full px-1.5">
                  {offlineCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </header>

      {/* List */}
      <div className="p-4 space-y-3">
        {!syncStatus.isOnline && (
          <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-sm">
            <WifiOff size={14} />
            Offline — showing locally saved audits
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card animate-pulse h-20 bg-gray-100" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="card text-center py-10 text-gray-500">
            <ClipboardList size={36} className="mx-auto mb-2 text-gray-300" />
            <p className="font-medium">No audits found</p>
            <p className="text-sm mt-1">
              {activeTab === 'offline'
                ? 'No audits pending sync'
                : 'Start a new audit to see it here'}
            </p>
          </div>
        ) : (
          filtered.map((audit) => (
            <AuditCard key={audit.id} audit={audit} onClick={() => onOpenAudit(audit.id)} />
          ))
        )}
      </div>
    </div>
  );
}

function AuditCard({ audit, onClick }: { audit: FieldAudit; onClick: () => void }) {
  const statusIcon = STATUS_ICONS[audit.status] ?? STATUS_ICONS.pending;
  const riskColor = audit.risk_level
    ? RISK_COLORS[audit.risk_level] ?? 'bg-gray-100 text-gray-700'
    : null;

  return (
    <button
      onClick={onClick}
      className="card w-full text-left tap-target relative overflow-hidden"
    >
      {/* Pending sync indicator */}
      {audit._pendingSync && (
        <div className="absolute top-0 right-0 bg-amber-400 text-white text-xs px-2 py-0.5 rounded-bl-lg flex items-center gap-1">
          <WifiOff size={10} />
          Offline
        </div>
      )}

      <div className="flex items-start justify-between gap-2 pr-4">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{audit.location_name}</p>
          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-gray-500">
            {statusIcon}
            <span className="capitalize">{audit.status.replace('_', ' ')}</span>
            <span>·</span>
            <span>{formatDate(audit.started_at)}</span>
          </div>
          {audit.total_findings > 0 && (
            <div className="flex items-center gap-1 text-xs text-orange-600 mt-1">
              <AlertCircle size={12} />
              {audit.total_findings} finding{audit.total_findings !== 1 ? 's' : ''}
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          {audit.overall_score != null && (
            <span className="text-xl font-bold text-gray-900">
              {Math.round(audit.overall_score)}%
            </span>
          )}
          {riskColor && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${riskColor}`}>
              {audit.risk_level}
            </span>
          )}
        </div>
      </div>

      <ChevronRight
        size={18}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
      />
    </button>
  );
}
