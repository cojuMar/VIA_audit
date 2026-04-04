import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  X,
  ChevronDown,
  ChevronUp,
  Star,
  Plus,
  Zap,
  Activity,
  History,
  Target,
} from 'lucide-react';
import {
  fetchTreatments,
  createTreatment,
  fetchIndicators,
  createIndicator,
  recordReading,
  fetchScoreHistory,
  suggestTreatments,
  fetchAppetites,
} from '../api';
import type { Risk, RiskTreatment, RiskIndicator, IndicatorStatus } from '../types';

interface Props {
  risk: Risk;
  tenantId: string;
  onClose: () => void;
  onUpdate: () => void;
}

type Tab = 'treatments' | 'indicators' | 'history' | 'appetite';

function scoreBand(score: number) {
  if (score >= 20) return 'critical';
  if (score >= 15) return 'high';
  if (score >= 9) return 'medium';
  return 'low';
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-400">—</span>;
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
    open: 'Open', in_treatment: 'In Treatment', accepted: 'Accepted',
    closed: 'Closed', transferred: 'Transferred',
  };
  return (
    <span className={`status-badge ${map[status] ?? 'bg-gray-50 text-gray-600 ring-gray-500/20'}`}>
      {label[status] ?? status}
    </span>
  );
}

function TreatmentBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    mitigate: 'bg-blue-50 text-blue-700 ring-blue-600/20',
    accept: 'bg-gray-50 text-gray-600 ring-gray-500/20',
    transfer: 'bg-purple-50 text-purple-700 ring-purple-600/20',
    avoid: 'bg-red-50 text-red-700 ring-red-600/20',
  };
  return (
    <span className={`status-badge ${map[type] ?? 'bg-gray-50 text-gray-600 ring-gray-500/20'} capitalize`}>
      {type}
    </span>
  );
}

function IndicatorStatusDot({ status }: { status: IndicatorStatus }) {
  const colors: Record<IndicatorStatus, string> = {
    green: 'bg-green-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
    unknown: 'bg-gray-400',
  };
  return <span className={`inline-block h-3 w-3 rounded-full ${colors[status]}`} />;
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

function ScoreGrid({ likelihood, impact, label }: { likelihood: number | null; impact: number | null; label: string }) {
  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <p className="mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      {likelihood === null || impact === null ? (
        <div className="grid grid-cols-5 gap-0.5">
          {Array.from({ length: 25 }).map((_, i) => (
            <div key={i} className="h-6 w-full rounded-sm bg-gray-100" />
          ))}
          <p className="col-span-5 mt-2 text-center text-xs text-gray-400">Not assessed</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-5 gap-0.5">
            {[5, 4, 3, 2, 1].map((imp) =>
              [1, 2, 3, 4, 5].map((lik) => {
                const selected = lik === likelihood && imp === impact;
                const score = lik * imp;
                const bg = score >= 20 ? 'bg-red-500' : score >= 15 ? 'bg-orange-400' : score >= 9 ? 'bg-yellow-300' : 'bg-green-400';
                return (
                  <div
                    key={`${imp}-${lik}`}
                    className={`h-5 w-full rounded-sm ${selected ? bg + ' ring-2 ring-gray-900' : 'bg-gray-100'}`}
                  />
                );
              })
            )}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-gray-500">L{likelihood} × I{impact}</span>
            <ScoreBadge score={likelihood * impact} />
          </div>
        </>
      )}
    </div>
  );
}

export default function RiskDetail({ risk, tenantId, onClose, onUpdate }: Props) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('treatments');
  const [descExpanded, setDescExpanded] = useState(false);
  const [showAddTreatment, setShowAddTreatment] = useState(false);
  const [showAddIndicator, setShowAddIndicator] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<Array<{ title: string; description: string; treatment_type: string }> | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [readingMap, setReadingMap] = useState<Record<string, string>>({});

  // Treatment form state
  const [txForm, setTxForm] = useState({
    treatment_type: 'mitigate',
    title: '',
    description: '',
    owner: '',
    target_date: '',
    status: 'planned',
  });

  // Indicator form state
  const [indForm, setIndForm] = useState({
    indicator_name: '',
    metric_type: 'kri',
    threshold_green: '',
    threshold_amber: '',
    threshold_red: '',
    data_source: '',
  });

  const { data: treatments = [] } = useQuery({
    queryKey: ['treatments', risk.id, tenantId],
    queryFn: () => fetchTreatments(risk.id),
    enabled: activeTab === 'treatments',
  });

  const { data: indicators = [] } = useQuery({
    queryKey: ['indicators', risk.id, tenantId],
    queryFn: () => fetchIndicators(risk.id),
    enabled: activeTab === 'indicators',
  });

  const { data: history = [] } = useQuery({
    queryKey: ['risk-history', risk.id, tenantId],
    queryFn: () => fetchScoreHistory(risk.id),
    enabled: activeTab === 'history',
  });

  const { data: appetites = [] } = useQuery({
    queryKey: ['appetites', tenantId],
    queryFn: fetchAppetites,
    enabled: activeTab === 'appetite',
  });

  const addTreatmentMut = useMutation({
    mutationFn: (payload: Partial<RiskTreatment>) => createTreatment(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['treatments', risk.id] });
      setShowAddTreatment(false);
      setTxForm({ treatment_type: 'mitigate', title: '', description: '', owner: '', target_date: '', status: 'planned' });
    },
  });

  const addIndicatorMut = useMutation({
    mutationFn: (payload: Partial<RiskIndicator>) => createIndicator(risk.id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['indicators', risk.id] });
      setShowAddIndicator(false);
    },
  });

  const readingMut = useMutation({
    mutationFn: ({ id, value }: { id: string; value: number }) => recordReading(id, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['indicators', risk.id] });
    },
  });

  async function handleAiSuggest() {
    setAiLoading(true);
    try {
      const result = await suggestTreatments(risk.id);
      setAiSuggestions(result.suggestions);
    } catch {
      setAiSuggestions([]);
    } finally {
      setAiLoading(false);
    }
  }

  const reductionPct =
    risk.residual_score !== null && risk.inherent_score > 0
      ? Math.round(((risk.inherent_score - risk.residual_score) / risk.inherent_score) * 100)
      : null;

  const categoryAppetite = appetites.find((a) => a.category_id === risk.category_id);
  const exceedsAppetite =
    categoryAppetite !== null &&
    risk.residual_score !== null &&
    risk.residual_score > (categoryAppetite?.max_acceptable_score ?? Infinity);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'treatments', label: 'Treatments', icon: <Target className="h-4 w-4" /> },
    { id: 'indicators', label: 'Indicators', icon: <Activity className="h-4 w-4" /> },
    { id: 'history', label: 'History', icon: <History className="h-4 w-4" /> },
    { id: 'appetite', label: 'Appetite', icon: <Zap className="h-4 w-4" /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/40" onClick={onClose} />

      {/* Drawer */}
      <div className="flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-start justify-between border-b border-gray-200 bg-white px-6 py-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm text-gray-500">{risk.risk_id}</span>
              <StatusBadge status={risk.status} />
            </div>
            <h2 className="text-xl font-bold text-gray-900">{risk.title}</h2>
          </div>
          <button onClick={onClose} className="ml-4 rounded-full p-1 text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 px-6 py-6 space-y-6">
          {/* Score Section */}
          <div className="grid grid-cols-2 gap-4">
            <ScoreGrid likelihood={risk.inherent_likelihood} impact={risk.inherent_impact} label="Inherent Risk" />
            <ScoreGrid likelihood={risk.residual_likelihood} impact={risk.residual_impact} label="Residual Risk" />
          </div>

          {reductionPct !== null && reductionPct > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-3 py-1 text-sm font-semibold text-green-700 ring-1 ring-green-600/20">
              ↓ {reductionPct}% risk reduction
            </div>
          )}

          {/* Details Grid */}
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Category</span>
              <p className="mt-0.5 text-gray-900">{risk.category_name ?? '—'}</p>
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Owner</span>
              <p className="mt-0.5 text-gray-900">{risk.owner ?? '—'}</p>
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Department</span>
              <p className="mt-0.5 text-gray-900">{risk.department ?? '—'}</p>
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Source</span>
              <p className="mt-0.5 text-gray-900">{risk.source}</p>
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Identified</span>
              <p className="mt-0.5 text-gray-900">{risk.identified_date}</p>
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Review Date</span>
              <p className={`mt-0.5 ${risk.review_date && risk.review_date < new Date().toISOString().slice(0, 10) ? 'font-semibold text-red-600' : 'text-gray-900'}`}>
                {risk.review_date ?? '—'}
              </p>
            </div>
            {risk.framework_control_refs.length > 0 && (
              <div className="col-span-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Control References</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {risk.framework_control_refs.map((ref) => (
                    <span key={ref} className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {ref}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Description */}
          <div className="rounded-lg border border-gray-200 p-4">
            <button
              onClick={() => setDescExpanded(!descExpanded)}
              className="flex w-full items-center justify-between text-sm font-semibold text-gray-700"
            >
              Description & Assessment Notes
              {descExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {descExpanded && (
              <p className="mt-3 text-sm text-gray-600 whitespace-pre-wrap">{risk.description}</p>
            )}
          </div>

          {/* Tabs */}
          <div>
            <div className="flex border-b border-gray-200">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Treatments Tab */}
            {activeTab === 'treatments' && (
              <div className="mt-4 space-y-4">
                <div className="flex justify-between">
                  <button
                    onClick={handleAiSuggest}
                    disabled={aiLoading}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-60"
                  >
                    <Zap className="h-4 w-4" />
                    {aiLoading ? 'Generating…' : 'Get AI Suggestions'}
                  </button>
                  <button
                    onClick={() => setShowAddTreatment(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    <Plus className="h-4 w-4" />
                    Add Treatment
                  </button>
                </div>

                {/* AI Suggestions */}
                {aiSuggestions && aiSuggestions.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">AI Suggestions</p>
                    {aiSuggestions.map((s, i) => (
                      <div key={i} className="rounded-lg border border-indigo-100 bg-indigo-50 p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <TreatmentBadge type={s.treatment_type} />
                          <span className="text-sm font-medium text-gray-900">{s.title}</span>
                        </div>
                        <p className="text-xs text-gray-600">{s.description}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Add Treatment Form */}
                {showAddTreatment && (
                  <div className="rounded-lg border border-gray-200 p-4 space-y-3">
                    <p className="text-sm font-semibold text-gray-700">New Treatment</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                        <select
                          value={txForm.treatment_type}
                          onChange={(e) => setTxForm({ ...txForm, treatment_type: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        >
                          {['mitigate', 'accept', 'transfer', 'avoid'].map((t) => (
                            <option key={t} value={t} className="capitalize">{t}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                        <select
                          value={txForm.status}
                          onChange={(e) => setTxForm({ ...txForm, status: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        >
                          {['planned', 'in_progress', 'completed', 'cancelled'].map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
                      <input
                        value={txForm.title}
                        onChange={(e) => setTxForm({ ...txForm, title: e.target.value })}
                        className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        placeholder="Treatment title"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                      <textarea
                        value={txForm.description}
                        onChange={(e) => setTxForm({ ...txForm, description: e.target.value })}
                        rows={2}
                        className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Owner</label>
                        <input
                          value={txForm.owner}
                          onChange={(e) => setTxForm({ ...txForm, owner: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Target Date</label>
                        <input
                          type="date"
                          value={txForm.target_date}
                          onChange={(e) => setTxForm({ ...txForm, target_date: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setShowAddTreatment(false)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">Cancel</button>
                      <button
                        onClick={() => addTreatmentMut.mutate({ ...txForm, risk_id: risk.id, treatment_type: txForm.treatment_type as RiskTreatment['treatment_type'] })}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700"
                      >
                        Save
                      </button>
                    </div>
                  </div>
                )}

                {/* Treatment List */}
                {treatments.length === 0 && !showAddTreatment && (
                  <p className="text-sm text-gray-400 text-center py-6">No treatments yet.</p>
                )}
                <div className="space-y-2">
                  {treatments.map((t) => {
                    const today = new Date().toISOString().slice(0, 10);
                    const overdue = t.target_date && t.target_date < today && t.status !== 'completed' && t.status !== 'cancelled';
                    return (
                      <div key={t.id} className="rounded-lg border border-gray-200 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <TreatmentBadge type={t.treatment_type} />
                            <span className="text-sm font-medium text-gray-900">{t.title}</span>
                          </div>
                          <StarRating rating={t.effectiveness_rating} />
                        </div>
                        <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-500">
                          {t.owner && <span>Owner: {t.owner}</span>}
                          <span className="capitalize">Status: {t.status}</span>
                          {t.target_date && (
                            <span className={overdue ? 'font-semibold text-red-600' : ''}>
                              Due: {t.target_date}
                            </span>
                          )}
                        </div>
                        {t.description && <p className="mt-1.5 text-xs text-gray-500">{t.description}</p>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Indicators Tab */}
            {activeTab === 'indicators' && (
              <div className="mt-4 space-y-4">
                <div className="flex justify-end">
                  <button
                    onClick={() => setShowAddIndicator(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    <Plus className="h-4 w-4" />
                    Add Indicator
                  </button>
                </div>

                {showAddIndicator && (
                  <div className="rounded-lg border border-gray-200 p-4 space-y-3">
                    <p className="text-sm font-semibold text-gray-700">New Indicator</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
                        <input
                          value={indForm.indicator_name}
                          onChange={(e) => setIndForm({ ...indForm, indicator_name: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                        <select
                          value={indForm.metric_type}
                          onChange={(e) => setIndForm({ ...indForm, metric_type: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        >
                          {['kri', 'kpi', 'kci'].map((t) => (
                            <option key={t} value={t}>{t.toUpperCase()}</option>
                          ))}
                        </select>
                      </div>
                      {['threshold_green', 'threshold_amber', 'threshold_red'].map((field) => (
                        <div key={field}>
                          <label className="block text-xs font-medium text-gray-600 mb-1 capitalize">
                            {field.replace('threshold_', '')} threshold
                          </label>
                          <input
                            type="number"
                            value={(indForm as Record<string, string>)[field]}
                            onChange={(e) => setIndForm({ ...indForm, [field]: e.target.value })}
                            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                          />
                        </div>
                      ))}
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Data Source</label>
                        <input
                          value={indForm.data_source}
                          onChange={(e) => setIndForm({ ...indForm, data_source: e.target.value })}
                          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setShowAddIndicator(false)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">Cancel</button>
                      <button
                        onClick={() => addIndicatorMut.mutate({
                          ...indForm,
                          metric_type: indForm.metric_type as RiskIndicator['metric_type'],
                          threshold_green: indForm.threshold_green ? Number(indForm.threshold_green) : null,
                          threshold_amber: indForm.threshold_amber ? Number(indForm.threshold_amber) : null,
                          threshold_red: indForm.threshold_red ? Number(indForm.threshold_red) : null,
                        })}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white"
                      >
                        Save
                      </button>
                    </div>
                  </div>
                )}

                {indicators.length === 0 && !showAddIndicator && (
                  <p className="text-sm text-gray-400 text-center py-6">No indicators configured.</p>
                )}
                <div className="space-y-2">
                  {indicators.map((ind) => (
                    <div key={ind.id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <IndicatorStatusDot status={ind.current_status} />
                          <span className="text-sm font-medium text-gray-900">{ind.indicator_name}</span>
                          <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-600 uppercase">
                            {ind.metric_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            placeholder="value"
                            value={readingMap[ind.id] ?? ''}
                            onChange={(e) => setReadingMap((m) => ({ ...m, [ind.id]: e.target.value }))}
                            className="w-20 rounded border border-gray-300 px-2 py-1 text-xs"
                          />
                          <button
                            onClick={() => {
                              const val = Number(readingMap[ind.id]);
                              if (!isNaN(val)) readingMut.mutate({ id: ind.id, value: val });
                            }}
                            className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
                          >
                            Record
                          </button>
                        </div>
                      </div>
                      <div className="mt-2 flex gap-4 text-xs text-gray-500">
                        {ind.current_value !== null && <span>Current: <strong>{ind.current_value}</strong></span>}
                        {ind.threshold_green !== null && <span className="text-green-600">Green: ≤{ind.threshold_green}</span>}
                        {ind.threshold_amber !== null && <span className="text-amber-600">Amber: ≤{ind.threshold_amber}</span>}
                        {ind.threshold_red !== null && <span className="text-red-600">Red: &gt;{ind.threshold_red}</span>}
                        {ind.data_source && <span>Source: {ind.data_source}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* History Tab */}
            {activeTab === 'history' && (
              <div className="mt-4">
                {history.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">No assessment history.</p>
                ) : (
                  <div className="relative border-l-2 border-gray-200 ml-4 space-y-6 py-2">
                    {history.map((h, i) => (
                      <div key={h.id} className="relative pl-6">
                        <div className="absolute -left-2 top-1 h-3.5 w-3.5 rounded-full border-2 border-white bg-indigo-500" />
                        <div className="rounded-lg border border-gray-200 p-3">
                          <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
                            <span>{h.assessed_at.slice(0, 10)}</span>
                            {h.assessed_by && <span>{h.assessed_by}</span>}
                          </div>
                          <div className="flex items-center gap-3 text-sm">
                            <div>
                              Inherent:
                              <ScoreBadge score={h.inherent_score} />
                            </div>
                            {h.residual_score !== null && (
                              <div>
                                Residual:
                                <ScoreBadge score={h.residual_score} />
                              </div>
                            )}
                          </div>
                          {h.notes && <p className="mt-1 text-xs text-gray-500">{h.notes}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Appetite Tab */}
            {activeTab === 'appetite' && (
              <div className="mt-4 space-y-4">
                {categoryAppetite ? (
                  <>
                    <div className="rounded-lg border border-gray-200 p-4">
                      <p className="text-sm font-semibold text-gray-700 mb-3">
                        Appetite: {categoryAppetite.category_name}
                      </p>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Appetite Level</span>
                          <span className="font-medium capitalize">{categoryAppetite.appetite_level.replace('_', ' ')}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Max Acceptable Score</span>
                          <span className="font-medium">{categoryAppetite.max_acceptable_score}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Residual Score</span>
                          <ScoreBadge score={risk.residual_score} />
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Status</span>
                          <span className={`font-semibold ${exceedsAppetite ? 'text-red-600' : 'text-green-600'}`}>
                            {exceedsAppetite ? 'Exceeds Appetite' : 'Within Appetite'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Visual Gauge */}
                    <div className="rounded-lg border border-gray-200 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Risk Score vs Appetite</p>
                      <div className="relative h-4 rounded-full bg-gray-100 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-green-400 via-yellow-400 to-red-500"
                          style={{ width: '100%', opacity: 0.3 }}
                        />
                        {/* Appetite threshold marker */}
                        <div
                          className="absolute top-0 h-full w-0.5 bg-gray-800"
                          style={{ left: `${(categoryAppetite.max_acceptable_score / 25) * 100}%` }}
                        />
                        {/* Current residual score dot */}
                        {risk.residual_score !== null && (
                          <div
                            className={`absolute top-0.5 h-3 w-3 rounded-full ${exceedsAppetite ? 'bg-red-500' : 'bg-green-500'} border-2 border-white`}
                            style={{ left: `calc(${(risk.residual_score / 25) * 100}% - 6px)` }}
                          />
                        )}
                      </div>
                      <div className="mt-1 flex justify-between text-xs text-gray-400">
                        <span>0</span>
                        <span>Threshold: {categoryAppetite.max_acceptable_score}</span>
                        <span>25</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-gray-400 text-center py-6">No appetite defined for this category.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
