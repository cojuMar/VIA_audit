import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts';
import { Target, Sparkles, X, CheckCircle, AlertTriangle, TrendingUp, Beaker } from 'lucide-react';
import {
  fetchTargetProgress, fetchMetricDefinitions, upsertTarget, aiSuggestTargets, fetchTrendData,
} from '../api';
import type { TargetProgress, ESGMetricDefinition, TrendDataPoint } from '../types';

interface Props { tenantId: string }

const TARGET_YEARS = [2025, 2026, 2027, 2028, 2030];
const TARGET_TYPES = ['absolute_reduction', 'intensity_reduction', 'percentage_increase', 'net_zero', 'custom'];
const FRAMEWORKS = ['GRI', 'TCFD', 'SBTI', 'CDP', 'UN SDGs', 'SASB'];

function getProgressColor(pct?: number, onTrack?: boolean): string {
  if (onTrack) return 'bg-green-500';
  if (pct === undefined) return 'bg-gray-300';
  if (pct >= 80) return 'bg-green-500';
  if (pct >= 50) return 'bg-orange-400';
  return 'bg-red-500';
}

function getProgressTextColor(pct?: number, onTrack?: boolean): string {
  if (onTrack) return 'text-green-700';
  if (pct === undefined) return 'text-gray-500';
  if (pct >= 80) return 'text-green-700';
  if (pct >= 50) return 'text-orange-700';
  return 'text-red-700';
}

interface TrendModalProps {
  metricId: string;
  metricName: string;
  targetValue: number;
  onClose: () => void;
}
function TrendModal({ metricId, metricName, targetValue, onClose }: TrendModalProps) {
  const { data: trendRaw, isLoading } = useQuery<TrendDataPoint[]>({
    queryKey: ['trend', metricId],
    queryFn: () => fetchTrendData(metricId, 12),
  });
  const trendData = (trendRaw ?? []).map((d) => ({ ...d, target: targetValue }));

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">{metricName} — Trend</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        {isLoading ? (
          <div className="h-56 flex items-center justify-center text-gray-400">Loading…</div>
        ) : trendData.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-gray-400">No trend data available.</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="reporting_period" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} dot name="Actual" />
              <ReferenceLine y={targetValue} stroke="#ef4444" strokeDasharray="6 3" label={{ value: 'Target', position: 'right', fontSize: 11, fill: '#ef4444' }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

interface SetTargetDrawerProps {
  metrics: ESGMetricDefinition[];
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
  prefill?: Partial<AISuggestion>;
}

interface AISuggestion {
  metric_id: string;
  metric_name: string;
  target_year: number;
  baseline_year: number;
  baseline_value: number;
  target_value: number;
  target_type: string;
  science_based: boolean;
  framework_alignment: string[];
  rationale: string;
}

function SetTargetDrawer({ metrics, onClose, onSubmit, submitting, prefill }: SetTargetDrawerProps) {
  const [metricId, setMetricId] = useState(prefill?.metric_id ?? '');
  const [targetYear, setTargetYear] = useState(prefill?.target_year ?? 2030);
  const [baselineYear, setBaselineYear] = useState<number | ''>(prefill?.baseline_year ?? 2023);
  const [baselineValue, setBaselineValue] = useState<number | ''>(prefill?.baseline_value ?? '');
  const [targetValue, setTargetValue] = useState<number | ''>(prefill?.target_value ?? '');
  const [targetType, setTargetType] = useState(prefill?.target_type ?? 'absolute_reduction');
  const [scienceBased, setScienceBased] = useState(prefill?.science_based ?? false);
  const [frameworkAlignment, setFrameworkAlignment] = useState<string[]>(prefill?.framework_alignment ?? []);
  const [description, setDescription] = useState('');

  const toggleFramework = (fw: string) => {
    setFrameworkAlignment((prev) => prev.includes(fw) ? prev.filter((f) => f !== fw) : [...prev, fw]);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      metric_definition_id: metricId,
      target_year: targetYear,
      baseline_year: baselineYear || undefined,
      baseline_value: baselineValue !== '' ? baselineValue : undefined,
      target_value: targetValue,
      target_type: targetType,
      science_based: scienceBased,
      framework_alignment: frameworkAlignment,
      description: description || undefined,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-end justify-end z-50">
      <div className="bg-white h-full w-full max-w-md shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-indigo-600" />
            <h3 className="text-lg font-semibold">Set ESG Target</h3>
          </div>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Metric</label>
            <select
              value={metricId}
              onChange={(e) => setMetricId(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            >
              <option value="">Select metric…</option>
              {metrics.map((m) => (
                <option key={m.id} value={m.id}>[{m.category[0].toUpperCase()}] {m.display_name} ({m.unit})</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Target Year</label>
              <select
                value={targetYear}
                onChange={(e) => setTargetYear(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {TARGET_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Baseline Year</label>
              <input
                type="number"
                value={baselineYear}
                onChange={(e) => setBaselineYear(e.target.value ? Number(e.target.value) : '')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Baseline Value</label>
              <input
                type="number"
                step="any"
                value={baselineValue}
                onChange={(e) => setBaselineValue(e.target.value ? Number(e.target.value) : '')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Target Value</label>
              <input
                type="number"
                step="any"
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value ? Number(e.target.value) : '')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Target Type</label>
            <select
              value={targetType}
              onChange={(e) => setTargetType(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {TARGET_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Framework Alignment</label>
            <div className="flex flex-wrap gap-2">
              {FRAMEWORKS.map((fw) => (
                <button
                  key={fw} type="button"
                  onClick={() => toggleFramework(fw)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    frameworkAlignment.includes(fw)
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'border-gray-300 text-gray-600 hover:border-indigo-400'
                  }`}
                >
                  {fw}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setScienceBased(!scienceBased)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${scienceBased ? 'bg-green-500' : 'bg-gray-300'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${scienceBased ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
            <div className="flex items-center gap-1.5">
              <Beaker className="w-4 h-4 text-green-600" />
              <span className="text-sm text-gray-700">Science-based target (SBTi)</span>
            </div>
          </div>

          <div className="pt-4">
            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
            >
              {submitting ? 'Saving…' : 'Save Target'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ESGTargets({ tenantId: _tenantId }: Props) {
  const queryClient = useQueryClient();
  const [selectedYear, setSelectedYear] = useState(2030);
  const [showDrawer, setShowDrawer] = useState(false);
  const [drawerPrefill, setDrawerPrefill] = useState<Partial<AISuggestion> | undefined>();
  const [trendMetric, setTrendMetric] = useState<{ id: string; name: string; targetValue: number } | null>(null);
  const [aiSuggestions, setAISuggestions] = useState<AISuggestion[] | null>(null);
  const [aiSuggestLoading, setAISuggestLoading] = useState(false);
  const [showAIModal, setShowAIModal] = useState(false);

  const { data: progressRaw, isLoading } = useQuery<TargetProgress[]>({
    queryKey: ['target-progress', selectedYear],
    queryFn: () => fetchTargetProgress(selectedYear),
    retry: 1,
  });
  const progress = progressRaw ?? [];

  const { data: metricsRaw } = useQuery<ESGMetricDefinition[]>({
    queryKey: ['metric-definitions'],
    queryFn: () => fetchMetricDefinitions(),
  });
  const metrics = metricsRaw ?? [];

  const targetMutation = useMutation({
    mutationFn: upsertTarget,
    onSuccess: () => {
      setShowDrawer(false);
      setDrawerPrefill(undefined);
      void queryClient.invalidateQueries({ queryKey: ['target-progress'] });
    },
  });

  const handleAISuggest = async () => {
    setAISuggestLoading(true);
    try {
      const res = await aiSuggestTargets(String(selectedYear));
      setAISuggestions(res.suggestions ?? res ?? []);
      setShowAIModal(true);
    } catch {
      setAISuggestions([]);
      setShowAIModal(true);
    } finally {
      setAISuggestLoading(false);
    }
  };

  const onTrack = progress.filter((p) => p.on_track).length;
  const atRisk = progress.filter((p) => !p.on_track && (p.progress_pct ?? 0) < 80).length;
  const achieved = progress.filter((p) => p.status === 'achieved' || (p.progress_pct ?? 0) >= 100).length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Targets &amp; Progress</h2>
          <p className="text-sm text-gray-500 mt-0.5">Track ESG targets and measure progress</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleAISuggest}
            disabled={aiSuggestLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {aiSuggestLoading ? 'Analyzing…' : 'AI Suggest Targets'}
          </button>
          <button
            onClick={() => { setDrawerPrefill(undefined); setShowDrawer(true); }}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            + Set Target
          </button>
        </div>
      </div>

      {/* Year Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {TARGET_YEARS.map((y) => (
          <button
            key={y}
            onClick={() => setSelectedYear(y)}
            className={`px-4 py-1.5 text-sm rounded-md transition-colors ${selectedYear === y ? 'bg-white shadow font-semibold text-indigo-700' : 'text-gray-600 hover:text-gray-900'}`}
          >
            {y}
          </button>
        ))}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="metric-card border-green-200 bg-green-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg"><CheckCircle className="w-5 h-5 text-green-600" /></div>
            <div>
              <p className="text-2xl font-bold text-green-700">{onTrack}</p>
              <p className="text-sm text-green-600">On Track</p>
            </div>
          </div>
        </div>
        <div className="metric-card border-orange-200 bg-orange-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-lg"><AlertTriangle className="w-5 h-5 text-orange-600" /></div>
            <div>
              <p className="text-2xl font-bold text-orange-700">{atRisk}</p>
              <p className="text-sm text-orange-600">At Risk</p>
            </div>
          </div>
        </div>
        <div className="metric-card border-blue-200 bg-blue-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg"><TrendingUp className="w-5 h-5 text-blue-600" /></div>
            <div>
              <p className="text-2xl font-bold text-blue-700">{achieved}</p>
              <p className="text-sm text-blue-600">Achieved</p>
            </div>
          </div>
        </div>
      </div>

      {/* Target Progress List */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-400">Loading targets…</div>
      ) : progress.length === 0 ? (
        <div className="metric-card text-center py-12 text-gray-400">No targets set for {selectedYear}.</div>
      ) : (
        <div className="space-y-3">
          {progress.map((t) => {
            const category = t.metric?.category ?? 'environmental';
            const badgeClass = category === 'environmental' ? 'esg-e' : category === 'social' ? 'esg-s' : 'esg-g';
            const pct = Math.min(100, t.progress_pct ?? 0);
            const progressColor = getProgressColor(pct, t.on_track);
            const progressTextColor = getProgressTextColor(pct, t.on_track);
            const statusLabel = t.status === 'achieved' || pct >= 100
              ? 'Achieved'
              : t.on_track ? 'On Track' : 'At Risk';
            const statusColor = statusLabel === 'Achieved' ? 'bg-blue-100 text-blue-700'
              : t.on_track ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700';

            return (
              <div key={t.id} className="metric-card hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${badgeClass}`}>
                      {category[0].toUpperCase()}
                    </span>
                    <button
                      className="text-sm font-semibold text-gray-800 hover:text-indigo-700 truncate"
                      onClick={() => setTrendMetric({
                        id: t.metric_definition_id,
                        name: t.metric?.display_name ?? t.metric_definition_id,
                        targetValue: t.target_value,
                      })}
                    >
                      {t.metric?.display_name ?? t.metric_definition_id}
                    </button>
                    {t.science_based && (
                      <span className="flex items-center gap-1 text-xs bg-green-50 text-green-700 border border-green-200 px-1.5 py-0.5 rounded-full">
                        <Beaker className="w-3 h-3" />SBTi
                      </span>
                    )}
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor}`}>{statusLabel}</span>
                </div>

                {/* Baseline → Current → Target */}
                <div className="flex items-center gap-4 mb-2 text-xs text-gray-500">
                  <span>Baseline: <strong className="text-gray-700">{t.baseline_value ?? '—'}</strong></span>
                  <span>Current: <strong className="text-gray-700">{t.latest_value ?? '—'}</strong></span>
                  <span>Target: <strong className="text-gray-700">{t.target_value}</strong> {t.metric?.unit}</span>
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${progressColor}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className={`text-xs font-semibold w-10 text-right ${progressTextColor}`}>
                    {Math.round(pct)}%
                  </span>
                </div>

                {t.framework_alignment.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {t.framework_alignment.map((fw) => (
                      <span key={fw} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{fw}</span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Set Target Drawer */}
      {showDrawer && (
        <SetTargetDrawer
          metrics={metrics}
          onClose={() => { setShowDrawer(false); setDrawerPrefill(undefined); }}
          onSubmit={(data) => targetMutation.mutate(data)}
          submitting={targetMutation.isPending}
          prefill={drawerPrefill}
        />
      )}

      {/* Trend Modal */}
      {trendMetric && (
        <TrendModal
          metricId={trendMetric.id}
          metricName={trendMetric.name}
          targetValue={trendMetric.targetValue}
          onClose={() => setTrendMetric(null)}
        />
      )}

      {/* AI Suggestions Modal */}
      {showAIModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-600" />
                <h3 className="text-lg font-semibold">AI Target Suggestions</h3>
              </div>
              <button onClick={() => setShowAIModal(false)}><X className="w-5 h-5 text-gray-500" /></button>
            </div>
            {!aiSuggestions || aiSuggestions.length === 0 ? (
              <p className="text-gray-400 text-sm">No suggestions available.</p>
            ) : (
              <div className="space-y-3">
                {aiSuggestions.map((s, i) => (
                  <div key={i} className="border border-purple-100 bg-purple-50 rounded-lg p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-semibold text-gray-800">{s.metric_name}</p>
                        <p className="text-sm text-gray-600 mt-1">
                          Target {s.target_value} by {s.target_year}
                          {s.science_based && <span className="ml-2 text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">SBTi</span>}
                        </p>
                        {s.rationale && <p className="text-xs text-gray-500 mt-1.5">{s.rationale}</p>}
                      </div>
                      <button
                        onClick={() => {
                          setDrawerPrefill(s);
                          setShowAIModal(false);
                          setShowDrawer(true);
                        }}
                        className="ml-4 px-3 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 whitespace-nowrap"
                      >
                        Accept
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
