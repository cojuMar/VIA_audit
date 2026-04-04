import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Star, RefreshCw } from 'lucide-react';
import { fetchTreatments, updateTreatment, fetchCategories } from '../api';
import type { RiskTreatment, TreatmentType } from '../types';

interface Props {
  tenantId: string;
}

const TREATMENT_TYPES: TreatmentType[] = ['mitigate', 'accept', 'transfer', 'avoid'];
const TREATMENT_STATUSES = ['planned', 'in_progress', 'completed', 'cancelled'];

const typeColor: Record<TreatmentType, string> = {
  mitigate: 'bg-blue-50 text-blue-700 ring-blue-600/20',
  accept: 'bg-gray-50 text-gray-600 ring-gray-500/20',
  transfer: 'bg-purple-50 text-purple-700 ring-purple-600/20',
  avoid: 'bg-red-50 text-red-700 ring-red-600/20',
};

const typeCardColor: Record<TreatmentType, string> = {
  mitigate: 'border-blue-200 bg-blue-50',
  accept: 'border-gray-200 bg-gray-50',
  transfer: 'border-purple-200 bg-purple-50',
  avoid: 'border-red-200 bg-red-50',
};

const statusColor: Record<string, string> = {
  planned: 'bg-gray-50 text-gray-600 ring-gray-500/20',
  in_progress: 'bg-blue-50 text-blue-700 ring-blue-600/20',
  completed: 'bg-green-50 text-green-700 ring-green-600/20',
  cancelled: 'bg-red-50 text-red-700 ring-red-600/20',
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge ${statusColor[status] ?? 'bg-gray-50 text-gray-600 ring-gray-500/20'} capitalize`}>
      {status.replace('_', ' ')}
    </span>
  );
}

function TreatmentBadge({ type }: { type: TreatmentType }) {
  return (
    <span className={`status-badge ${typeColor[type]} capitalize`}>{type}</span>
  );
}

function StarRating({ rating }: { rating: number | null }) {
  if (rating === null) return <span className="text-gray-400 text-xs">—</span>;
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={`h-3.5 w-3.5 ${i <= rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`} />
      ))}
    </div>
  );
}

export default function TreatmentTracker({ tenantId }: Props) {
  const qc = useQueryClient();
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [newStatus, setNewStatus] = useState<string>('');

  const { data: treatments = [], isLoading } = useQuery({
    queryKey: ['treatments-all', tenantId],
    queryFn: () => fetchTreatments(),
  });

  const { data: _categories = [] } = useQuery({
    queryKey: ['categories', tenantId],
    queryFn: fetchCategories,
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<RiskTreatment> }) =>
      updateTreatment(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['treatments-all'] });
      setUpdatingId(null);
    },
  });

  const today = new Date().toISOString().slice(0, 10);

  // Derived counts
  const totalCount = treatments.length;
  const plannedCount = treatments.filter((t) => t.status === 'planned').length;
  const inProgressCount = treatments.filter((t) => t.status === 'in_progress').length;
  const completedCount = treatments.filter((t) => t.status === 'completed').length;
  const cancelledCount = treatments.filter((t) => t.status === 'cancelled').length;
  const overdueCount = treatments.filter(
    (t) => t.target_date && t.target_date < today && !['completed', 'cancelled'].includes(t.status)
  ).length;

  // Type breakdown
  const typeStats = TREATMENT_TYPES.map((type) => {
    const group = treatments.filter((t) => t.treatment_type === type);
    const rated = group.filter((t) => t.effectiveness_rating !== null);
    const avgEff =
      rated.length > 0
        ? rated.reduce((sum, t) => sum + (t.effectiveness_rating ?? 0), 0) / rated.length
        : null;
    return { type, count: group.length, avgEff };
  });

  // Effectiveness trend (completed treatments sorted by completed_date)
  const trendData = treatments
    .filter((t) => t.status === 'completed' && t.completed_date && t.effectiveness_rating !== null)
    .sort((a, b) => (a.completed_date! < b.completed_date! ? -1 : 1))
    .map((t) => ({
      date: t.completed_date!.slice(0, 7),
      effectiveness: t.effectiveness_rating,
    }));

  // Filtered table
  const filtered = treatments.filter((t) => {
    if (typeFilter !== 'all' && t.treatment_type !== typeFilter) return false;
    if (statusFilter !== 'all' && t.status !== statusFilter) return false;
    return true;
  });

  const summaryCards = [
    { label: 'Total', value: totalCount, color: 'text-gray-700', bg: 'bg-white' },
    { label: 'Planned', value: plannedCount, color: 'text-gray-600', bg: 'bg-gray-50' },
    { label: 'In Progress', value: inProgressCount, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: 'Completed', value: completedCount, color: 'text-green-600', bg: 'bg-green-50' },
    { label: 'Cancelled', value: cancelledCount, color: 'text-gray-400', bg: 'bg-gray-50' },
    { label: 'Overdue', value: overdueCount, color: 'text-red-600', bg: 'bg-red-50' },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Treatment Tracker</h1>

      {/* Summary Strip */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {summaryCards.map((card) => (
          <div key={card.label} className={`rounded-xl p-4 shadow-sm ring-1 ring-gray-200 ${card.bg}`}>
            <p className="text-xs font-medium text-gray-500">{card.label}</p>
            <p className={`mt-1.5 text-3xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Type Breakdown */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {typeStats.map(({ type, count, avgEff }) => (
          <div key={type} className={`rounded-xl border p-4 shadow-sm ${typeCardColor[type]}`}>
            <div className="flex items-center justify-between mb-2">
              <TreatmentBadge type={type} />
              <span className="text-2xl font-bold text-gray-900">{count}</span>
            </div>
            <div className="text-xs text-gray-500">
              Avg effectiveness:{' '}
              {avgEff !== null ? (
                <span className="font-medium text-gray-700">{avgEff.toFixed(1)} / 5</span>
              ) : (
                '—'
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Effectiveness Trend */}
      {trendData.length > 0 && (
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Effectiveness Trend (Completed Treatments)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 5]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="effectiveness"
                stroke="#6366f1"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filters + Table */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-gray-200">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4 border-b border-gray-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Type:</label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-1 text-sm"
            >
              <option value="all">All</option>
              {TREATMENT_TYPES.map((t) => (
                <option key={t} value={t} className="capitalize">{t}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-1 text-sm"
            >
              <option value="all">All</option>
              {TREATMENT_STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
          <span className="ml-auto text-xs text-gray-400">{filtered.length} treatments</span>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {['Risk ID', 'Title', 'Type', 'Owner', 'Status', 'Target Date', 'Effectiveness', 'Actions'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {isLoading && (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-gray-400">Loading…</td>
                </tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-gray-400">No treatments found.</td>
                </tr>
              )}
              {filtered.map((t) => {
                const overdue =
                  t.target_date &&
                  t.target_date < today &&
                  !['completed', 'cancelled'].includes(t.status);
                return (
                  <tr key={t.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-600">
                      {t.risk_id.slice(0, 8)}…
                    </td>
                    <td className="max-w-xs px-4 py-3 font-medium text-gray-900 truncate">{t.title}</td>
                    <td className="px-4 py-3">
                      <TreatmentBadge type={t.treatment_type} />
                    </td>
                    <td className="px-4 py-3 text-gray-600">{t.owner ?? '—'}</td>
                    <td className="px-4 py-3">
                      {updatingId === t.id ? (
                        <div className="flex items-center gap-2">
                          <select
                            value={newStatus}
                            onChange={(e) => setNewStatus(e.target.value)}
                            className="rounded border border-gray-300 px-2 py-1 text-xs"
                          >
                            {TREATMENT_STATUSES.map((s) => (
                              <option key={s} value={s}>{s.replace('_', ' ')}</option>
                            ))}
                          </select>
                          <button
                            onClick={() => updateMut.mutate({ id: t.id, payload: { status: newStatus } })}
                            className="rounded bg-indigo-600 px-2 py-1 text-xs text-white"
                          >
                            OK
                          </button>
                          <button onClick={() => setUpdatingId(null)} className="text-xs text-gray-400">✕</button>
                        </div>
                      ) : (
                        <StatusBadge status={t.status} />
                      )}
                    </td>
                    <td className={`px-4 py-3 text-xs ${overdue ? 'font-semibold text-red-600' : 'text-gray-600'}`}>
                      {t.target_date ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <StarRating rating={t.effectiveness_rating} />
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => {
                          setUpdatingId(t.id);
                          setNewStatus(t.status);
                        }}
                        title="Update Status"
                        className="inline-flex items-center gap-1 rounded p-1 text-xs text-gray-400 hover:text-indigo-600"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Update
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
