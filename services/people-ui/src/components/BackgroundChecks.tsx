import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  UserCheck,
  Plus,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import {
  fetchBackgroundChecks,
  createBackgroundCheck,
  updateBackgroundCheckStatus,
  fetchEmployees,
  setTenant,
} from '../api';
import type { BackgroundCheck, Employee } from '../types';

interface Props {
  tenantId: string;
}

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-gray-700 text-gray-300',
  in_progress: 'bg-blue-900 text-blue-200',
  passed: 'bg-green-900 text-green-200',
  failed: 'bg-red-900 text-red-200',
  expired: 'bg-orange-900 text-orange-200',
  cancelled: 'bg-gray-800 text-gray-400',
};

const ADJUDICATION_BADGE: Record<string, string> = {
  clear: 'bg-green-900 text-green-200',
  review: 'bg-amber-900 text-amber-200',
  adverse_action: 'bg-red-900 text-red-200',
};

const CHECK_TYPES = [
  'Criminal Background',
  'Employment Verification',
  'Education Verification',
  'Credit Check',
  'Drug Screen',
  'Reference Check',
  'Identity Verification',
  'Motor Vehicle Record',
];

const PROVIDERS = ['HireRight', 'Checkr', 'Sterling', 'First Advantage', 'GoodHire', 'IntelliCorp'];

function InitiateCheckModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const { data: employees } = useQuery<Employee[]>({ queryKey: ['employees'], queryFn: fetchEmployees });

  const [form, setForm] = useState({
    employee_id: '',
    check_type: CHECK_TYPES[0],
    provider: PROVIDERS[0],
    expiry_date: '',
  });

  const mutation = useMutation({
    mutationFn: () => createBackgroundCheck(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['background-checks'] });
      onDone();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-4">Initiate Background Check</h3>
        <div className="space-y-3">
          <div>
            <label className="label">Employee</label>
            <select
              className="select"
              value={form.employee_id}
              onChange={(e) => setForm((f) => ({ ...f, employee_id: e.target.value }))}
            >
              <option value="">Select employee…</option>
              {(employees ?? []).map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Check Type</label>
            <select
              className="select"
              value={form.check_type}
              onChange={(e) => setForm((f) => ({ ...f, check_type: e.target.value }))}
            >
              {CHECK_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Provider</label>
            <select
              className="select"
              value={form.provider}
              onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
            >
              {PROVIDERS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Expiry Date (optional)</label>
            <input
              className="input"
              type="date"
              value={form.expiry_date}
              onChange={(e) => setForm((f) => ({ ...f, expiry_date: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-5">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.employee_id}
          >
            {mutation.isPending ? 'Initiating…' : 'Initiate Check'}
          </button>
        </div>
        {mutation.isError && <p className="text-red-400 text-sm mt-2">Failed. Please try again.</p>}
      </div>
    </div>
  );
}

function UpdateStatusModal({
  check,
  onClose,
  onDone,
}: {
  check: BackgroundCheck;
  onClose: () => void;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<BackgroundCheck['status']>(check.status);
  const [adjudication, setAdjudication] = useState<BackgroundCheck['adjudication']>(check.adjudication);
  const [completedAt, setCompletedAt] = useState(
    check.completed_at ? new Date(check.completed_at).toISOString().split('T')[0] : new Date().toISOString().split('T')[0]
  );

  const mutation = useMutation({
    mutationFn: () =>
      updateBackgroundCheckStatus(check.id, {
        status,
        adjudication: adjudication ?? undefined,
        completed_at: completedAt ? new Date(completedAt).toISOString() : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['background-checks'] });
      onDone();
    },
  });

  const STATUSES: BackgroundCheck['status'][] = ['pending', 'in_progress', 'passed', 'failed', 'expired', 'cancelled'];
  const ADJS: Array<BackgroundCheck['adjudication']> = [null, 'clear', 'review', 'adverse_action'];

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-sm shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-4">Update Check Status</h3>
        <div className="space-y-3">
          <div>
            <label className="label">Status</label>
            <select
              className="select"
              value={status}
              onChange={(e) => setStatus(e.target.value as BackgroundCheck['status'])}
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Adjudication</label>
            <select
              className="select"
              value={adjudication ?? ''}
              onChange={(e) =>
                setAdjudication((e.target.value || null) as BackgroundCheck['adjudication'])
              }
            >
              {ADJS.map((a) => (
                <option key={a ?? 'none'} value={a ?? ''}>
                  {a ? a.replace(/_/g, ' ') : 'None'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Completed Date</label>
            <input
              className="input"
              type="date"
              value={completedAt}
              onChange={(e) => setCompletedAt(e.target.value)}
            />
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-5">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Update'}
          </button>
        </div>
        {mutation.isError && <p className="text-red-400 text-sm mt-2">Failed. Please try again.</p>}
      </div>
    </div>
  );
}

export default function BackgroundChecks({ tenantId }: Props) {
  setTenant(tenantId);
  const [showInitiate, setShowInitiate] = useState(false);
  const [updateCheck, setUpdateCheck] = useState<BackgroundCheck | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data: checks, isLoading, refetch } = useQuery<BackgroundCheck[]>({
    queryKey: ['background-checks', tenantId, statusFilter],
    queryFn: () =>
      fetchBackgroundChecks(statusFilter !== 'all' ? { status: statusFilter } : undefined),
    refetchInterval: 60_000,
  });

  const allChecks = checks ?? [];

  // Summary counts
  const counts = {
    total: allChecks.length,
    pending: allChecks.filter((c) => c.status === 'pending').length,
    in_progress: allChecks.filter((c) => c.status === 'in_progress').length,
    passed: allChecks.filter((c) => c.status === 'passed').length,
    failed: allChecks.filter((c) => c.status === 'failed').length,
    expired: allChecks.filter((c) => c.status === 'expired').length,
  };

  // Expiring soon (within 60 days)
  const now = Date.now();
  const expiringSoon = allChecks.filter(
    (c) =>
      c.expiry_date &&
      c.status !== 'expired' &&
      c.status !== 'cancelled' &&
      (new Date(c.expiry_date).getTime() - now) / 86400000 < 60 &&
      new Date(c.expiry_date).getTime() > now
  );

  const isDateExpired = (dateStr: string | null) => dateStr && new Date(dateStr) < new Date();
  const isDateSoon = (dateStr: string | null) =>
    dateStr &&
    !isDateExpired(dateStr) &&
    (new Date(dateStr).getTime() - now) / 86400000 < 60;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 p-6">
        <RefreshCw size={20} className="animate-spin mr-2" /> Loading background checks…
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <UserCheck size={20} className="text-purple-400" />
          Background Checks
        </h1>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => refetch()}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => setShowInitiate(true)}>
            <Plus size={13} /> Initiate New Check
          </button>
        </div>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { label: 'Total', count: counts.total, color: 'text-gray-200', bg: '' },
          { label: 'Pending', count: counts.pending, color: 'text-gray-300', bg: 'bg-gray-800' },
          { label: 'In Progress', count: counts.in_progress, color: 'text-blue-300', bg: 'bg-blue-900/30' },
          { label: 'Passed', count: counts.passed, color: 'text-green-400', bg: 'bg-green-900/30' },
          { label: 'Failed', count: counts.failed, color: 'text-red-400', bg: 'bg-red-900/30' },
          { label: 'Expired', count: counts.expired, color: 'text-orange-400', bg: 'bg-orange-900/30' },
        ].map((item) => (
          <div key={item.label} className={`card ${item.bg} flex flex-col items-center py-3`}>
            <div className={`text-2xl font-bold ${item.color}`}>{item.count}</div>
            <div className="text-xs text-gray-500 mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Expiring Soon Banner */}
      {expiringSoon.length > 0 && (
        <div className="flex items-center gap-3 bg-amber-900/30 border border-amber-700/50 rounded-xl px-4 py-3">
          <AlertTriangle size={18} className="text-amber-400 flex-shrink-0" />
          <span className="text-sm text-amber-200">
            <strong>{expiringSoon.length}</strong> background{' '}
            {expiringSoon.length === 1 ? 'check' : 'checks'} expiring within the next 60 days
          </span>
          <button
            className="ml-auto text-xs text-amber-300 underline underline-offset-2"
            onClick={() => setStatusFilter('all')}
          >
            View all
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex gap-2 flex-wrap">
        {['all', 'pending', 'in_progress', 'passed', 'failed', 'expired'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              statusFilter === s
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {s === 'all' ? 'All' : s.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Checks Table */}
      {allChecks.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-12 text-gray-500">
          <UserCheck size={32} className="mb-2 text-gray-700" />
          <p className="text-sm">No background checks found.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Employee ID</th>
                  <th className="th">Check Type</th>
                  <th className="th">Provider</th>
                  <th className="th">Status</th>
                  <th className="th">Initiated</th>
                  <th className="th">Completed</th>
                  <th className="th">Expiry</th>
                  <th className="th">Adjudication</th>
                  <th className="th">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {allChecks.map((check) => {
                  const expired = isDateExpired(check.expiry_date);
                  const soon = !expired && isDateSoon(check.expiry_date);
                  return (
                    <tr key={check.id} className="hover:bg-gray-800/50">
                      <td className="td text-xs font-mono text-gray-400">{check.employee_id}</td>
                      <td className="td font-medium text-gray-200 text-sm">{check.check_type}</td>
                      <td className="td text-gray-400 text-sm">{check.provider}</td>
                      <td className="td">
                        <span className={`badge ${STATUS_BADGE[check.status] ?? 'bg-gray-700 text-gray-300'}`}>
                          {check.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="td text-xs text-gray-400">
                        {new Date(check.initiated_at).toLocaleDateString()}
                      </td>
                      <td className="td text-xs text-gray-400">
                        {check.completed_at
                          ? new Date(check.completed_at).toLocaleDateString()
                          : (
                            <span className="flex items-center gap-1 text-gray-600">
                              <Clock size={11} /> Pending
                            </span>
                          )}
                      </td>
                      <td className="td text-xs">
                        {check.expiry_date ? (
                          <span
                            className={
                              expired
                                ? 'text-red-400 font-semibold'
                                : soon
                                ? 'text-amber-400'
                                : 'text-gray-400'
                            }
                          >
                            {new Date(check.expiry_date).toLocaleDateString()}
                            {expired && ' ⚠'}
                            {soon && !expired && ' ⏰'}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="td">
                        {check.adjudication ? (
                          <span className={`badge ${ADJUDICATION_BADGE[check.adjudication] ?? 'bg-gray-700 text-gray-300'}`}>
                            {check.adjudication.replace(/_/g, ' ')}
                          </span>
                        ) : (
                          <span className="text-gray-600">—</span>
                        )}
                      </td>
                      <td className="td">
                        {check.status !== 'cancelled' && (
                          <button
                            className="btn-secondary text-xs py-0.5"
                            onClick={() => setUpdateCheck(check)}
                          >
                            Update
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modals */}
      {showInitiate && (
        <InitiateCheckModal
          onClose={() => setShowInitiate(false)}
          onDone={() => setShowInitiate(false)}
        />
      )}
      {updateCheck && (
        <UpdateStatusModal
          check={updateCheck}
          onClose={() => setUpdateCheck(null)}
          onDone={() => setUpdateCheck(null)}
        />
      )}
    </div>
  );
}
