import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchGantt, fetchPlans } from '../api';
import type { GanttItem, AuditPlan } from '../types';

interface Props {
  tenantId: string;
}

const STATUS_COLORS: Record<string, string> = {
  planning: '#818cf8',
  fieldwork: '#fbbf24',
  reporting: '#60a5fa',
  review: '#a78bfa',
  closed: '#34d399',
  cancelled: '#9ca3af',
};

const MILESTONE_STATUS_COLORS: Record<string, string> = {
  completed: '#10b981',
  overdue: '#ef4444',
  pending: '#9ca3af',
};

const LEGEND_ITEMS = [
  { label: 'Planning', color: STATUS_COLORS.planning },
  { label: 'Fieldwork', color: STATUS_COLORS.fieldwork },
  { label: 'Reporting', color: STATUS_COLORS.reporting },
  { label: 'Review', color: STATUS_COLORS.review },
  { label: 'Closed', color: STATUS_COLORS.closed },
  { label: 'Cancelled', color: STATUS_COLORS.cancelled },
];

const MIN_PX_PER_DAY = 3;
const ROW_HEIGHT = 44;
const LABEL_WIDTH = 220;
const HEADER_HEIGHT = 40;

function parseDate(s?: string): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function formatMonth(d: Date): string {
  return d.toLocaleString('default', { month: 'short', year: '2-digit' });
}

interface Tooltip {
  x: number;
  y: number;
  item: GanttItem;
}

export default function GanttChart({ tenantId: _tenantId }: Props) {
  const [planId, setPlanId] = useState<string>('');
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: plans = [] } = useQuery<AuditPlan[]>({
    queryKey: ['plans'],
    queryFn: fetchPlans,
  });

  const { data: ganttItems = [], isLoading } = useQuery<GanttItem[]>({
    queryKey: ['gantt', planId],
    queryFn: () => fetchGantt(planId || undefined),
  });

  // Compute date range
  const allDates: Date[] = [];
  for (const item of ganttItems) {
    const s = parseDate(item.start);
    const e = parseDate(item.end);
    if (s) allDates.push(s);
    if (e) allDates.push(e);
    for (const ms of item.milestones) {
      const d = parseDate(ms.due);
      if (d) allDates.push(d);
    }
  }

  const today = new Date();
  allDates.push(today);

  const minDate = allDates.length > 0
    ? new Date(Math.min(...allDates.map((d) => d.getTime())))
    : today;
  const maxDate = allDates.length > 0
    ? new Date(Math.max(...allDates.map((d) => d.getTime())))
    : addDays(today, 90);

  // Add padding
  const chartStart = addDays(minDate, -7);
  const chartEnd = addDays(maxDate, 14);
  const totalDays = Math.max(
    Math.ceil((chartEnd.getTime() - chartStart.getTime()) / 86400000),
    1
  );
  const chartWidth = Math.max(totalDays * MIN_PX_PER_DAY, 800);

  function xForDate(d: Date): number {
    return ((d.getTime() - chartStart.getTime()) / 86400000) * MIN_PX_PER_DAY;
  }

  // Month labels
  const monthLabels: Array<{ label: string; x: number }> = [];
  let cursor = new Date(chartStart.getFullYear(), chartStart.getMonth(), 1);
  while (cursor <= chartEnd) {
    monthLabels.push({ label: formatMonth(cursor), x: xForDate(cursor) });
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
  }

  const todayX = xForDate(today);
  const svgHeight = HEADER_HEIGHT + ganttItems.length * ROW_HEIGHT + 20;

  const handleMouseMove = useCallback(
    (e: React.MouseEvent, item: GanttItem) => {
      setTooltip({ x: e.clientX, y: e.clientY, item });
    },
    []
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  function milestoneStatus(ms: { done: boolean; due: string }): string {
    if (ms.done) return 'completed';
    if (new Date(ms.due) < today) return 'overdue';
    return 'pending';
  }

  return (
    <div className="space-y-4">
      {/* Plan selector */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4 flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700">Plan:</label>
        <select
          value={planId}
          onChange={(e) => setPlanId(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">All Plans</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>{p.plan_year} — {p.title}</option>
          ))}
        </select>
        <span className="text-xs text-gray-400">{ganttItems.length} engagements</span>
      </div>

      {/* Gantt body */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">Loading Gantt…</div>
        ) : ganttItems.length === 0 ? (
          <div className="p-12 text-center text-gray-400">No engagement data to display</div>
        ) : (
          <div className="flex overflow-hidden" style={{ height: svgHeight + 8 }}>
            {/* Fixed left labels */}
            <div
              className="shrink-0 bg-gray-50 border-r border-gray-200 overflow-hidden"
              style={{ width: LABEL_WIDTH }}
            >
              {/* Header spacer */}
              <div style={{ height: HEADER_HEIGHT }} className="border-b border-gray-200" />
              {ganttItems.map((item, i) => (
                <div
                  key={item.id}
                  style={{ height: ROW_HEIGHT }}
                  className="flex items-center px-3 border-b border-gray-100"
                >
                  <div className="overflow-hidden">
                    {item.code && (
                      <span className="text-xs font-mono bg-gray-200 text-gray-600 px-1 py-0.5 rounded mr-1">
                        {item.code}
                      </span>
                    )}
                    <span className="text-xs font-medium text-gray-800 truncate block" title={item.title}>
                      {item.title}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Scrollable SVG area */}
            <div ref={containerRef} className="flex-1 overflow-x-auto overflow-y-hidden">
              <svg width={chartWidth} height={svgHeight}>
                {/* Month header */}
                <g>
                  {monthLabels.map((ml, i) => (
                    <g key={i}>
                      <line
                        x1={ml.x}
                        y1={0}
                        x2={ml.x}
                        y2={svgHeight}
                        stroke="#e5e7eb"
                        strokeWidth={1}
                      />
                      <text
                        x={ml.x + 4}
                        y={HEADER_HEIGHT - 10}
                        fontSize={11}
                        fill="#6b7280"
                        fontFamily="system-ui"
                      >
                        {ml.label}
                      </text>
                    </g>
                  ))}
                  <line
                    x1={0}
                    y1={HEADER_HEIGHT}
                    x2={chartWidth}
                    y2={HEADER_HEIGHT}
                    stroke="#e5e7eb"
                    strokeWidth={1}
                  />
                </g>

                {/* Today line */}
                <line
                  x1={todayX}
                  y1={0}
                  x2={todayX}
                  y2={svgHeight}
                  stroke="#ef4444"
                  strokeWidth={1.5}
                  strokeDasharray="5,3"
                />
                <text
                  x={todayX + 3}
                  y={14}
                  fontSize={10}
                  fill="#ef4444"
                  fontFamily="system-ui"
                  fontWeight="500"
                >
                  Today
                </text>

                {/* Engagement rows */}
                {ganttItems.map((item, i) => {
                  const y = HEADER_HEIGHT + i * ROW_HEIGHT;
                  const barY = y + ROW_HEIGHT * 0.25;
                  const barH = ROW_HEIGHT * 0.5;
                  const startDate = parseDate(item.start);
                  const endDate = parseDate(item.end);
                  const barX = startDate ? xForDate(startDate) : 0;
                  const barW = startDate && endDate
                    ? Math.max(xForDate(endDate) - barX, 4)
                    : 4;
                  const barColor = STATUS_COLORS[item.status] ?? '#94a3b8';

                  return (
                    <g key={item.id}>
                      {/* Row bg */}
                      <rect
                        x={0}
                        y={y}
                        width={chartWidth}
                        height={ROW_HEIGHT}
                        fill={i % 2 === 0 ? 'transparent' : '#f9fafb'}
                      />
                      {/* Bar */}
                      {startDate && (
                        <rect
                          x={barX}
                          y={barY}
                          width={barW}
                          height={barH}
                          rx={3}
                          fill={barColor}
                          opacity={0.85}
                          style={{ cursor: 'pointer' }}
                          onMouseMove={(e) => handleMouseMove(e, item)}
                          onMouseLeave={handleMouseLeave}
                        />
                      )}
                      {/* Milestone diamonds */}
                      {item.milestones.map((ms, j) => {
                        const msDate = parseDate(ms.due);
                        if (!msDate) return null;
                        const msX = xForDate(msDate);
                        const msCenterY = y + ROW_HEIGHT / 2;
                        const msSt = milestoneStatus(ms);
                        const msColor = MILESTONE_STATUS_COLORS[msSt] ?? '#9ca3af';
                        const size = 7;
                        const points = [
                          `${msX},${msCenterY - size}`,
                          `${msX + size},${msCenterY}`,
                          `${msX},${msCenterY + size}`,
                          `${msX - size},${msCenterY}`,
                        ].join(' ');
                        return (
                          <g key={j}>
                            <polygon
                              points={points}
                              fill={msColor}
                              stroke="white"
                              strokeWidth={1.5}
                              style={{ cursor: 'default' }}
                            />
                          </g>
                        );
                      })}
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
        <div className="text-xs font-semibold text-gray-600 mb-2">Legend</div>
        <div className="flex flex-wrap gap-4">
          {LEGEND_ITEMS.map((l) => (
            <div key={l.label} className="flex items-center gap-1.5">
              <div className="w-5 h-3 rounded" style={{ backgroundColor: l.color }} />
              <span className="text-xs text-gray-600">{l.label}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5">
            <svg width={14} height={14} viewBox="-7 -7 14 14">
              <polygon points="0,-6 6,0 0,6 -6,0" fill={MILESTONE_STATUS_COLORS.completed} />
            </svg>
            <span className="text-xs text-gray-600">Milestone (complete)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg width={14} height={14} viewBox="-7 -7 14 14">
              <polygon points="0,-6 6,0 0,6 -6,0" fill={MILESTONE_STATUS_COLORS.overdue} />
            </svg>
            <span className="text-xs text-gray-600">Milestone (overdue)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg width={14} height={14} viewBox="-7 -7 14 14">
              <polygon points="0,-6 6,0 0,6 -6,0" fill={MILESTONE_STATUS_COLORS.pending} />
            </svg>
            <span className="text-xs text-gray-600">Milestone (pending)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <svg width={14} height={4} viewBox="0 0 14 4">
              <line x1={0} y1={2} x2={14} y2={2} stroke="#ef4444" strokeWidth={2} strokeDasharray="4,2" />
            </svg>
            <span className="text-xs text-gray-600">Today</span>
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg pointer-events-none max-w-xs"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <div className="font-semibold mb-1">
            {tooltip.item.code ? `[${tooltip.item.code}] ` : ''}
            {tooltip.item.title}
          </div>
          <div className="text-gray-300 mb-1">
            Status: <span className="capitalize">{tooltip.item.status}</span>
          </div>
          <div className="text-gray-300">
            {tooltip.item.start ?? '?'} → {tooltip.item.end ?? '?'}
          </div>
          {tooltip.item.milestones.length > 0 && (
            <div className="mt-1 text-gray-400">
              Milestones:
              {tooltip.item.milestones.slice(0, 5).map((m, i) => (
                <div key={i} className="pl-2">
                  {m.done ? '✓' : '○'} {m.title} ({m.due})
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
