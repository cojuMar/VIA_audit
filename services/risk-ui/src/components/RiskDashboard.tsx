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
  Search,
} from 'lucide-react';
import { fetchRegisterSummary, fetchRisks, fetchCategories, createRisk, updateRisk, importFromFindings, closeRisk } from '../api';
import type { Risk } from '../types';
import RiskDetail from './RiskDetail';
import { useToast } from './Toaster';

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

const LIKELIHOOD_LABELS: Record<number, string> = { 1: 'Rare', 2: 'Unlikely', 3: 'Possible', 4: 'Likely', 5: 'Almost Certain' };
const IMPACT_LABELS: Record<number, string> = { 1: 'Negligible', 2: 'Minor', 3: 'Moderate', 4: 'Major', 5: 'Catastrophic' };

const DEFAULT_FORM = {
  title: '',
  description: '',
  category_id: '',
  owner: '',
  department: '',
  inherent_likelihood: 3,
  inherent_impact: 3,
  review_date: '',
};

export default function RiskDashboard({ tenantId }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [selectedRisk, setSelectedRisk] = useState<Risk | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingRisk, setEditingRisk] = useState<Risk | null>(null);
  const [formData, setFormData] = useState({ ...DEFAULT_FORM });
  const [formError, setFormError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [confirmClose, setConfirmClose] = useState<Risk | null>(null);

  const { data: summary } = useQuery({
    queryKey: ['risk-summary', tenantId],
    queryFn: fetchRegisterSummary,
  });

  const { data: risks = [], isLoading } = useQuery({
    queryKey: ['risks', tenantId],
    queryFn: () => fetchRisks(),
  });

  const { data: categories = [] } = useQuery({
    queryKey: ['risk-categories', tenantId],
    queryFn: fetchCategories,
  });

  const createMut = useMutation({
    mutationFn: createRisk,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
      setShowAddForm(false);
      setFormData({ ...DEFAULT_FORM });
      setFormError(null);
      toast('Risk created successfully', 'success');
    },
    onError: (err: Error) => {
      setFormError(err.message ?? 'Failed to create risk');
      toast('Failed to create risk', 'error');
    },
  });

  const importMut = useMutation({
    mutationFn: importFromFindings,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
      toast(`Imported ${data.imported} risk${data.imported !== 1 ? 's' : ''} from findings`, 'success');
    },
    onError: () => {
      toast('Import from findings failed', 'error');
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Risk> }) => updateRisk(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
      setEditingRisk(null);
      setFormData({ ...DEFAULT_FORM });
      setFormError(null);
      toast('Risk updated successfully', 'success');
    },
    onError: (err: Error) => {
      setFormError(err.message ?? 'Failed to update risk');
      toast('Failed to update risk', 'error');
    },
  });

  const closeMut = useMutation({
    mutationFn: (id: string) => closeRisk(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] });
      qc.invalidateQueries({ queryKey: ['risk-summary'] });
      setConfirmClose(null);
      toast('Risk closed', 'success');
    },
    onError: () => {
      toast('Failed to close risk', 'error');
    },
  });

  const openEditForm = (risk: Risk) => {
    setFormData({
      title: risk.title,
      description: risk.description ?? '',
      category_id: risk.category_id ?? '',
      owner: risk.owner ?? '',
      department: risk.department ?? '',
      inherent_likelihood: risk.inherent_likelihood ?? 3,
      inherent_impact: risk.inherent_impact ?? 3,
      review_date: risk.review_date ?? '',
    });
    setFormError(null);
    setEditingRisk(risk);
  };

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

  const filteredRisks = searchQuery.trim()
    ? risks.filter((r) => {
        const q = searchQuery.toLowerCase();
        return (
          r.title.toLowerCase().includes(q) ||
          (r.risk_id?.toLowerCase().includes(q) ?? false) ||
          (r.owner?.toLowerCase().includes(q) ?? false) ||
          (r.department?.toLowerCase().includes(q) ?? false) ||
          (r.category_name?.toLowerCase().includes(q) ?? false) ||
          r.status.toLowerCase().includes(q)
        );
      })
    : risks;

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
        {/* Search bar */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
          <Search className="h-4 w-4 text-gray-400 flex-shrink-0" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search risks by title, ID, owner, category, status…"
            className="flex-1 text-sm outline-none text-gray-700 placeholder-gray-400"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="text-gray-400 hover:text-gray-600">
              <X className="h-4 w-4" />
            </button>
          )}
          {searchQuery && (
            <span className="text-xs text-gray-500">{filteredRisks.length} of {risks.length}</span>
          )}
        </div>
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
              {!isLoading && filteredRisks.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-10 text-center text-gray-400">
                    {searchQuery ? 'No risks match your search.' : 'No risks found.'}
                  </td>
                </tr>
              )}
              {filteredRisks.map((risk) => {
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
                          onClick={() => openEditForm(risk)}
                          className="rounded p-1 text-gray-400 hover:text-indigo-600"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        {risk.status !== 'closed' && (
                          <button
                            title="Close Risk"
                            onClick={() => setConfirmClose(risk)}
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

      {/* Confirm Close Dialog */}
      {confirmClose && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-xl bg-white shadow-2xl overflow-hidden">
            <div className="px-6 py-5">
              <h2 className="text-lg font-semibold text-gray-900 mb-2">Close Risk?</h2>
              <p className="text-sm text-gray-600">
                Are you sure you want to close <strong>{confirmClose.risk_id}</strong>: "{confirmClose.title}"?
                This will mark the risk as closed and remove it from active tracking.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                onClick={() => setConfirmClose(null)}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => closeMut.mutate(confirmClose.id)}
                disabled={closeMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {closeMut.isPending ? 'Closing…' : 'Close Risk'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Risk Modal */}
      {editingRisk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-900">Edit Risk — {editingRisk.risk_id}</h2>
              <button onClick={() => { setEditingRisk(null); setFormError(null); }}>
                <X className="h-5 w-5 text-gray-500 hover:text-gray-700" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
              {formError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {formError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Risk Title <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Category <span className="text-red-500">*</span></label>
                  <select
                    value={formData.category_id}
                    onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Select category…</option>
                    {categories.map((cat) => (
                      <option key={cat.id} value={cat.id}>{cat.display_name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Owner</label>
                  <input
                    type="text"
                    value={formData.owner}
                    onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
                  <input
                    type="text"
                    value={formData.department}
                    onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Review Date</label>
                  <input
                    type="date"
                    value={formData.review_date}
                    onChange={(e) => setFormData({ ...formData, review_date: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Inherent Likelihood — <span className="text-indigo-600 font-semibold">{LIKELIHOOD_LABELS[formData.inherent_likelihood]}</span>
                  </label>
                  <input
                    type="range" min={1} max={5} step={1}
                    value={formData.inherent_likelihood}
                    onChange={(e) => setFormData({ ...formData, inherent_likelihood: Number(e.target.value) })}
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>Rare</span><span>Almost Certain</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Inherent Impact — <span className="text-indigo-600 font-semibold">{IMPACT_LABELS[formData.inherent_impact]}</span>
                  </label>
                  <input
                    type="range" min={1} max={5} step={1}
                    value={formData.inherent_impact}
                    onChange={(e) => setFormData({ ...formData, inherent_impact: Number(e.target.value) })}
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>Negligible</span><span>Catastrophic</span>
                  </div>
                </div>
              </div>
              <div className="rounded-lg bg-indigo-50 border border-indigo-100 px-4 py-3 flex items-center gap-3">
                <ShieldAlert className="h-5 w-5 text-indigo-500 flex-shrink-0" />
                <span className="text-sm text-indigo-700">
                  Inherent Risk Score: <strong>{formData.inherent_likelihood * formData.inherent_impact}</strong> / 25
                  {' '}({formData.inherent_likelihood * formData.inherent_impact >= 20 ? 'Critical' :
                         formData.inherent_likelihood * formData.inherent_impact >= 15 ? 'High' :
                         formData.inherent_likelihood * formData.inherent_impact >= 9 ? 'Medium' : 'Low'})
                </span>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                onClick={() => { setEditingRisk(null); setFormError(null); }}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (!formData.title.trim()) { setFormError('Risk title is required.'); return; }
                  if (!formData.category_id) { setFormError('Please select a category.'); return; }
                  setFormError(null);
                  updateMut.mutate({
                    id: editingRisk.id,
                    payload: {
                      title: formData.title.trim(),
                      description: formData.description.trim() || undefined,
                      category_id: formData.category_id,
                      owner: formData.owner.trim() || null,
                      department: formData.department.trim() || null,
                      inherent_likelihood: formData.inherent_likelihood,
                      inherent_impact: formData.inherent_impact,
                      review_date: formData.review_date || null,
                    } as Partial<Risk>,
                  });
                }}
                disabled={updateMut.isPending}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {updateMut.isPending ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Risk Modal */}
      {showAddForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-900">Add New Risk</h2>
              <button onClick={() => { setShowAddForm(false); setFormError(null); setFormData({ ...DEFAULT_FORM }); }}>
                <X className="h-5 w-5 text-gray-500 hover:text-gray-700" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
              {formError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {formError}
                </div>
              )}

              {/* Title */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Risk Title <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g. Unauthorized data access via legacy API"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                  placeholder="Describe the risk, its cause and potential consequences…"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>

              {/* Category + Owner */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Category <span className="text-red-500">*</span></label>
                  <select
                    value={formData.category_id}
                    onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Select category…</option>
                    {categories.map((cat) => (
                      <option key={cat.id} value={cat.id}>{cat.display_name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Owner</label>
                  <input
                    type="text"
                    value={formData.owner}
                    onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                    placeholder="e.g. John Smith"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {/* Department + Review Date */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
                  <input
                    type="text"
                    value={formData.department}
                    onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                    placeholder="e.g. Engineering"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Review Date</label>
                  <input
                    type="date"
                    value={formData.review_date}
                    onChange={(e) => setFormData({ ...formData, review_date: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {/* Likelihood + Impact sliders */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Inherent Likelihood — <span className="text-indigo-600 font-semibold">{LIKELIHOOD_LABELS[formData.inherent_likelihood]}</span>
                  </label>
                  <input
                    type="range" min={1} max={5} step={1}
                    value={formData.inherent_likelihood}
                    onChange={(e) => setFormData({ ...formData, inherent_likelihood: Number(e.target.value) })}
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>Rare</span><span>Almost Certain</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Inherent Impact — <span className="text-indigo-600 font-semibold">{IMPACT_LABELS[formData.inherent_impact]}</span>
                  </label>
                  <input
                    type="range" min={1} max={5} step={1}
                    value={formData.inherent_impact}
                    onChange={(e) => setFormData({ ...formData, inherent_impact: Number(e.target.value) })}
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>Negligible</span><span>Catastrophic</span>
                  </div>
                </div>
              </div>

              {/* Score preview */}
              <div className="rounded-lg bg-indigo-50 border border-indigo-100 px-4 py-3 flex items-center gap-3">
                <ShieldAlert className="h-5 w-5 text-indigo-500 flex-shrink-0" />
                <span className="text-sm text-indigo-700">
                  Inherent Risk Score: <strong>{formData.inherent_likelihood * formData.inherent_impact}</strong> / 25
                  {' '}({formData.inherent_likelihood * formData.inherent_impact >= 20 ? 'Critical' :
                         formData.inherent_likelihood * formData.inherent_impact >= 15 ? 'High' :
                         formData.inherent_likelihood * formData.inherent_impact >= 9 ? 'Medium' : 'Low'})
                </span>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                onClick={() => { setShowAddForm(false); setFormError(null); setFormData({ ...DEFAULT_FORM }); }}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (!formData.title.trim()) { setFormError('Risk title is required.'); return; }
                  if (!formData.category_id) { setFormError('Please select a category.'); return; }
                  setFormError(null);
                  createMut.mutate({
                    title: formData.title.trim(),
                    description: formData.description.trim() || undefined,
                    category_id: formData.category_id,
                    owner: formData.owner.trim() || null,
                    department: formData.department.trim() || null,
                    inherent_likelihood: formData.inherent_likelihood,
                    inherent_impact: formData.inherent_impact,
                    review_date: formData.review_date || null,
                    status: 'open',
                  } as Partial<Risk>);
                }}
                disabled={createMut.isPending}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {createMut.isPending ? 'Saving…' : 'Save Risk'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
