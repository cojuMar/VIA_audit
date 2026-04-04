import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AlertOctagon,
  CheckCircle,
  Clock,
  RefreshCw,
  Play,
  Shield,
  BookOpen,
  UserCheck,
  XCircle,
} from 'lucide-react';
import {
  fetchEscalations,
  resolveEscalation,
  runEscalationCheck,
  setTenant,
} from '../api';
import type { Escalation } from '../types';

interface Props {
  tenantId: string;
}

const TYPE_BADGE: Record<string, string> = {
  policy_overdue: 'bg-blue-900 text-blue-200',
  training_overdue: 'bg-amber-900 text-amber-200',
  background_check_expired: 'bg-orange-900 text-orange-200',
  training_failed: 'bg-red-900 text-red-200',
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  policy_overdue: <Shield size={14} className="text-blue-400" />,
  training_overdue: <BookOpen size={14} className="text-amber-400" />,
  background_check_expired: <UserCheck size={14} className="text-orange-400" />,
  training_failed: <XCircle size={14} className="text-red-400" />,
};

function Toast({
  message,
  type,
  onDismiss,
}: {
  message: string;
  type: 'success' | 'error';
  onDismiss: () => void;
}) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border ${
        type === 'success'
          ? 'bg-green-900 border-green-700 text-green-200'
          : 'bg-red-900 border-red-700 text-red-200'
      }`}
    >
      {type === 'success' ? <CheckCircle size={16} /> : <XCircle size={16} />}
      <span className="text-sm">{message}</span>
      <button onClick={onDismiss} className="ml-2 text-current opacity-60 hover:opacity-100">✕</button>
    </div>
  );
}

export default function EscalationLog({ tenantId }: Props) {
  setTenant(tenantId);
  const qc = useQueryClient();

  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [resolvedFilter, setResolvedFilter] = useState<'open' | 'resolved' | 'all'>('open');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const { data: escalations, isLoading, refetch } = useQuery<Escalation[]>({
    queryKey: ['escalations', tenantId, typeFilter, resolvedFilter],
    queryFn: () =>
      fetchEscalations({
        type: typeFilter !== 'all' ? typeFilter : undefined,
        resolved:
          resolvedFilter === 'open' ? false : resolvedFilter === 'resolved' ? true : undefined,
      }),
    refetchInterval: 60_000,
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) => resolveEscalation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['escalations'] });
      showToast('Escalation resolved.', 'success');
    },
    onError: () => showToast('Failed to resolve escalation.', 'error'),
  });

  const runMutation = useMutation({
    mutationFn: runEscalationCheck,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['escalations'] });
      showToast(`Escalation check complete: ${result.escalations_created} new escalation(s) created.`, 'success');
    },
    onError: () => showToast('Escalation check failed.', 'error'),
  });

  const esc = escalations ?? [];

  // Type breakdown counts (across all filters — use separate query for totals)
  const allTypeCounts = {
    policy_overdue: esc.filter((e) => e.escalation_type === 'policy_overdue').length,
    training_overdue: esc.filter((e) => e.escalation_type === 'training_overdue').length,
    background_check_expired: esc.filter((e) => e.escalation_type === 'background_check_expired').length,
    training_failed: esc.filter((e) => e.escalation_type === 'training_failed').length,
  };

  const TYPES = [
    { key: 'all', label: 'All Types' },
    { key: 'policy_overdue', label: 'Policy Overdue' },
    { key: 'training_overdue', label: 'Training Overdue' },
    { key: 'background_check_expired', label: 'BG Check Expired' },
    { key: 'training_failed', label: 'Training Failed' },
  ];

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <AlertOctagon size={20} className="text-amber-400" />
          Escalation Log
        </h1>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => refetch()}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            className="btn-primary"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
          >
            {runMutation.isPending ? (
              <>
                <RefreshCw size={13} className="animate-spin" /> Running…
              </>
            ) : (
              <>
                <Play size={13} /> Run Escalation Check
              </>
            )}
          </button>
        </div>
      </div>

      {/* Type Breakdown Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { key: 'policy_overdue', label: 'Policy Overdue', icon: <Shield size={18} className="text-blue-400" />, color: 'text-blue-400' },
          { key: 'training_overdue', label: 'Training Overdue', icon: <BookOpen size={18} className="text-amber-400" />, color: 'text-amber-400' },
          { key: 'background_check_expired', label: 'BG Check Expired', icon: <UserCheck size={18} className="text-orange-400" />, color: 'text-orange-400' },
          { key: 'training_failed', label: 'Training Failed', icon: <XCircle size={18} className="text-red-400" />, color: 'text-red-400' },
        ].map((item) => (
          <div key={item.key} className="card">
            <div className="flex items-center gap-2 mb-2">
              {item.icon}
              <span className="text-sm text-gray-400">{item.label}</span>
            </div>
            <div className={`text-3xl font-bold ${item.color}`}>
              {allTypeCounts[item.key as keyof typeof allTypeCounts]}
            </div>
          </div>
        ))}
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Type filter */}
        <div className="flex gap-1.5">
          {TYPES.map((t) => (
            <button
              key={t.key}
              onClick={() => setTypeFilter(t.key)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                typeFilter === t.key
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="h-4 border-l border-gray-700" />

        {/* Resolved filter */}
        <div className="flex gap-1.5">
          {(['open', 'resolved', 'all'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setResolvedFilter(r)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium capitalize transition-colors ${
                resolvedFilter === r
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        <span className="ml-auto text-xs text-gray-500">
          {esc.length} escalation{esc.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-gray-400">
          <RefreshCw size={18} className="animate-spin mr-2" /> Loading…
        </div>
      ) : esc.length === 0 ? (
        <div className="card flex flex-col items-center py-12 text-gray-500">
          <CheckCircle size={32} className="mb-2 text-green-600" />
          <p className="text-sm">No escalations match the current filter.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Type</th>
                  <th className="th">Employee</th>
                  <th className="th">Ref Type</th>
                  <th className="th">Days Overdue</th>
                  <th className="th">Message</th>
                  <th className="th">Status</th>
                  <th className="th">Date</th>
                  <th className="th">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {esc.map((e) => (
                  <tr key={e.id} className="hover:bg-gray-800/50">
                    <td className="td">
                      <div className="flex items-center gap-1.5">
                        {TYPE_ICONS[e.escalation_type]}
                        <span
                          className={`badge text-xs ${TYPE_BADGE[e.escalation_type] ?? 'bg-gray-700 text-gray-300'}`}
                        >
                          {e.escalation_type.replace(/_/g, ' ')}
                        </span>
                      </div>
                    </td>
                    <td className="td text-xs font-mono text-gray-400">{e.employee_id}</td>
                    <td className="td text-gray-500 text-xs">{e.reference_type ?? '—'}</td>
                    <td className="td">
                      {e.days_overdue != null ? (
                        <span className="text-red-400 font-semibold">{e.days_overdue}d</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="td text-gray-400 text-xs max-w-xs truncate">
                      {e.message ?? '—'}
                    </td>
                    <td className="td">
                      {e.resolved ? (
                        <span className="badge bg-green-900 text-green-200 flex items-center gap-1 w-fit">
                          <CheckCircle size={11} /> Resolved
                        </span>
                      ) : (
                        <span className="badge bg-amber-900 text-amber-200 flex items-center gap-1 w-fit">
                          <Clock size={11} /> Open
                        </span>
                      )}
                    </td>
                    <td className="td text-xs text-gray-400">
                      {new Date(e.escalated_at).toLocaleDateString()}
                    </td>
                    <td className="td">
                      {!e.resolved && (
                        <button
                          className="btn-secondary text-xs py-0.5"
                          onClick={() => resolveMutation.mutate(e.id)}
                          disabled={resolveMutation.isPending}
                        >
                          Resolve
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}
