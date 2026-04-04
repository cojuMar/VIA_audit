import { useQuery } from '@tanstack/react-query';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Briefcase, Flag, Clock, Globe, AlertTriangle } from 'lucide-react';
import {
  fetchEngagements,
  fetchOverdueMilestones,
  fetchUniverseCoverage,
  fetchUtilization,
} from '../api';
import type { Engagement, Milestone, UniverseCoverage, AuditEntity } from '../types';

interface Props {
  tenantId: string;
}

const STATUS_COLORS: Record<string, string> = {
  planning: '#6366f1',
  fieldwork: '#f59e0b',
  reporting: '#3b82f6',
  review: '#8b5cf6',
  closed: '#10b981',
  cancelled: '#6b7280',
};

const PIE_COLORS = ['#6366f1', '#e5e7eb'];

function MetricCard({
  icon,
  label,
  value,
  sub,
  alert,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  alert?: boolean;
}) {
  return (
    <div className={`bg-white rounded-xl shadow-sm border p-5 flex gap-4 items-start ${alert ? 'border-red-300' : 'border-gray-200'}`}>
      <div className={`p-2 rounded-lg ${alert ? 'bg-red-100 text-red-600' : 'bg-indigo-50 text-indigo-600'}`}>
        {icon}
      </div>
      <div>
        <div className="text-2xl font-bold text-gray-900">{value}</div>
        <div className="text-sm font-medium text-gray-600">{label}</div>
        {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

function getRiskPillClass(score: number) {
  if (score >= 8) return 'bg-red-100 text-red-800';
  if (score >= 6) return 'bg-orange-100 text-orange-800';
  if (score >= 4) return 'bg-yellow-100 text-yellow-800';
  return 'bg-green-100 text-green-800';
}

export default function PlanningDashboard({ tenantId: _tenantId }: Props) {
  const currentYear = new Date().getFullYear();

  const now = new Date();
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
  const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];

  const { data: engagementsData } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => fetchEngagements(),
  });

  const { data: overdueMilestones } = useQuery<Milestone[]>({
    queryKey: ['milestones', 'overdue'],
    queryFn: fetchOverdueMilestones,
  });

  const { data: coverage } = useQuery<UniverseCoverage>({
    queryKey: ['universe-coverage', currentYear],
    queryFn: () => fetchUniverseCoverage(currentYear),
  });

  const { data: utilization } = useQuery<{ by_auditor: Array<{ name: string; hours: number }> }>({
    queryKey: ['utilization', monthStart, monthEnd],
    queryFn: () => fetchUtilization(monthStart, monthEnd),
  });

  const engagements = engagementsData ?? [];
  const milestones = overdueMilestones ?? [];

  const activeEngagements = engagements.filter(
    (e) => !['closed', 'cancelled'].includes(e.status)
  ).length;

  const totalHoursThisMonth = (utilization?.by_auditor ?? []).reduce(
    (acc, a) => acc + a.hours,
    0
  );

  // Status distribution for bar chart
  const statusCounts = engagements.reduce<Record<string, number>>((acc, e) => {
    acc[e.status] = (acc[e.status] ?? 0) + 1;
    return acc;
  }, {});
  const statusBarData = Object.entries(statusCounts).map(([status, count]) => ({
    status,
    count,
  }));

  // Upcoming milestones (non-overdue, sorted by due_date) — next 10
  const upcomingMilestones = [...milestones]
    .sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime())
    .slice(0, 10);

  // High-risk unaudited
  const highRiskUnaudited: AuditEntity[] = coverage?.high_risk_unaudited?.slice(0, 5) ?? [];

  // Coverage donut
  const covered = coverage?.entities_with_audits ?? 0;
  const uncovered = (coverage?.total_entities ?? 0) - covered;
  const coveragePct = coverage?.coverage_pct ?? 0;
  const pieData = [
    { name: 'Covered', value: covered },
    { name: 'Uncovered', value: uncovered },
  ];

  function daysUntilColor(days?: number) {
    if (days === undefined) return 'text-gray-500';
    if (days < 0) return 'text-red-600 font-bold';
    if (days < 3) return 'text-red-600 font-semibold';
    if (days < 7) return 'text-orange-500 font-semibold';
    return 'text-gray-600';
  }

  function daysLabel(days?: number) {
    if (days === undefined) return '—';
    if (days < 0) return `${Math.abs(days)}d overdue`;
    if (days === 0) return 'Due today';
    return `${days}d`;
  }

  return (
    <div className="space-y-6">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={<Briefcase className="w-5 h-5" />}
          label="Active Engagements"
          value={activeEngagements}
          sub="currently in progress"
        />
        <MetricCard
          icon={<Flag className="w-5 h-5" />}
          label="Overdue Milestones"
          value={milestones.filter((m) => m.status === 'overdue' || (m.days_until_due !== undefined && m.days_until_due < 0)).length}
          sub="require attention"
          alert={milestones.some((m) => m.days_until_due !== undefined && m.days_until_due < 0)}
        />
        <MetricCard
          icon={<Clock className="w-5 h-5" />}
          label="Hours Logged (Month)"
          value={totalHoursThisMonth.toFixed(1)}
          sub={`${monthStart} — ${monthEnd}`}
        />
        <MetricCard
          icon={<Globe className="w-5 h-5" />}
          label="Universe Coverage"
          value={`${coveragePct.toFixed(1)}%`}
          sub={`${covered} of ${coverage?.total_entities ?? 0} entities audited`}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Coverage donut */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Universe Coverage</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                dataKey="value"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {pieData.map((_entry, index) => (
                  <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Status bar chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Engagement Status</h2>
          {statusBarData.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
              No engagement data
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={statusBarData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <XAxis dataKey="status" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {statusBarData.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={STATUS_COLORS[entry.status] ?? '#94a3b8'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upcoming milestones */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Upcoming Milestones</h2>
          {upcomingMilestones.length === 0 ? (
            <div className="text-sm text-gray-400 py-8 text-center">No upcoming milestones</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {upcomingMilestones.map((m) => (
                <div key={m.id} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-800 truncate">{m.title}</div>
                    <div className="text-xs text-gray-400">{m.milestone_type}</div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-gray-500">
                      {new Date(m.due_date).toLocaleDateString()}
                    </span>
                    <span className={`text-xs ${daysUntilColor(m.days_until_due)}`}>
                      {daysLabel(m.days_until_due)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* High-risk unaudited */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-800 mb-1 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            High-Risk Unaudited Entities
          </h2>
          <p className="text-xs text-gray-400 mb-4">Risk ≥ 7, not in current year plan</p>
          {highRiskUnaudited.length === 0 ? (
            <div className="text-sm text-gray-400 py-8 text-center">All high-risk entities are covered</div>
          ) : (
            <div className="space-y-2">
              {highRiskUnaudited.map((entity) => (
                <div
                  key={entity.id}
                  className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100"
                >
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded-full ${getRiskPillClass(entity.risk_score)}`}
                  >
                    {entity.risk_score.toFixed(1)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-800 truncate">{entity.name}</div>
                    {entity.department && (
                      <div className="text-xs text-gray-400">{entity.department}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
