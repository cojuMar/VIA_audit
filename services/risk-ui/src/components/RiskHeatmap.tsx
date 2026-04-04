import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchHeatmap } from '../api';
import type { HeatmapPoint } from '../types';

interface Props {
  tenantId: string;
}

type ViewMode = 'inherent' | 'residual' | 'both';

const LIKELIHOOD_LABELS = ['Rare', 'Unlikely', 'Possible', 'Likely', 'Almost\nCertain'];
const IMPACT_LABELS = ['Catastrophic', 'Major', 'Moderate', 'Minor', 'Negligible'];

const CATEGORY_COLORS = [
  '#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
];

function cellScore(likelihood: number, impact: number): number {
  return likelihood * impact;
}

function cellBg(score: number): string {
  if (score >= 20) return 'bg-red-600';
  if (score >= 15) return 'bg-orange-500';
  if (score >= 9) return 'bg-yellow-400';
  return 'bg-green-500';
}

function cellTextColor(score: number): string {
  if (score >= 9) return 'text-white';
  return 'text-gray-800';
}

interface TooltipState {
  x: number;
  y: number;
  risks: HeatmapPoint[];
  mode: 'inherent' | 'residual';
}

export default function RiskHeatmap({ tenantId }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>('both');
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const { data: points = [], isLoading } = useQuery({
    queryKey: ['heatmap', tenantId],
    queryFn: fetchHeatmap,
  });

  // Build unique category list for color legend
  const categories = Array.from(new Set(points.map((p) => p.category)));
  const categoryColor = (cat: string) =>
    CATEGORY_COLORS[categories.indexOf(cat) % CATEGORY_COLORS.length];

  // Group points by cell coordinate
  function getRisksAtCell(
    likelihood: number,
    impact: number,
    mode: 'inherent' | 'residual'
  ): HeatmapPoint[] {
    return points.filter((p) => {
      if (mode === 'inherent') {
        return p.inherent_likelihood === likelihood && p.inherent_impact === impact;
      }
      const l = p.residual_likelihood ?? p.inherent_likelihood;
      const i = p.residual_impact ?? p.inherent_impact;
      return l === likelihood && i === impact;
    });
  }

  function handleCellEnter(
    e: React.MouseEvent,
    likelihood: number,
    impact: number,
    mode: 'inherent' | 'residual'
  ) {
    const risks = getRisksAtCell(likelihood, impact, mode);
    if (risks.length === 0) return;
    setTooltip({ x: e.clientX, y: e.clientY, risks, mode });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Risk Heat Map</h1>
        <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
          {(['inherent', 'residual', 'both'] as ViewMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === m
                  ? 'bg-white shadow text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m === 'both' ? 'Show Both' : m === 'inherent' ? 'Inherent' : 'Residual'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="flex h-64 items-center justify-center text-gray-400">Loading…</div>
      )}

      {!isLoading && (
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <div className="flex gap-4">
            {/* Y-axis label */}
            <div className="flex flex-col items-center justify-center" style={{ width: 20 }}>
              <span
                className="text-xs font-semibold text-gray-500 tracking-widest"
                style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
              >
                IMPACT
              </span>
            </div>

            {/* Impact labels + grid */}
            <div className="flex-1">
              <div className="flex">
                {/* Impact labels on left */}
                <div className="flex flex-col" style={{ width: 90 }}>
                  {[5, 4, 3, 2, 1].map((impact) => (
                    <div
                      key={impact}
                      className="flex items-center justify-end pr-2 text-xs font-medium text-gray-600"
                      style={{ height: 80 }}
                    >
                      {IMPACT_LABELS[5 - impact]}
                    </div>
                  ))}
                </div>

                {/* Grid */}
                <div className="flex-1">
                  <div
                    className="grid"
                    style={{ gridTemplateColumns: 'repeat(5, 1fr)', gridTemplateRows: 'repeat(5, 80px)' }}
                    onMouseLeave={() => setTooltip(null)}
                  >
                    {[5, 4, 3, 2, 1].map((impact) =>
                      [1, 2, 3, 4, 5].map((likelihood) => {
                        const score = cellScore(likelihood, impact);
                        const inherentRisks = getRisksAtCell(likelihood, impact, 'inherent');
                        const residualRisks = getRisksAtCell(likelihood, impact, 'residual');

                        return (
                          <div
                            key={`${impact}-${likelihood}`}
                            className={`relative border border-white/30 flex items-center justify-center ${cellBg(score)} ${cellTextColor(score)}`}
                            onMouseEnter={(e) => {
                              const mode = viewMode === 'residual' ? 'residual' : 'inherent';
                              handleCellEnter(e, likelihood, impact, mode);
                            }}
                            onMouseMove={(e) => {
                              if (tooltip) setTooltip((prev) => prev ? { ...prev, x: e.clientX, y: e.clientY } : null);
                            }}
                          >
                            <span className="absolute top-1 right-1 text-[10px] opacity-60 font-mono">
                              {score}
                            </span>

                            {/* Risk dots */}
                            <div className="flex flex-wrap gap-0.5 p-1 justify-center">
                              {(viewMode === 'inherent' || viewMode === 'both') &&
                                inherentRisks.map((r) => (
                                  <span
                                    key={`i-${r.risk_id}`}
                                    title={r.title}
                                    className="inline-block h-3 w-3 rounded-full border-2 border-white"
                                    style={{ backgroundColor: categoryColor(r.category) }}
                                  />
                                ))}
                              {(viewMode === 'residual' || viewMode === 'both') &&
                                residualRisks.map((r) => {
                                  const moved =
                                    r.residual_likelihood !== null &&
                                    (r.residual_likelihood !== r.inherent_likelihood ||
                                      (r.residual_impact ?? r.inherent_impact) !== r.inherent_impact);
                                  return (
                                    <span
                                      key={`r-${r.risk_id}`}
                                      title={`${r.title} (residual)`}
                                      className="inline-block h-3 w-3 rounded-full border-2"
                                      style={{
                                        borderColor: categoryColor(r.category),
                                        backgroundColor: moved ? 'transparent' : categoryColor(r.category),
                                      }}
                                    />
                                  );
                                })}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* X-axis labels */}
                  <div className="grid mt-1" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
                    {LIKELIHOOD_LABELS.map((l, i) => (
                      <div key={i} className="text-center text-xs font-medium text-gray-600 px-1 leading-tight">
                        {l}
                      </div>
                    ))}
                  </div>

                  {/* X-axis title */}
                  <div className="mt-1 text-center text-xs font-semibold text-gray-500 tracking-widest">
                    LIKELIHOOD
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="mt-6 flex flex-wrap items-center gap-6">
            {/* Risk level legend */}
            <div className="flex items-center gap-3">
              {[
                { label: 'Critical (≥20)', color: 'bg-red-600' },
                { label: 'High (15–19)', color: 'bg-orange-500' },
                { label: 'Medium (9–14)', color: 'bg-yellow-400' },
                { label: 'Low (≤8)', color: 'bg-green-500' },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5">
                  <span className={`inline-block h-3 w-3 rounded ${item.color}`} />
                  <span className="text-xs text-gray-600">{item.label}</span>
                </div>
              ))}
            </div>

            <div className="h-4 w-px bg-gray-200" />

            {/* Inherent vs Residual */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="inline-block h-3 w-3 rounded-full bg-gray-500" />
                <span className="text-xs text-gray-600">Inherent (●)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="inline-block h-3 w-3 rounded-full border-2 border-gray-500" />
                <span className="text-xs text-gray-600">Residual (○)</span>
              </div>
            </div>

            <div className="h-4 w-px bg-gray-200" />

            {/* Category colors */}
            <div className="flex flex-wrap gap-3">
              {categories.map((cat, i) => (
                <div key={cat} className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-3 w-3 rounded-full"
                    style={{ backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
                  />
                  <span className="text-xs text-gray-600">{cat}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 rounded-lg bg-gray-900 px-3 py-2 text-xs text-white shadow-xl pointer-events-none max-w-xs"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <p className="font-semibold mb-1 capitalize">{tooltip.mode} risks at this cell:</p>
          <ul className="space-y-0.5">
            {tooltip.risks.map((r) => (
              <li key={r.risk_id} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: categoryColor(r.category) }}
                />
                {r.title}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
