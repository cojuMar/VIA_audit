import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Clock, AlertCircle, CheckCircle } from 'lucide-react';
import {
  fetchEngagements,
  fetchTimeEntries,
  fetchUtilization,
  fetchBudgetStatus,
  fetchPlans,
  logHours,
} from '../api';
import type { Engagement, TimeEntry, AuditPlan } from '../types';

interface Props {
  tenantId: string;
}

const ACTIVITY_TYPES = ['planning', 'fieldwork', 'reporting', 'review', 'admin', 'travel'];

const ACTIVITY_COLORS: Record<string, string> = {
  planning: '#818cf8',
  fieldwork: '#fbbf24',
  reporting: '#60a5fa',
  review: '#a78bfa',
  admin: '#9ca3af',
  travel: '#f97316',
};

interface BudgetRow {
  engagement_id: string;
  title: string;
  code?: string;
  budget_hours: number;
  logged_hours: number;
  variance: number;
  pct_consumed: number;
}

function BudgetIndicator({ pct }: { pct: number }) {
  if (pct >= 100)
    return <AlertCircle className="w-4 h-4 text-red-500" />;
  if (pct >= 80)
    return <AlertCircle className="w-4 h-4 text-amber-500" />;
  return <CheckCircle className="w-4 h-4 text-green-500" />;
}

function weekBounds(offset = 0): { start: string; end: string } {
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((day + 6) % 7) + offset * 7);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return {
    start: monday.toISOString().split('T')[0],
    end: sunday.toISOString().split('T')[0],
  };
}

function weekLabel(offset: number): string {
  if (offset === 0) return 'This week';
  if (offset === -1) return 'Last week';
  if (offset === -2) return '2 weeks ago';
  return `${Math.abs(offset)} weeks ago`;
}

export default function TimeTracker({ tenantId: _tenantId }: Props) {
  const qc = useQueryClient();

  // Quick Log form
  const [logForm, setLogForm] = useState({
    engagement_id: '',
    auditor_name: '',
    auditor_email: '',
    entry_date: new Date().toISOString().split('T')[0],
    hours: 1,
    activity_type: 'fieldwork',
    description: '',
    is_billable: true,
  });
  const [logSuccess, setLogSuccess] = useState(false);

  // Filters
  const [filterAuditor, setFilterAuditor] = useState('');
  const [filterEngagement, setFilterEngagement] = useState('');
  const [filterStart, setFilterStart] = useState(weekBounds(-3).start);
  const [filterEnd, setFilterEnd] = useState(weekBounds(0).end);

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => fetchEngagements(),
  });

  const { data: plans = [] } = useQuery<AuditPlan[]>({
    queryKey: ['plans'],
    queryFn: fetchPlans,
  });

  const currentPlan = useMemo(() => {
    const y = new Date().getFullYear();
    return plans.find((p) => p.plan_year === y);
  }, [plans]);

  const { data: timeEntries = [] } = useQuery<TimeEntry[]>({
    queryKey: ['time-entries', filterAuditor, filterEngagement, filterStart, filterEnd],
    queryFn: () =>
      fetchTimeEntries({
        auditor_email: filterAuditor || undefined,
        engagement_id: filterEngagement || undefined,
        start_date: filterStart || undefined,
        end_date: filterEnd || undefined,
      }),
  });

  const thisWeek = weekBounds(0);
  const { data: thisWeekEntries = [] } = useQuery<TimeEntry[]>({
    queryKey: ['time-entries-week', thisWeek.start, thisWeek.end],
    queryFn: () =>
      fetchTimeEntries({ start_date: thisWeek.start, end_date: thisWeek.end }),
  });

  // Utilization: last 4 weeks
  const util4wStart = weekBounds(-3).start;
  const util4wEnd = weekBounds(0).end;
  const { data: utilization } = useQuery<{
    by_week: Array<{
      week_start: string;
      by_activity: Record<string, number>;
      auditors: Array<{ name: string; hours: number }>;
    }>;
  }>({
    queryKey: ['utilization', util4wStart, util4wEnd],
    queryFn: () => fetchUtilization(util4wStart, util4wEnd),
  });

  const { data: budgetStatus = [] } = useQuery<BudgetRow[]>({
    queryKey: ['budget-status', currentPlan?.id],
    queryFn: () => fetchBudgetStatus(currentPlan!.id),
    enabled: !!currentPlan,
  });

  const logMutation = useMutation({
    mutationFn: logHours,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['time-entries'] });
      qc.invalidateQueries({ queryKey: ['time-entries-week'] });
      qc.invalidateQueries({ queryKey: ['utilization'] });
      qc.invalidateQueries({ queryKey: ['budget-status'] });
      qc.invalidateQueries({ queryKey: ['engagements'] });
      setLogSuccess(true);
      setTimeout(() => setLogSuccess(false), 3000);
      setLogForm((f) => ({
        ...f,
        hours: 1,
        description: '',
      }));
    },
  });

  // Build utilization chart data
  const utilChartData = useMemo(() => {
    if (!utilization?.by_week) {
      // Fallback: group timeEntries by week
      const weeks: Record<string, Record<string, number>> = {};
      for (let i = -3; i <= 0; i++) {
        const wb = weekBounds(i);
        weeks[wb.start] = {};
      }
      for (const entry of timeEntries) {
        const entryDate = new Date(entry.entry_date);
        // find week key
        for (const wk of Object.keys(weeks)) {
          const wkEnd = new Date(wk);
          wkEnd.setDate(wkEnd.getDate() + 6);
          if (entryDate >= new Date(wk) && entryDate <= wkEnd) {
            weeks[wk][entry.activity_type] =
              (weeks[wk][entry.activity_type] ?? 0) + entry.hours;
            break;
          }
        }
      }
      return Object.entries(weeks).map(([wk, acts]) => ({
        week: wk,
        ...acts,
      }));
    }
    return utilization.by_week.map((w) => ({
      week: w.week_start,
      ...w.by_activity,
    }));
  }, [utilization, timeEntries]);

  // Group this week entries by auditor
  const weekByAuditor = useMemo(() => {
    const m: Record<string, { name: string; email: string; entries: TimeEntry[] }> = {};
    for (const e of thisWeekEntries) {
      const key = e.auditor_email ?? e.auditor_name;
      if (!m[key]) m[key] = { name: e.auditor_name, email: e.auditor_email ?? '', entries: [] };
      m[key].entries.push(e);
    }
    return Object.values(m);
  }, [thisWeekEntries]);

  function handleLogSubmit(e: React.FormEvent) {
    e.preventDefault();
    logMutation.mutate(logForm);
  }

  return (
    <div className="space-y-6">
      {/* Quick Log form */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Clock className="w-4 h-4 text-indigo-600" />
          Log Hours
        </h2>
        <form onSubmit={handleLogSubmit} className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">Engagement *</label>
            <select
              required
              value={logForm.engagement_id}
              onChange={(e) => setLogForm((f) => ({ ...f, engagement_id: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              <option value="">— Select —</option>
              {engagements.map((eng) => (
                <option key={eng.id} value={eng.id}>
                  {eng.engagement_code ? `[${eng.engagement_code}] ` : ''}{eng.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Auditor Name *</label>
            <input
              required
              type="text"
              value={logForm.auditor_name}
              onChange={(e) => setLogForm((f) => ({ ...f, auditor_name: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Date</label>
            <input
              type="date"
              value={logForm.entry_date}
              onChange={(e) => setLogForm((f) => ({ ...f, entry_date: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Hours</label>
            <input
              type="number"
              min={0.25}
              step={0.25}
              max={24}
              value={logForm.hours}
              onChange={(e) => setLogForm((f) => ({ ...f, hours: Number(e.target.value) }))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Activity</label>
            <select
              value={logForm.activity_type}
              onChange={(e) => setLogForm((f) => ({ ...f, activity_type: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {ACTIVITY_TYPES.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2 lg:col-span-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <input
              type="text"
              value={logForm.description}
              onChange={(e) => setLogForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Optional description…"
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={logForm.is_billable}
                onChange={(e) => setLogForm((f) => ({ ...f, is_billable: e.target.checked }))}
                className="accent-indigo-600"
              />
              Billable
            </label>
          </div>
          <div>
            <button
              type="submit"
              disabled={logMutation.isPending}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg py-2 text-sm font-medium disabled:opacity-60 transition-colors"
            >
              {logMutation.isPending ? 'Logging…' : 'Log Hours'}
            </button>
          </div>
          {logSuccess && (
            <div className="sm:col-span-3 lg:col-span-6 text-green-600 text-xs flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" /> Hours logged successfully
            </div>
          )}
        </form>
      </div>

      {/* Two-column row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* This week */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-3">My Hours This Week</h2>
          <div className="text-xs text-gray-400 mb-3">
            {thisWeek.start} — {thisWeek.end}
          </div>
          {weekByAuditor.length === 0 ? (
            <div className="text-center text-gray-400 text-sm py-6">No hours logged this week</div>
          ) : (
            weekByAuditor.map((a) => (
              <div key={a.email} className="mb-4">
                <div className="font-medium text-sm text-gray-800 mb-1">{a.name}</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-100 text-gray-500">
                        <th className="text-left py-1 pr-3">Date</th>
                        <th className="text-left py-1 pr-3">Engagement</th>
                        <th className="text-left py-1 pr-3">Activity</th>
                        <th className="text-right py-1">Hours</th>
                      </tr>
                    </thead>
                    <tbody>
                      {a.entries.map((entry) => {
                        const eng = engagements.find((e) => e.id === entry.engagement_id);
                        return (
                          <tr key={entry.id} className="border-b border-gray-50">
                            <td className="py-1 pr-3 text-gray-500">{entry.entry_date}</td>
                            <td className="py-1 pr-3 text-gray-700 truncate max-w-32">
                              {eng?.title ?? entry.engagement_id}
                            </td>
                            <td className="py-1 pr-3">
                              <span
                                className="px-1.5 py-0.5 rounded text-xs"
                                style={{
                                  backgroundColor: (ACTIVITY_COLORS[entry.activity_type] ?? '#9ca3af') + '22',
                                  color: ACTIVITY_COLORS[entry.activity_type] ?? '#6b7280',
                                }}
                              >
                                {entry.activity_type}
                              </span>
                            </td>
                            <td className="py-1 text-right font-medium text-gray-800">{entry.hours}h</td>
                          </tr>
                        );
                      })}
                      <tr>
                        <td colSpan={3} className="pt-1 text-right text-gray-500 font-medium">Total</td>
                        <td className="pt-1 text-right font-bold text-gray-900">
                          {a.entries.reduce((s, e) => s + e.hours, 0)}h
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Utilization chart */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-3">Utilization — Last 4 Weeks</h2>
          {utilChartData.length === 0 ? (
            <div className="text-center text-gray-400 text-sm py-6">No utilization data</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={utilChartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <XAxis
                  dataKey="week"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v, i) => weekLabel(-3 + i)}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                {ACTIVITY_TYPES.map((act) => (
                  <Bar
                    key={act}
                    dataKey={act}
                    stackId="util"
                    fill={ACTIVITY_COLORS[act] ?? '#9ca3af'}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Budget status table */}
      {currentPlan && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-3">
            Budget Status — {currentPlan.title}
          </h2>
          {budgetStatus.length === 0 ? (
            <div className="text-center text-gray-400 text-sm py-6">No budget data</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left bg-gray-50">
                    <th className="px-3 py-2 text-xs font-semibold text-gray-600">Engagement</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-600 text-right">Budget</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-600 text-right">Logged</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-600 text-right">Variance</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-600">Consumed</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {budgetStatus.map((row) => {
                    const pct = row.pct_consumed ?? (row.budget_hours > 0 ? (row.logged_hours / row.budget_hours) * 100 : 0);
                    const barColor = pct >= 100 ? 'bg-red-400' : pct >= 80 ? 'bg-amber-400' : 'bg-green-400';
                    return (
                      <tr key={row.engagement_id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 font-medium text-gray-800">
                          {row.code && (
                            <span className="font-mono text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded mr-1">
                              {row.code}
                            </span>
                          )}
                          {row.title}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-600">{row.budget_hours}h</td>
                        <td className="px-3 py-2 text-right text-gray-600">{row.logged_hours}h</td>
                        <td className={`px-3 py-2 text-right font-medium ${row.variance < 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {row.variance > 0 ? '+' : ''}{row.variance}h
                        </td>
                        <td className="px-3 py-2 min-w-28">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                              <div
                                className={`${barColor} h-2 rounded-full transition-all`}
                                style={{ width: `${Math.min(pct, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-gray-500 w-10 text-right">{pct.toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-center">
                          <BudgetIndicator pct={pct} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Filterable time entries report */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h2 className="text-base font-semibold text-gray-800 mb-3">Time Entries Report</h2>
        <p className="text-xs text-gray-400 mb-3">Filterable report below</p>
        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Auditor Email</label>
            <input
              type="text"
              value={filterAuditor}
              onChange={(e) => setFilterAuditor(e.target.value)}
              placeholder="Filter by email…"
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Engagement</label>
            <select
              value={filterEngagement}
              onChange={(e) => setFilterEngagement(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
            >
              <option value="">All Engagements</option>
              {engagements.map((eng) => (
                <option key={eng.id} value={eng.id}>{eng.title}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">From</label>
            <input
              type="date"
              value={filterStart}
              onChange={(e) => setFilterStart(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">To</label>
            <input
              type="date"
              value={filterEnd}
              onChange={(e) => setFilterEnd(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left">
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Date</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Auditor</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Engagement</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Activity</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600 text-right">Hours</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Description</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-600">Billable</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {timeEntries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-400 text-sm">
                    No time entries found
                  </td>
                </tr>
              ) : (
                timeEntries.map((entry) => {
                  const eng = engagements.find((e) => e.id === entry.engagement_id);
                  return (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{entry.entry_date}</td>
                      <td className="px-3 py-2">
                        <div className="font-medium text-gray-800 text-xs">{entry.auditor_name}</div>
                        {entry.auditor_email && (
                          <div className="text-gray-400 text-xs">{entry.auditor_email}</div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-gray-700 text-xs max-w-32 truncate">
                        {eng?.title ?? entry.engagement_id}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className="px-1.5 py-0.5 rounded text-xs"
                          style={{
                            backgroundColor: (ACTIVITY_COLORS[entry.activity_type] ?? '#9ca3af') + '22',
                            color: ACTIVITY_COLORS[entry.activity_type] ?? '#6b7280',
                          }}
                        >
                          {entry.activity_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-800">{entry.hours}h</td>
                      <td className="px-3 py-2 text-gray-500 text-xs max-w-48 truncate">
                        {entry.description ?? '—'}
                      </td>
                      <td className="px-3 py-2">
                        {entry.is_billable ? (
                          <span className="text-xs bg-green-50 text-green-600 px-1.5 py-0.5 rounded">
                            Billable
                          </span>
                        ) : (
                          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                            Non-billable
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
            {timeEntries.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-gray-200">
                  <td colSpan={4} className="px-3 py-2 text-xs font-semibold text-gray-600 text-right">
                    Total
                  </td>
                  <td className="px-3 py-2 text-right font-bold text-gray-900">
                    {timeEntries.reduce((s, e) => s + e.hours, 0).toFixed(1)}h
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
