import { useQuery } from '@tanstack/react-query';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  AlertTriangle,
  Clock,
  TrendingUp,
  DollarSign,
  CreditCard,
  Users,
  Cloud,
  Play,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import {
  getFindingsSummary,
  getFindings,
  getFindingsTrend,
  getRules,
  getTenantConfig,
} from '../api';
import type { Severity, FindingStatus } from '../types';

interface Props {
  tenantId: string;
  onNavigate?: (tab: string) => void;
}

function severityColor(s: Severity): string {
  switch (s) {
    case 'critical': return 'bg-red-700 text-white';
    case 'high': return 'bg-orange-600 text-white';
    case 'medium': return 'bg-yellow-600 text-white';
    case 'low': return 'bg-blue-500 text-white';
    default: return 'bg-gray-600 text-white';
  }
}

function statusColor(s: FindingStatus): string {
  switch (s) {
    case 'open': return 'bg-red-900/40 text-red-300 border border-red-700';
    case 'acknowledged': return 'bg-yellow-900/40 text-yellow-300 border border-yellow-700';
    case 'resolved': return 'bg-green-900/40 text-green-300 border border-green-700';
    case 'false_positive': return 'bg-gray-700 text-gray-300 border border-gray-600';
  }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const CATEGORY_META = [
  { key: 'payroll', label: 'Payroll', icon: DollarSign, tab: 'payroll', color: 'text-green-400', typePrefix: 'payroll' },
  { key: 'ap', label: 'Accounts Payable', icon: TrendingUp, tab: 'invoices', color: 'text-blue-400', typePrefix: 'duplicate_invoice,invoice_split' },
  { key: 'card', label: 'Card Spend', icon: CreditCard, tab: 'invoices', color: 'text-purple-400', typePrefix: 'card' },
  { key: 'sod', label: 'Seg. of Duties', icon: Users, tab: 'sod', color: 'text-yellow-400', typePrefix: 'sod' },
  { key: 'cloud', label: 'Cloud Config', icon: Cloud, tab: 'cloud', color: 'text-cyan-400', typePrefix: 'cloud' },
];

export default function MonitoringDashboard({ tenantId, onNavigate }: Props) {
  const { data: summary } = useQuery({
    queryKey: ['findings-summary', tenantId],
    queryFn: () => getFindingsSummary(tenantId),
  });

  const { data: trend } = useQuery({
    queryKey: ['findings-trend', tenantId],
    queryFn: () => getFindingsTrend(tenantId, 30),
  });

  const { data: recentFindings } = useQuery({
    queryKey: ['findings-recent', tenantId],
    queryFn: () => getFindings(tenantId, { severity: 'critical,high', limit: 10 }),
  });

  const { data: rules } = useQuery({
    queryKey: ['rules', tenantId],
    queryFn: () => getRules(tenantId),
  });

  const { data: tenantConfig } = useQuery({
    queryKey: ['tenant-config', tenantId],
    queryFn: () => getTenantConfig(tenantId),
  });

  const { data: allFindings } = useQuery({
    queryKey: ['findings-all', tenantId],
    queryFn: () => getFindings(tenantId, { limit: 500 }),
  });

  const countByCategory = (prefix: string) => {
    if (!allFindings) return 0;
    return allFindings.filter(f =>
      prefix.split(',').some(p => f.finding_type.startsWith(p))
    ).length;
  };

  const trendUp = summary && trend && trend.length >= 2
    ? (trend[trend.length - 1].critical + trend[trend.length - 1].high) >
      (trend[trend.length - 2].critical + trend[trend.length - 2].high)
    : false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Continuous Monitoring</h1>
          <p className="text-gray-400 text-sm mt-1">Real-time audit intelligence across all risk domains</p>
        </div>
        <button
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          onClick={() => onNavigate?.('payroll')}
        >
          <Play size={14} />
          Run All Checks
        </button>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {/* Total Findings */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Total Findings</p>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-white">{summary?.total ?? '--'}</span>
            {trendUp
              ? <ArrowUpRight size={18} className="text-red-400 mb-1" />
              : <ArrowDownRight size={18} className="text-green-400 mb-1" />
            }
          </div>
        </div>

        {/* Critical */}
        <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
          <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Critical</p>
          <div className="flex items-center gap-2">
            <span className="text-3xl font-bold text-red-400">{summary?.by_severity.critical ?? '--'}</span>
            <AlertTriangle size={20} className="text-red-500" />
          </div>
        </div>

        {/* High */}
        <div className="bg-gray-800 rounded-xl p-4 border border-orange-900/50">
          <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">High</p>
          <span className="text-3xl font-bold text-orange-400">{summary?.by_severity.high ?? '--'}</span>
        </div>

        {/* Open Items */}
        <div className="bg-gray-800 rounded-xl p-4 border border-blue-900/50">
          <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Open Items</p>
          <span className="text-3xl font-bold text-blue-400">{summary?.open_count ?? '--'}</span>
        </div>

        {/* Last Run */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Last Run</p>
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-gray-400" />
            <span className="text-sm text-gray-200">
              {summary?.last_run_at ? relativeTime(summary.last_run_at) : 'Never'}
            </span>
          </div>
        </div>
      </div>

      {/* Trend Chart */}
      <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
        <h2 className="text-base font-semibold text-white mb-4">30-Day Finding Trend</h2>
        {trend && trend.length > 0 ? (
          <ResponsiveContainer width="100%" height={256}>
            <AreaChart data={trend} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="gcrit" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="ghigh" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gmed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} tickLine={false} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#e5e7eb' }}
              />
              <Legend wrapperStyle={{ color: '#9ca3af', fontSize: 12 }} />
              <Area type="monotone" dataKey="critical" stackId="1" stroke="#ef4444" fill="url(#gcrit)" name="Critical" />
              <Area type="monotone" dataKey="high" stackId="1" stroke="#f97316" fill="url(#ghigh)" name="High" />
              <Area type="monotone" dataKey="medium" stackId="1" stroke="#eab308" fill="url(#gmed)" name="Medium" />
              <Area type="monotone" dataKey="low" stackId="1" stroke="#3b82f6" fill="url(#glow)" name="Low" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-500">No trend data available</div>
        )}
      </div>

      {/* Category Breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {CATEGORY_META.map(cat => {
          const Icon = cat.icon;
          const count = countByCategory(cat.typePrefix);
          return (
            <button
              key={cat.key}
              onClick={() => onNavigate?.(cat.tab)}
              className="bg-gray-800 hover:bg-gray-750 rounded-xl p-4 border border-gray-700 text-left transition-colors group"
            >
              <Icon size={24} className={`${cat.color} mb-3 group-hover:scale-110 transition-transform`} />
              <p className="text-2xl font-bold text-white">{count}</p>
              <p className="text-gray-400 text-xs mt-1">{cat.label}</p>
              <div className="mt-2 h-1 rounded bg-gray-700 overflow-hidden">
                <div
                  className="h-full rounded bg-current"
                  style={{
                    width: summary?.total ? `${Math.min(100, (count / summary.total) * 100)}%` : '0%',
                    color: cat.color.replace('text-', ''),
                  }}
                />
              </div>
            </button>
          );
        })}
      </div>

      {/* Recent Critical Findings */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">Recent Critical &amp; High Findings</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left px-5 py-3 text-gray-400 font-medium w-24">Severity</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Title</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Entity</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium w-28">Detected</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium w-28">Status</th>
              </tr>
            </thead>
            <tbody>
              {recentFindings && recentFindings.length > 0 ? (
                recentFindings.map(f => (
                  <tr key={f.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${severityColor(f.severity)}`}>
                        {f.severity}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-200 font-medium max-w-xs">
                      <span className="line-clamp-2">{f.title}</span>
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs">
                      {f.entity_type && <span className="text-gray-500">{f.entity_type}: </span>}
                      {f.entity_name ?? f.entity_id ?? '—'}
                    </td>
                    <td className="px-5 py-3 text-gray-400">{relativeTime(f.detected_at)}</td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${statusColor(f.status)}`}>
                        {f.status.replace('_', ' ')}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-gray-500">No critical or high findings</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Monitoring Rules Status Strip */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">Monitoring Rules Status</h2>
        </div>
        <div className="p-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {rules ? rules.map(rule => {
            const cfg = tenantConfig?.find(c => c.rule_key === rule.rule_key);
            const enabled = cfg?.is_enabled ?? rule.is_active;
            return (
              <div key={rule.id} className="flex items-start gap-3 p-3 bg-gray-750 rounded-lg border border-gray-700">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 font-medium truncate">{rule.display_name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {cfg?.last_run_at ? `Last: ${relativeTime(cfg.last_run_at)}` : 'Never run'}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-semibold uppercase ${severityColor(rule.severity_default)}`}>
                    {rule.severity_default.charAt(0)}
                  </span>
                  <div className={`w-8 h-4 rounded-full transition-colors ${enabled ? 'bg-green-600' : 'bg-gray-600'}`}>
                    <div className={`w-3 h-3 rounded-full bg-white mt-0.5 transition-transform ${enabled ? 'translate-x-4 ml-0.5' : 'translate-x-0.5'}`} />
                  </div>
                </div>
              </div>
            );
          }) : (
            <div className="col-span-3 text-center text-gray-500 py-4">Loading rules...</div>
          )}
        </div>
      </div>
    </div>
  );
}
