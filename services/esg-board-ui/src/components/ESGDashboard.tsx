import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import { Leaf, Users, Shield, Sparkles, Copy, Check, X, ChevronDown } from 'lucide-react';
import {
  fetchScorecard, fetchMetricDefinitions, submitDisclosure, aiESGNarrative,
} from '../api';
import type { ESGScorecard, ESGMetricDefinition, ScorecardMetric } from '../types';

interface Props { tenantId: string }

function generatePeriods(): string[] {
  const periods: string[] = [];
  const now = new Date();
  for (let y = now.getFullYear(); y >= now.getFullYear() - 2; y--) {
    periods.push(String(y));
    for (let q = 4; q >= 1; q--) {
      periods.push(`${y}-Q${q}`);
    }
  }
  return periods;
}

interface CircleProgressProps { pct: number; color: string; size?: number }
function CircleProgress({ pct, color, size = 64 }: CircleProgressProps) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <svg width={size} height={size}>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="#e5e7eb" strokeWidth={6} fill="none" />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        stroke={color} strokeWidth={6} fill="none"
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x={size / 2} y={size / 2 + 4} textAnchor="middle" fontSize={11} fontWeight="bold" fill={color}>
        {Math.round(pct)}%
      </text>
    </svg>
  );
}

interface DisclosureModalProps {
  metrics: ESGMetricDefinition[];
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
  reportingPeriod: string;
}
function DisclosureModal({ metrics, onClose, onSubmit, submitting, reportingPeriod }: DisclosureModalProps) {
  const [metricId, setMetricId] = useState('');
  const [value, setValue] = useState('');
  const [period, setPeriod] = useState(reportingPeriod);
  const [notes, setNotes] = useState('');
  const [dataSource, setDataSource] = useState('');
  const [assurance, setAssurance] = useState('none');

  const selectedMetric = metrics.find((m) => m.id === metricId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!metricId) return;
    const payload: Record<string, unknown> = {
      metric_definition_id: metricId,
      reporting_period: period,
      period_type: period.includes('Q') ? 'quarterly' : 'annual',
      notes: notes || undefined,
      data_source: dataSource || undefined,
      assurance_level: assurance !== 'none' ? assurance : undefined,
      currency_code: 'USD',
    };
    if (selectedMetric?.data_type === 'numeric') payload.numeric_value = parseFloat(value);
    else if (selectedMetric?.data_type === 'boolean') payload.boolean_value = value === 'true';
    else if (selectedMetric?.data_type === 'currency') payload.currency_value = parseFloat(value);
    else payload.text_value = value;
    onSubmit(payload);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Submit ESG Disclosure</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Metric</label>
            <select
              value={metricId}
              onChange={(e) => setMetricId(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            >
              <option value="">Select a metric…</option>
              {metrics.map((m) => (
                <option key={m.id} value={m.id}>[{m.category.toUpperCase()[0]}] {m.display_name} ({m.unit})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Value{selectedMetric ? ` (${selectedMetric.unit})` : ''}
            </label>
            {selectedMetric?.data_type === 'boolean' ? (
              <select
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              >
                <option value="">Select…</option>
                <option value="true">Yes / True</option>
                <option value="false">No / False</option>
              </select>
            ) : selectedMetric?.data_type === 'text' ? (
              <textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            ) : (
              <input
                type="number"
                step="any"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reporting Period</label>
              <input
                type="text"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                placeholder="e.g. 2025 or 2025-Q4"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Assurance Level</label>
              <select
                value={assurance}
                onChange={(e) => setAssurance(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="none">None</option>
                <option value="limited">Limited</option>
                <option value="reasonable">Reasonable</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data Source</label>
            <input
              type="text"
              value={dataSource}
              onChange={(e) => setDataSource(e.target.value)}
              placeholder="e.g. Utility bills, HR system"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting ? 'Submitting…' : 'Submit Disclosure'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface MetricRowProps {
  metric: ScorecardMetric;
  category: 'environmental' | 'social' | 'governance';
  onSubmit: (m: ScorecardMetric) => void;
}
function MetricRow({ metric, category, onSubmit }: MetricRowProps) {
  const badgeClass = category === 'environmental' ? 'esg-e' : category === 'social' ? 'esg-s' : 'esg-g';
  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="py-2 px-3">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${badgeClass}`}>
            {category[0].toUpperCase()}
          </span>
          <span className="text-sm font-medium text-gray-800">{metric.display_name}</span>
          {metric.is_required && <span className="text-xs text-red-500">*</span>}
        </div>
      </td>
      <td className="py-2 px-3 text-sm text-gray-500">{metric.unit}</td>
      <td className="py-2 px-3 text-sm">
        {metric.has_disclosure && metric.latest_value !== undefined ? (
          <span className="font-medium text-gray-800">{String(metric.latest_value)}</span>
        ) : (
          <span className="text-gray-400 italic">Not disclosed</span>
        )}
      </td>
      <td className="py-2 px-3">
        {metric.assurance_level ? (
          <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{metric.assurance_level}</span>
        ) : null}
      </td>
      <td className="py-2 px-3">
        <button
          onClick={() => onSubmit(metric)}
          className="text-xs px-2 py-1 bg-indigo-50 text-indigo-700 rounded hover:bg-indigo-100 transition-colors"
        >
          Submit
        </button>
      </td>
    </tr>
  );
}

export default function ESGDashboard({ tenantId: _tenantId }: Props) {
  const periods = generatePeriods();
  const [selectedPeriod, setSelectedPeriod] = useState(periods[0]);
  const [showModal, setShowModal] = useState(false);
  const [selectedMetricForSubmit, setSelectedMetricForSubmit] = useState<ScorecardMetric | null>(null);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrativeOpen, setNarrativeOpen] = useState(false);
  const [narrativeCopied, setNarrativeCopied] = useState(false);
  const [narrativeLoading, setNarrativeLoading] = useState(false);

  const { data: scorecard, isLoading: scorecardLoading, refetch: refetchScorecard } = useQuery<ESGScorecard>({
    queryKey: ['scorecard', selectedPeriod],
    queryFn: () => fetchScorecard(selectedPeriod),
    retry: 1,
  });

  const { data: metricsRaw } = useQuery<ESGMetricDefinition[]>({
    queryKey: ['metric-definitions'],
    queryFn: () => fetchMetricDefinitions(),
  });
  const metrics = metricsRaw ?? [];

  const disclosureMutation = useMutation({
    mutationFn: submitDisclosure,
    onSuccess: () => {
      setShowModal(false);
      setSelectedMetricForSubmit(null);
      void refetchScorecard();
    },
  });

  const handleAINarrative = async () => {
    setNarrativeLoading(true);
    try {
      const res = await aiESGNarrative(selectedPeriod);
      setNarrative(res.narrative ?? res.text ?? JSON.stringify(res));
      setNarrativeOpen(true);
    } catch {
      setNarrative('Failed to generate narrative. Please try again.');
      setNarrativeOpen(true);
    } finally {
      setNarrativeLoading(false);
    }
  };

  const copyNarrative = () => {
    if (narrative) {
      void navigator.clipboard.writeText(narrative);
      setNarrativeCopied(true);
      setTimeout(() => setNarrativeCopied(false), 2000);
    }
  };

  const handleOpenModal = (metric?: ScorecardMetric) => {
    setSelectedMetricForSubmit(metric ?? null);
    setShowModal(true);
  };

  const radarData = scorecard ? [
    { dimension: 'Environmental', coverage: Math.round(scorecard.environmental.coverage_pct) },
    { dimension: 'Social', coverage: Math.round(scorecard.social.coverage_pct) },
    { dimension: 'Governance', coverage: Math.round(scorecard.governance.coverage_pct) },
  ] : [];

  const allScorecardMetrics: { metric: ScorecardMetric; category: 'environmental' | 'social' | 'governance' }[] = scorecard ? [
    ...scorecard.environmental.metrics.map((m) => ({ metric: m, category: 'environmental' as const })),
    ...scorecard.social.metrics.map((m) => ({ metric: m, category: 'social' as const })),
    ...scorecard.governance.metrics.map((m) => ({ metric: m, category: 'governance' as const })),
  ] : [];

  const requiredMetrics = allScorecardMetrics.filter((x) => x.metric.is_required).length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">ESG Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">Track environmental, social, and governance disclosures</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Period</label>
            <div className="relative">
              <select
                value={selectedPeriod}
                onChange={(e) => setSelectedPeriod(e.target.value)}
                className="appearance-none border border-gray-300 rounded-lg pl-3 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {periods.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
          <button
            onClick={() => handleOpenModal()}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            + Submit Disclosure
          </button>
          <button
            onClick={handleAINarrative}
            disabled={narrativeLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {narrativeLoading ? 'Generating…' : 'AI Narrative'}
          </button>
        </div>
      </div>

      {/* AI Narrative Panel */}
      {narrativeOpen && narrative && (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-600" />
              <span className="text-sm font-semibold text-purple-800">AI-Generated ESG Narrative — {selectedPeriod}</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={copyNarrative} className="p-1 hover:bg-purple-100 rounded">
                {narrativeCopied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4 text-purple-600" />}
              </button>
              <button onClick={() => setNarrativeOpen(false)} className="p-1 hover:bg-purple-100 rounded">
                <X className="w-4 h-4 text-purple-600" />
              </button>
            </div>
          </div>
          <p className="text-sm text-purple-900 whitespace-pre-wrap">{narrative}</p>
        </div>
      )}

      {scorecardLoading ? (
        <div className="text-center py-12 text-gray-400">Loading scorecard…</div>
      ) : (
        <>
          {/* ESG Score Cards */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { key: 'environmental' as const, label: 'Environmental', Icon: Leaf, color: '#16a34a', bgColor: 'bg-green-50', border: 'border-green-200' },
              { key: 'social' as const, label: 'Social', Icon: Users, color: '#2563eb', bgColor: 'bg-blue-50', border: 'border-blue-200' },
              { key: 'governance' as const, label: 'Governance', Icon: Shield, color: '#7c3aed', bgColor: 'bg-purple-50', border: 'border-purple-200' },
            ].map(({ key, label, Icon, color, bgColor, border }) => {
              const cat = scorecard?.[key];
              const disclosed = cat?.metrics.filter((m) => m.has_disclosure).length ?? 0;
              const total = cat?.metrics.length ?? 0;
              const reqCount = cat?.metrics.filter((m) => m.is_required).length ?? 0;
              return (
                <div key={key} className={`metric-card ${bgColor} ${border}`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Icon className="w-5 h-5" style={{ color }} />
                        <span className="font-semibold text-gray-800">{label}</span>
                      </div>
                      <p className="text-sm text-gray-600">{disclosed} / {total} metrics disclosed</p>
                      <p className="text-xs text-gray-500 mt-1">{reqCount} required metrics</p>
                    </div>
                    <CircleProgress pct={cat?.coverage_pct ?? 0} color={color} size={72} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Overall Coverage */}
          <div className="metric-card">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-gray-700">Overall Coverage</span>
              <span className="text-sm font-bold text-gray-900">
                {scorecard?.disclosed_metrics ?? 0} / {scorecard?.total_metrics ?? 0} metrics ({Math.round(scorecard?.overall_coverage_pct ?? 0)}%)
              </span>
            </div>
            <div
              role="progressbar"
              aria-label="Overall ESG disclosure coverage"
              aria-valuenow={Math.round(scorecard?.overall_coverage_pct ?? 0)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-3 bg-gray-100 rounded-full overflow-hidden"
            >
              <div
                className="h-full bg-indigo-600 rounded-full transition-all"
                style={{ width: `${scorecard?.overall_coverage_pct ?? 0}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>0%</span>
              <span>Required: {requiredMetrics} metrics</span>
              <span>100%</span>
            </div>
          </div>

          {/* Radar Chart + Metrics Table */}
          <div className="grid grid-cols-5 gap-4">
            <div className="col-span-2 metric-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Coverage by Dimension</h3>
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 9 }} />
                  <Radar name="Coverage" dataKey="coverage" stroke="#6366f1" fill="#6366f1" fillOpacity={0.35} />
                  <Tooltip formatter={(v) => [`${v}%`, 'Coverage']} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="col-span-3 metric-card overflow-auto">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Metric Disclosures</h3>
              {allScorecardMetrics.length === 0 ? (
                <p className="text-sm text-gray-400 italic">No scorecard data for this period.</p>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
                      <th className="pb-2 px-3">Metric</th>
                      <th className="pb-2 px-3">Unit</th>
                      <th className="pb-2 px-3">Latest Value</th>
                      <th className="pb-2 px-3">Assurance</th>
                      <th className="pb-2 px-3">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allScorecardMetrics.map(({ metric, category }) => (
                      <MetricRow
                        key={metric.metric_key}
                        metric={metric}
                        category={category}
                        onSubmit={() => handleOpenModal(metric)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* Submit Disclosure Modal */}
      {showModal && (
        <DisclosureModal
          metrics={metrics}
          reportingPeriod={selectedPeriod}
          onClose={() => { setShowModal(false); setSelectedMetricForSubmit(null); }}
          onSubmit={(data) => disclosureMutation.mutate(data)}
          submitting={disclosureMutation.isPending}
        />
      )}

      {/* Pre-select metric in modal */}
      {selectedMetricForSubmit && showModal && (
        <style>{`/* metric pre-selected via state */`}</style>
      )}
    </div>
  );
}
