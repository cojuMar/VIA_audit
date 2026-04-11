import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import {
  ArrowLeft,
  Plus,
  Calendar,
  User,
  ClipboardList,
  AlertTriangle,
  FileText,
  ChevronRight,
} from 'lucide-react';
import {
  listEngagements,
  getEngagementDashboard,
  createEngagement,
  type EngagementCreate,
} from '../api';
import type { AuditEngagement, EngagementDashboard, EngagementStatus } from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusColor(s: EngagementStatus) {
  const map: Record<EngagementStatus, string> = {
    planning: 'bg-purple-100 text-purple-800',
    fieldwork: 'bg-blue-100 text-blue-800',
    review: 'bg-yellow-100 text-yellow-800',
    complete: 'bg-green-100 text-green-800',
    cancelled: 'bg-gray-100 text-gray-500',
  };
  return map[s] ?? 'bg-gray-100 text-gray-600';
}

function typeColor(t: string | null | undefined) {
  if (!t) return 'bg-gray-100 text-gray-700';
  const map: Record<string, string> = {
    internal: 'bg-indigo-100 text-indigo-800',
    external: 'bg-teal-100 text-teal-800',
    sox: 'bg-red-100 text-red-700',
    it_general: 'bg-orange-100 text-orange-800',
    operational: 'bg-cyan-100 text-cyan-800',
  };
  return map[t.toLowerCase()] ?? 'bg-gray-100 text-gray-700';
}

function formatPeriod(start: string | null, end: string | null, fy: number | null) {
  const parts: string[] = [];
  if (fy) parts.push(`FY${fy}`);
  if (start && end) {
    const fmt = (d: string) =>
      new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    parts.push(`${fmt(start)} – ${fmt(end)}`);
  }
  return parts.join(' | ') || '—';
}

function daysUntil(dateStr: string | null) {
  if (!dateStr) return null;
  const diff = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86_400_000);
  return diff;
}

const SEVERITY_BADGES: { key: string; label: string; cls: string }[] = [
  { key: 'critical', label: 'Critical', cls: 'bg-red-100 text-red-800' },
  { key: 'high', label: 'High', cls: 'bg-orange-100 text-orange-800' },
  { key: 'medium', label: 'Medium', cls: 'bg-yellow-100 text-yellow-800' },
  { key: 'low', label: 'Low', cls: 'bg-blue-100 text-blue-800' },
  { key: 'informational', label: 'Info', cls: 'bg-gray-100 text-gray-600' },
];

const STEPS: EngagementStatus[] = ['planning', 'fieldwork', 'review', 'complete'];
const STEP_LABELS: Record<string, string> = {
  planning: 'Planning',
  fieldwork: 'Fieldwork',
  review: 'Review',
  complete: 'Complete',
};

const WP_COLORS = ['#93c5fd', '#fbbf24', '#6ee7b7', '#818cf8'];

// ── New Engagement Modal ───────────────────────────────────────────────────────

interface NewEngagementModalProps {
  tenantId: string;
  onClose: () => void;
}

function NewEngagementModal({ tenantId, onClose }: NewEngagementModalProps) {
  const qc = useQueryClient();
  const [form, setForm] = useState<EngagementCreate>({
    engagement_name: '',
    engagement_type: 'internal',
    fiscal_year: null,
    period_start: null,
    period_end: null,
    lead_auditor: null,
    description: null,
  });

  const mut = useMutation({
    mutationFn: () => createEngagement(tenantId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['engagements', tenantId] });
      onClose();
    },
  });

  function set(k: keyof EngagementCreate, v: unknown) {
    setForm((f) => ({ ...f, [k]: v || null }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">New Engagement</h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="form-label">Engagement Name *</label>
            <input
              className="form-input"
              value={form.engagement_name}
              onChange={(e) => set('engagement_name', e.target.value)}
            />
          </div>
          <div>
            <label className="form-label">Type</label>
            <select
              className="form-input"
              value={form.engagement_type}
              onChange={(e) => set('engagement_type', e.target.value)}
            >
              {['internal', 'external', 'sox', 'it_general', 'operational'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Fiscal Year</label>
            <input
              type="number"
              className="form-input"
              placeholder="2024"
              onChange={(e) => set('fiscal_year', e.target.value ? Number(e.target.value) : null)}
            />
          </div>
          <div>
            <label className="form-label">Period Start</label>
            <input type="date" className="form-input" onChange={(e) => set('period_start', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Period End</label>
            <input type="date" className="form-input" onChange={(e) => set('period_end', e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="form-label">Lead Auditor</label>
            <input className="form-input" onChange={(e) => set('lead_auditor', e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="form-label">Description</label>
            <textarea
              className="form-input"
              rows={3}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>
        </div>
        {mut.isError && (
          <p className="text-sm text-red-600">Failed to create engagement.</p>
        )}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!form.engagement_name || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Engagement Card ───────────────────────────────────────────────────────────

function EngagementCard({ eng, onClick }: { eng: AuditEngagement; onClick: () => void }) {
  const name = eng.engagement_name ?? eng.title ?? 'Untitled';
  const type = eng.engagement_type ?? eng.audit_type;
  const periodStart = eng.period_start ?? eng.planned_start_date ?? null;
  const periodEnd = eng.period_end ?? eng.planned_end_date ?? null;
  const fiscalYear = eng.fiscal_year ?? null;
  return (
    <div
      className="card p-4 cursor-pointer hover:shadow-md transition-shadow space-y-3"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-gray-900 leading-tight">{name}</h3>
        <div className="flex gap-1 flex-shrink-0">
          {type && <span className={`badge ${typeColor(type)}`}>{type}</span>}
          <span className={`badge ${statusColor(eng.status as EngagementStatus)}`}>{eng.status}</span>
        </div>
      </div>
      <div className="flex items-center gap-1 text-xs text-gray-500">
        <Calendar className="w-3 h-3" />
        {formatPeriod(periodStart, periodEnd, fiscalYear)}
      </div>
      {eng.lead_auditor && (
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <User className="w-3 h-3" />
          {eng.lead_auditor}
        </div>
      )}
      <div className="flex items-center gap-1">
        <ChevronRight className="w-3 h-3 text-gray-400 ml-auto" />
      </div>
    </div>
  );
}

// ── Detail Stepper ────────────────────────────────────────────────────────────

function StatusStepper({ status }: { status: EngagementStatus }) {
  const idx = STEPS.indexOf(status);
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((step, i) => {
        const active = i === idx;
        const done = i < idx;
        return (
          <div key={step} className="flex items-center">
            <div
              className={`px-3 py-1 text-xs font-medium rounded-full ${
                active
                  ? 'bg-blue-600 text-white'
                  : done
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-400'
              }`}
            >
              {STEP_LABELS[step]}
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-6 h-0.5 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Engagement Detail ─────────────────────────────────────────────────────────

interface DetailProps {
  tenantId: string;
  engagement: AuditEngagement;
  onBack: () => void;
  onNavigate: (tab: string) => void;
}

function EngagementDetailView({ tenantId, engagement, onBack, onNavigate }: DetailProps) {
  const { data: dash } = useQuery<EngagementDashboard>({
    queryKey: ['dashboard', tenantId, engagement.id],
    queryFn: () => getEngagementDashboard(tenantId, engagement.id),
  });

  const engName = engagement.engagement_name ?? engagement.title ?? 'Untitled';
  const periodStart = engagement.period_start ?? engagement.planned_start_date ?? null;
  const periodEnd = engagement.period_end ?? engagement.planned_end_date ?? null;
  const fiscalYear = engagement.fiscal_year ?? null;
  const stepperStatus = (STEPS.includes(engagement.status as EngagementStatus) ? engagement.status : 'planning') as EngagementStatus;

  const days = daysUntil(periodEnd);
  const pbc = dash?.pbc_summary;
  const issues = dash?.issue_summary;
  const wps = dash?.workpaper_summary;

  const wpChartData = wps
    ? [
        { name: 'Draft', value: wps.draft },
        { name: 'In Review', value: wps.in_review },
        { name: 'Reviewed', value: wps.total - wps.draft - wps.in_review - wps.final },
        { name: 'Final', value: wps.final },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900">{engName}</h1>
          <p className="text-sm text-gray-500">
            {formatPeriod(periodStart, periodEnd, fiscalYear)}
          </p>
        </div>
        <StatusStepper status={stepperStatus} />
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: 'PBC Completion',
            value: pbc ? `${pbc.completion_pct.toFixed(0)}%` : '—',
            sub: pbc ? `${pbc.fulfilled} / ${pbc.total} requests` : '',
            color: 'text-blue-600',
          },
          {
            label: 'Open Issues',
            value: issues?.open_count ?? '—',
            sub: `${issues?.total ?? 0} total`,
            color: 'text-orange-600',
          },
          {
            label: 'Workpapers Final',
            value: wps ? `${wps.final} / ${wps.total}` : '—',
            sub: wps ? `${wps.completion_pct.toFixed(0)}% complete` : '',
            color: 'text-green-600',
          },
          {
            label: 'Days to Period End',
            value: days !== null ? (days < 0 ? 'Ended' : `${days}d`) : '—',
            sub: periodEnd ?? '',
            color: days !== null && days < 14 ? 'text-red-600' : 'text-gray-700',
          },
        ].map((c) => (
          <div key={c.label} className="card p-4 text-center">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{c.label}</p>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-xs text-gray-400 mt-1">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* PBC Progress + Issue breakdown + WP donut */}
      <div className="grid grid-cols-3 gap-4">
        {/* PBC Progress bar */}
        <div className="card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">PBC Progress</h3>
          {pbc ? (
            <>
              <div className="w-full h-4 rounded-full bg-gray-100 overflow-hidden flex">
                {pbc.total > 0 && (
                  <>
                    <div
                      className="bg-green-500 h-full transition-all"
                      style={{ width: `${(pbc.fulfilled / pbc.total) * 100}%` }}
                    />
                    <div
                      className="bg-gray-300 h-full transition-all"
                      style={{ width: `${(pbc.open / pbc.total) * 100}%` }}
                    />
                  </>
                )}
              </div>
              <div className="flex gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  {pbc.fulfilled} fulfilled
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-gray-300" />
                  {pbc.open} open
                </span>
              </div>
            </>
          ) : (
            <p className="text-xs text-gray-400">No data</p>
          )}
        </div>

        {/* Issue breakdown */}
        <div className="card p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">Issues by Severity</h3>
          <div className="flex flex-wrap gap-2">
            {SEVERITY_BADGES.map((b) => (
              <span key={b.key} className={`badge ${b.cls}`}>
                {b.label}: {issues?.by_severity?.[b.key] ?? 0}
              </span>
            ))}
          </div>
        </div>

        {/* Workpaper donut */}
        <div className="card p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">Workpaper Status</h3>
          {wpChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={100}>
              <PieChart>
                <Pie
                  data={wpChartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={28}
                  outerRadius={44}
                  dataKey="value"
                >
                  {wpChartData.map((_, i) => (
                    <Cell key={i} fill={WP_COLORS[i % WP_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v, n) => [`${v}`, n]} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-gray-400">No workpapers</p>
          )}
        </div>
      </div>

      {/* Quick navigation */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { tab: 'pbc', icon: ClipboardList, label: 'PBC Requests', sub: pbc ? `${pbc.total} items` : '' },
          { tab: 'issues', icon: AlertTriangle, label: 'Issue Register', sub: issues ? `${issues.total} issues` : '' },
          { tab: 'workpapers', icon: FileText, label: 'Workpapers', sub: wps ? `${wps.total} workpapers` : '' },
        ].map((n) => (
          <button
            key={n.tab}
            className="card p-5 flex flex-col items-center gap-2 hover:bg-gray-50 transition-colors cursor-pointer"
            onClick={() => onNavigate(n.tab)}
          >
            <n.icon className="w-8 h-8 text-blue-600" />
            <span className="font-medium text-gray-800">{n.label}</span>
            {n.sub && <span className="text-xs text-gray-400">{n.sub}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  tenantId: string;
  selectedEngagement: AuditEngagement | null;
  onSelectEngagement: (eng: AuditEngagement) => void;
  onNavigate: (tab: string) => void;
  onBack: () => void;
}

export default function EngagementDashboard({
  tenantId,
  selectedEngagement,
  onSelectEngagement,
  onNavigate,
  onBack,
}: Props) {
  const [showNew, setShowNew] = useState(false);

  const { data: engagements = [], isLoading } = useQuery<AuditEngagement[]>({
    queryKey: ['engagements', tenantId],
    queryFn: () => listEngagements(tenantId),
    enabled: !!tenantId,
  });

  if (selectedEngagement) {
    return (
      <EngagementDetailView
        tenantId={tenantId}
        engagement={selectedEngagement}
        onBack={onBack}
        onNavigate={onNavigate}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Engagements</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage PBC requests, workpapers, and issue registers per engagement</p>
        </div>
        <button className="btn-primary" onClick={() => setShowNew(true)}>
          <Plus className="w-4 h-4" />
          New Engagement
        </button>
      </div>

      {isLoading && <p className="text-gray-500">Loading engagements…</p>}

      {!isLoading && engagements.length === 0 && (
        <div className="card p-12 text-center text-gray-400">
          <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p>No engagements yet. Create your first one.</p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {engagements.map((eng) => (
          <EngagementCard key={eng.id} eng={eng} onClick={() => onSelectEngagement(eng)} />
        ))}
      </div>

      {showNew && <NewEngagementModal tenantId={tenantId} onClose={() => setShowNew(false)} />}
    </div>
  );
}
