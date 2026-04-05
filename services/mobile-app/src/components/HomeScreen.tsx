import { useEffect, useState } from 'react';
import {
  MapPin,
  Calendar,
  AlertCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ChevronRight,
  Wifi,
  WifiOff,
  ClipboardList,
  Plus,
} from 'lucide-react';
import { getAllAssignments, getAllAudits } from '../offline/db';
import { useSyncStatus } from '../offline/sync';
import type { Assignment, FieldAudit } from '../types';

interface HomeScreenProps {
  tenantId: string;
  auditorEmail: string;
  onStartNewAudit: () => void;
  onViewAudits: () => void;
  onOpenAudit: (auditId: string) => void;
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-white',
  low: 'bg-green-500 text-white',
  normal: 'bg-gray-400 text-white',
};

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending: { label: 'Pending', color: 'text-gray-500', icon: <Clock size={14} /> },
  in_progress: { label: 'In Progress', color: 'text-blue-600', icon: <ClipboardList size={14} /> },
  completed: { label: 'Completed', color: 'text-green-600', icon: <CheckCircle2 size={14} /> },
  submitted: { label: 'Submitted', color: 'text-purple-600', icon: <CheckCircle2 size={14} /> },
};

const RISK_SCORE_COLORS: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function formatRelativeTime(dateStr: string): string {
  try {
    const diff = Date.now() - new Date(dateStr).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  } catch {
    return dateStr;
  }
}

export default function HomeScreen({
  tenantId,
  auditorEmail,
  onStartNewAudit,
  onViewAudits,
  onOpenAudit,
}: HomeScreenProps) {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [recentAudits, setRecentAudits] = useState<FieldAudit[]>([]);
  const [loading, setLoading] = useState(true);

  const syncStatus = useSyncStatus(tenantId, auditorEmail);
  const totalPending =
    syncStatus.pendingAudits + syncStatus.pendingResponses + syncStatus.pendingPhotos;

  useEffect(() => {
    async function loadData() {
      try {
        const [allAssignments, allAudits] = await Promise.all([
          getAllAssignments(),
          getAllAudits(),
        ]);
        // Active assignments for this auditor
        const myAssignments = allAssignments.filter(
          (a) => a.assigned_to_email === auditorEmail && a.status !== 'completed'
        );
        setAssignments(myAssignments.slice(0, 10));

        // Recent completed/submitted audits
        const sorted = allAudits
          .filter((a) => a.status === 'completed' || a.status === 'submitted')
          .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
        setRecentAudits(sorted.slice(0, 5));
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [auditorEmail]);

  return (
    <div className="min-h-screen bg-gray-50 pb-safe">
      {/* Offline banner */}
      {!syncStatus.isOnline && (
        <div className="offline-banner flex items-center justify-center gap-2">
          <WifiOff size={14} />
          <span>You're offline — changes saved locally</span>
        </div>
      )}

      {/* Header */}
      <header
        className={`bg-blue-700 text-white px-4 py-4 ${!syncStatus.isOnline ? 'mt-10' : ''}`}
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">VIA Field</h1>
            <p className="text-blue-200 text-sm">{auditorEmail}</p>
          </div>
          <div className="flex items-center gap-2">
            {syncStatus.isOnline ? (
              <div className="flex items-center gap-1 text-green-300 text-sm">
                <Wifi size={16} />
                <span>Online</span>
              </div>
            ) : (
              <div className="flex items-center gap-1 text-gray-300 text-sm">
                <WifiOff size={16} />
                <span>Offline</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="px-4 py-4 space-y-5">
        {/* Sync status card */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-900 flex items-center gap-2">
              <RefreshCw size={16} className={syncStatus.isSyncing ? 'animate-spin text-blue-600' : 'text-gray-500'} />
              Sync Status
            </h2>
            {syncStatus.isOnline && (
              <button
                onClick={syncStatus.triggerSync}
                disabled={syncStatus.isSyncing}
                className="text-blue-600 text-sm font-medium disabled:opacity-50 tap-target px-2"
              >
                {syncStatus.isSyncing ? 'Syncing…' : 'Sync Now'}
              </button>
            )}
          </div>

          {totalPending > 0 ? (
            <div className="flex items-start gap-3">
              <AlertCircle size={18} className="text-amber-500 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-gray-700">
                <p className="font-medium text-amber-700">{totalPending} item{totalPending !== 1 ? 's' : ''} pending sync</p>
                <div className="text-gray-500 mt-1 space-y-0.5">
                  {syncStatus.pendingAudits > 0 && <p>{syncStatus.pendingAudits} audit{syncStatus.pendingAudits !== 1 ? 's' : ''}</p>}
                  {syncStatus.pendingResponses > 0 && <p>{syncStatus.pendingResponses} response{syncStatus.pendingResponses !== 1 ? 's' : ''}</p>}
                  {syncStatus.pendingPhotos > 0 && <p>{syncStatus.pendingPhotos} photo{syncStatus.pendingPhotos !== 1 ? 's' : ''}</p>}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-green-600 text-sm">
              <CheckCircle2 size={16} />
              <span>All data synced</span>
            </div>
          )}

          {syncStatus.lastSyncAt && (
            <p className="text-xs text-gray-400 mt-2">
              Last sync: {formatRelativeTime(syncStatus.lastSyncAt)}
            </p>
          )}
        </div>

        {/* Assigned audits */}
        <section>
          <h2 className="section-header">My Assignments</h2>
          {loading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div key={i} className="card animate-pulse h-24 bg-gray-100" />
              ))}
            </div>
          ) : assignments.length === 0 ? (
            <div className="card text-center py-8 text-gray-500">
              <ClipboardList size={32} className="mx-auto mb-2 text-gray-300" />
              <p className="text-sm">No active assignments</p>
            </div>
          ) : (
            <div className="space-y-3">
              {assignments.map((assignment) => {
                const statusCfg = STATUS_CONFIG[assignment.status] ?? STATUS_CONFIG.pending;
                const priorityColor = PRIORITY_COLORS[assignment.priority] ?? PRIORITY_COLORS.normal;
                return (
                  <div key={assignment.id} className="card">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${priorityColor}`}>
                            {assignment.priority?.toUpperCase() ?? 'NORMAL'}
                          </span>
                          <span className={`flex items-center gap-1 text-xs ${statusCfg.color}`}>
                            {statusCfg.icon}
                            {statusCfg.label}
                          </span>
                        </div>
                        <p className="font-semibold text-gray-900 truncate">{assignment.location_name}</p>
                        {assignment.template_name && (
                          <p className="text-sm text-gray-600 truncate">{assignment.template_name}</p>
                        )}
                        <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                          <Calendar size={12} />
                          <span>Due {formatDate(assignment.due_date)}</span>
                        </div>
                        {assignment.location_address && (
                          <div className="flex items-center gap-1 text-xs text-gray-400 mt-0.5">
                            <MapPin size={12} />
                            <span className="truncate">{assignment.location_address}</span>
                          </div>
                        )}
                      </div>
                      <ChevronRight size={18} className="text-gray-400 flex-shrink-0 mt-1" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Recent audits */}
        {recentAudits.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="section-header mb-0">Recent Audits</h2>
              <button
                onClick={onViewAudits}
                className="text-blue-600 text-sm font-medium tap-target px-1"
              >
                View all
              </button>
            </div>
            <div className="space-y-3">
              {recentAudits.map((audit) => (
                <button
                  key={audit.id}
                  onClick={() => onOpenAudit(audit.id)}
                  className="card w-full text-left tap-target block"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-gray-900 truncate">{audit.location_name}</p>
                      <p className="text-sm text-gray-500 truncate">{formatDate(audit.started_at)}</p>
                      {audit.total_findings > 0 && (
                        <p className="text-xs text-orange-600 mt-0.5">
                          {audit.total_findings} finding{audit.total_findings !== 1 ? 's' : ''}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {audit.overall_score != null && (
                        <span className="text-lg font-bold text-gray-900">
                          {Math.round(audit.overall_score)}%
                        </span>
                      )}
                      {audit.risk_level && (
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                            RISK_SCORE_COLORS[audit.risk_level] ?? 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {audit.risk_level}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Quick actions */}
        <div className="grid grid-cols-2 gap-3 pt-2">
          <button onClick={onStartNewAudit} className="btn-primary flex-col gap-2 py-5">
            <Plus size={22} />
            <span>Start New Audit</span>
          </button>
          <button onClick={onViewAudits} className="btn-secondary flex-col gap-2 py-5">
            <ClipboardList size={22} />
            <span>View All Audits</span>
          </button>
        </div>
      </div>
    </div>
  );
}
