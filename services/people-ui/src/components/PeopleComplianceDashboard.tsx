import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  Legend,
} from 'recharts';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  AlertOctagon,
  Shield,
  BookOpen,
  UserCheck,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { fetchOrgCompliance, fetchEscalations, setTenant } from '../api';
import type { OrgComplianceSummary, Escalation } from '../types';

interface Props {
  tenantId: string;
}

const GREEN = '#22c55e';
const AMBER = '#f59e0b';
const RED = '#ef4444';
const BLUE = '#3b82f6';

function scoreColor(score: number) {
  if (score >= 90) return GREEN;
  if (score >= 70) return AMBER;
  return RED;
}

function ScoreGauge({ score, label }: { score: number; label: string }) {
  const color = scoreColor(score);
  const data = [{ name: label, value: score, fill: color }];
  return (
    <div className="flex flex-col items-center">
      <RadialBarChart
        width={120}
        height={120}
        cx={60}
        cy={60}
        innerRadius={40}
        outerRadius={55}
        barSize={12}
        data={data}
        startAngle={90}
        endAngle={-270}
      >
        <RadialBar dataKey="value" cornerRadius={6} background={{ fill: '#374151' }} />
      </RadialBarChart>
      <div className="text-2xl font-bold mt-1" style={{ color }}>
        {score.toFixed(0)}
      </div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  );
}

function IssueTypeIcon({ type }: { type: string }) {
  const t = type.toLowerCase();
  if (t.includes('training')) return <BookOpen size={16} className="text-amber-400" />;
  if (t.includes('policy')) return <Shield size={16} className="text-blue-400" />;
  if (t.includes('background')) return <UserCheck size={16} className="text-purple-400" />;
  return <AlertTriangle size={16} className="text-red-400" />;
}

const ESCALATION_TYPE_COLORS: Record<string, string> = {
  policy_overdue: 'bg-blue-900 text-blue-200',
  training_overdue: 'bg-amber-900 text-amber-200',
  background_check_expired: 'bg-orange-900 text-orange-200',
  training_failed: 'bg-red-900 text-red-200',
};

function EscalationTypeBadge({ type }: { type: string }) {
  const cls = ESCALATION_TYPE_COLORS[type] ?? 'bg-gray-800 text-gray-300';
  return (
    <span className={`badge ${cls}`}>
      {type.replace(/_/g, ' ')}
    </span>
  );
}

export default function PeopleComplianceDashboard({ tenantId }: Props) {
  setTenant(tenantId);

  const {
    data: summary,
    isLoading: summaryLoading,
    dataUpdatedAt,
    refetch,
  } = useQuery<OrgComplianceSummary>({
    queryKey: ['org-compliance', tenantId],
    queryFn: fetchOrgCompliance,
    refetchInterval: 60_000,
  });

  const { data: escalations, isLoading: escLoading } = useQuery<Escalation[]>({
    queryKey: ['escalations', tenantId],
    queryFn: () => fetchEscalations({ resolved: false }),
    refetchInterval: 60_000,
  });

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—';

  if (summaryLoading || escLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <RefreshCw size={20} className="animate-spin mr-2" /> Loading compliance data…
      </div>
    );
  }

  const s = summary!;
  const esc = escalations ?? [];

  // Department bar chart data
  const deptData = (s.by_department ?? []).map((d) => ({
    dept: d.dept,
    score: d.score,
    fill: scoreColor(d.score),
  }));

  // Pie chart data
  const pieData = [
    { name: 'Compliant', value: s.compliant_count, fill: GREEN },
    { name: 'At Risk', value: s.at_risk_count, fill: AMBER },
    { name: 'Non-Compliant', value: s.non_compliant_count, fill: RED },
  ];

  const recentEscalations = esc.slice(0, 10);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">People &amp; Training Compliance</h1>
          <p className="text-sm text-gray-400 mt-0.5">Last updated: {lastUpdated}</p>
        </div>
        <button className="btn-secondary" onClick={() => refetch()}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-5 gap-4">
        {/* Overall Score */}
        <div className="card flex flex-col items-center col-span-1">
          <div className="text-xs text-gray-400 mb-2 font-semibold uppercase tracking-wider">
            Overall Score
          </div>
          <ScoreGauge score={s.overall_score} label="Score" />
        </div>

        {/* Compliant */}
        <div className="card flex flex-col justify-between">
          <div className="flex items-center gap-2 text-green-400 mb-2">
            <CheckCircle size={18} />
            <span className="text-sm font-semibold">Compliant</span>
          </div>
          <div className="text-3xl font-bold text-green-400">{s.compliant_count}</div>
          <div className="text-xs text-gray-500">of {s.total_employees} employees</div>
        </div>

        {/* At Risk */}
        <div className="card flex flex-col justify-between">
          <div className="flex items-center gap-2 text-amber-400 mb-2">
            <AlertTriangle size={18} />
            <span className="text-sm font-semibold">At Risk</span>
          </div>
          <div className="text-3xl font-bold text-amber-400">{s.at_risk_count}</div>
          <div className="text-xs text-gray-500">employees</div>
        </div>

        {/* Non-Compliant */}
        <div className="card flex flex-col justify-between">
          <div className="flex items-center gap-2 text-red-400 mb-2">
            <XCircle size={18} />
            <span className="text-sm font-semibold">Non-Compliant</span>
          </div>
          <div className="text-3xl font-bold text-red-400">{s.non_compliant_count}</div>
          <div className="text-xs text-gray-500">employees</div>
        </div>

        {/* Open Escalations */}
        <div className="card flex flex-col justify-between">
          <div className="flex items-center gap-2 text-blue-400 mb-2">
            <AlertOctagon size={18} />
            <span className="text-sm font-semibold">Open Escalations</span>
          </div>
          <div className="text-3xl font-bold text-blue-400">{esc.length}</div>
          <div className="text-xs text-gray-500">unresolved</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Compliance by Department */}
        <div className="card col-span-2">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Compliance by Department</h2>
          {deptData.length === 0 ? (
            <div className="text-center text-gray-500 py-8">No department data</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={deptData}
                layout="vertical"
                margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
              >
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="dept"
                  tick={{ fill: '#d1d5db', fontSize: 11 }}
                  width={110}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#f9fafb' }}
                  formatter={(v: number) => [`${v.toFixed(1)}%`, 'Score']}
                />
                <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                  {deptData.map((entry, index) => (
                    <Cell key={index} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Score Distribution Pie */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Score Distribution</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="45%"
                outerRadius={70}
                dataKey="value"
                label={({ name, percent }) =>
                  percent > 0.05 ? `${(percent * 100).toFixed(0)}%` : ''
                }
                labelLine={false}
              >
                {pieData.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} />
                ))}
              </Pie>
              <Legend
                iconType="circle"
                iconSize={10}
                formatter={(value) => (
                  <span style={{ color: '#d1d5db', fontSize: 12 }}>{value}</span>
                )}
              />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(v: number) => [v, 'Employees']}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Issues */}
      {s.top_issues && s.top_issues.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Top Issues</h2>
          <div className="space-y-2">
            {s.top_issues.slice(0, 5).map((issue, i) => (
              <div
                key={i}
                className="flex items-center gap-3 bg-gray-800 rounded-lg px-3 py-2.5"
              >
                <IssueTypeIcon type={issue.issue_type} />
                <span className="text-sm text-gray-200 flex-1">{issue.description}</span>
                <span className="badge bg-red-900 text-red-200">{issue.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Escalations */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Recent Escalations</h2>
        {recentEscalations.length === 0 ? (
          <div className="text-center text-gray-500 py-6 flex flex-col items-center gap-2">
            <CheckCircle size={24} className="text-green-500" />
            <span>No open escalations</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Type</th>
                  <th className="th">Employee ID</th>
                  <th className="th">Days Overdue</th>
                  <th className="th">Message</th>
                  <th className="th">Status</th>
                  <th className="th">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {recentEscalations.map((e) => (
                  <tr key={e.id} className="hover:bg-gray-800/50">
                    <td className="td">
                      <EscalationTypeBadge type={e.escalation_type} />
                    </td>
                    <td className="td font-mono text-xs text-gray-400">{e.employee_id}</td>
                    <td className="td">
                      {e.days_overdue != null ? (
                        <span className="text-red-400 font-semibold">{e.days_overdue}d</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="td text-gray-400 max-w-xs truncate">{e.message ?? '—'}</td>
                    <td className="td">
                      <span className="badge bg-amber-900 text-amber-200">
                        <Clock size={10} /> Open
                      </span>
                    </td>
                    <td className="td text-gray-400 text-xs">
                      {new Date(e.escalated_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
