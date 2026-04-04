import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  ShieldAlert,
  AlertTriangle,
  TrendingUp,
  Clock,
  Activity,
  Plus,
  Upload,
  Eye,
  Pencil,
  X,
} from 'lucide-react';
import { fetchRegisterSummary, fetchRisks, importFromFindings, closeRisk } from '../api';
import type { Risk } from '../types';
import RiskDetail from './RiskDetail';

interface Props {
  tenantId: string;
}

function scoreBand(score: number): 'critical' | 'high' | 'medium' | 'low' {
  if (score >= 20) return 'critical';
  if (score >= 15) return 'high';
  if (score >= 9) return 'medium';
  return 'low';
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-400 text-xs">—</span>;
  const band = scoreBand(score);
  const cls = {
    critical: 'score-badge score-critical',
    high: 'score-badge score-high',
    medium: 'score-badge score-medium',
    low: 'score-badge score-low',
  }[band];
  return <span className={cls}>{score}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    open: 'bg-blue-50 text-blue-700 ring-blue-600/20',
    in_treatment: 'bg-purple-50 text-purple-700 ring-purple-600/20',
    accepted: 'bg-gray-50 text-gray-600 ring-gray-500/20',
    closed: 'bg-green-50 text-green-700 ring-green-600/20',
    transferred: 'bg-yellow-50 text-yellow-700 ring-yellow-600/20',
  };
  const label: Record<string, string> = {
    open: 'Open',
    in_treatment: 'In Treatment',
    accepted: 'Accepted',
    closed: 'Closed',
    transferred: 'Transferred',
  };
  return (
    <span className={`status-badge ${map[status] ?? 'bg-gray-50 text-gray-600 ring-gray-500/20'}`}>
      {label[status] ?? status}
    </span>
  );
}

const DONUT_COLORS = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#eab308',
  low: '#16a34a',
};

const CATEGORY_COLORS = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16'];

export default function RiskDashboard({ tenantId }: Props) {
  const qc = useQueryClient();
  const [selectedRisk, setSelectedRisk] = useState<Risk | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);

  const { data: summary } = useQuery({
    queryKey: ['risk-summary', tenantId],
    queryFn: fetchRegisterSummary,
  });

  const { data: risks = [], isLoading } = useQuery({
    queryKey: ['risks', tenantId],
    queryFn: () => fetchRisks(),
  });

  const importMut = useMutation({
    mutationFn: importFromFindings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
    },
  });

  const closeMut = useMutation({
    mutationFn: (id: string) => closeRisk(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
    },
  });

  const donutData = summary
    ? [
        { name: 'Critical', value: summary.score_distribution.critical, color: DONUT_COLORS.critical },
        { name: 'High', value: summary.score_distribution.high, color: DONUT_COLORS.high },
        { name: 'Medium', value: summary.score_distribution.medium, color: DONUT_COLORS.medium },
        { name: 'Low', value: summary.score_distribution.low, color: DONUT_COLORS.low },
      ]
    : [];

  const categoryBarData = summary
    ? Object.entries(summary.by_category).map(([cat, count]) => ({ category: cat, count }))
    : [];

  const inTreatmentCount = risks.filter((r) => r.status === 'in_treatment').length;
  const today = new Date().toISOString().slice(0, 10);
  const overdueCount = risks.filter(
    (r) => r.review_date && r.review_date < today && r.status !== 'closed'
  ).length;

  const metricCards = [
    {
      label: 'Total Risks',
      value: summary?.total ?? risks.length,
      icon: ShieldAlert,
      color: 'text-gray-700',
      bg: 'bg-white',
    },
    {
      label: 'Critical',
      value: summary?.score_distribution.critical ?? 0,
      icon: AlertTriangle,
      color: 'text-red-600',
      bg: 'bg-red-50',
    },
    {
      label: 'High',
      value: summary?.score_distribution.high ?? 0,
      icon: TrendingUp,
      color: 'text-orange-600',
      bg: 'bg-orange-50',
    },
    {
      label: 'Above Appetite',
      value: summary?.above_appetite ?? 0,
      icon: AlertTriangle,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
    },
    {
      label: 'In Treatment',
      value: inTreatmentCount,
      icon: Activity,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      label: 'Overdue Review',
      value: summary?.overdue_review ?? overdueCount,
      icon: Clock,
      color: 'text-red-600',
      bg: 'bg-red-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Risk Register</h1>
        <div className="flex gap-3">
          <button
            onClick={() => importMut.mutate()}
            disabled={importMut.isPending}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60"
          >
            <Upload className="h-4 w-4" />
            Import from Findings
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            <Plus className="h-4 w-4" />
            Add Risk
          </button>
        </div>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {metricCards.map((card) => (
          <div key={card.label} className={`rounded-xl p-4 shadow-sm ring-1 ring-gray-200 ${card.bg}`}>
            <div className="flex items-center gap-2">
              <card.icon className={`h-5 w-5 ${card.color}`} />
              <span className="text-xs font-medium text-gray-500">{card.label}</span>
            </div>
            <p className={`mt-2 text-3xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Donut */}
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Score Distribution</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={donutData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={3}
                dataKey="value"
              >
                {donutData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [`${v} risks`]} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Category Breakdown */}
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Risks by Category</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={categoryBarData} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={80} />
              <Tooltip />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {categoryBarData.map((_, i) => (
                  <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Risk Table */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-gray-200">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {['Risk ID', 'Title', 'Category', 'Owner', 'Inherent', 'Residual', 'Status', 'Review Date', 'Actions'].map(
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
                  <td colSpan={9} className="py-10 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              )}
              {!isLoading && risks.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-10 text-center text-gray-400">
                    No risks found.
                  </td>
                </tr>
              )}
              {risks.map((risk) => {
                const overdue =
                  risk.review_date && risk.review_date < today && risk.status !== 'closed';
                return (
                  <tr
                    key={risk.id}
                    className="cursor-pointer hover:bg-gray-50"
                    onClick={() => setSelectedRisk(risk)}
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-600">
                      {risk.risk_id}
                    </td>
                    <td className="max-w-xs px-4 py-3 font-medium text-gray-900 truncate">
                      {risk.title}
                    </td>
                    <td className="px-4 py-3">
                      {risk.category_name && (
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                          {risk.category_name}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{risk.owner ?? '—'}</td>
                    <td className="px-4 py-3">
                      <ScoreBadge score={risk.inherent_score} />
                    </td>
                    <td className="px-4 py-3">
                      <ScoreBadge score={risk.residual_score} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={risk.status} />
                    </td>
                    <td
                      className={`px-4 py-3 text-xs ${overdue ? 'font-semibold text-red-600' : 'text-gray-600'}`}
                    >
                      {risk.review_date ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div
                        className="flex gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          title="View"
                          onClick={() => setSelectedRisk(risk)}
                          className="rounded p-1 text-gray-400 hover:text-indigo-600"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                        <button
                          title="Edit"
                          className="rounded p-1 text-gray-400 hover:text-indigo-600"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        {risk.status !== 'closed' && (
                          <button
                            title="Close"
                            onClick={() => closeMut.mutate(risk.id)}
                            className="rounded p-1 text-gray-400 hover:text-red-600"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Risk Detail Drawer */}
      {selectedRisk && (
        <RiskDetail
          risk={selectedRisk}
          tenantId={tenantId}
          onClose={() => setSelectedRisk(null)}
          onUpdate={() => {
            qc.invalidateQueries({ queryKey: ['risks'] });
            qc.invalidateQueries({ queryKey: ['risk-summary'] });
            setSelectedRisk(null);
          }}
        />
      )}

      {/* Add Risk Modal placeholder */}
      {showAddForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add Risk</h2>
              <button onClick={() => setShowAddForm(false)}>
                <X className="h-5 w-5 text-gray-500" />
              </button>
            </div>
            <p className="text-sm text-gray-500">Risk creation form — connect to your API.</p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                onClick={() => setShowAddForm(false)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm"
              >
                Cancel
              </button>
              <button className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
