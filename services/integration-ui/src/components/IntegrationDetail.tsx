import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  ArrowLeft,
  RefreshCw,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  type LucideIcon,
} from 'lucide-react';
import {
  listSyncLogs,
  listRecords,
  getFieldMappingTemplates,
  getIntegrationStats,
  triggerSync,
  updateIntegration,
  deleteIntegration,
} from '../api';
import type { TenantIntegration, SyncLog } from '../types';

interface Props {
  integration: TenantIntegration;
  tenantId: string;
  onBack: () => void;
}

const TABS = ['Overview', 'Sync History', 'Records', 'Field Mappings', 'Settings'] as const;
type Tab = (typeof TABS)[number];

function relativeTime(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function duration(start: string, end: string | null): string {
  if (!end) return '—';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function SyncStatusBadge({ status }: { status: SyncLog['status'] }) {
  const cfg: Record<SyncLog['status'], { cls: string; label: string; Icon?: LucideIcon }> = {
    success: { cls: 'bg-green-500/20 text-green-400 border border-green-500/30', label: 'Success' },
    partial: { cls: 'bg-amber-500/20 text-amber-400 border border-amber-500/30', label: 'Partial' },
    failed: { cls: 'bg-red-500/20 text-red-400 border border-red-500/30', label: 'Failed' },
    running: { cls: 'bg-blue-500/20 text-blue-400 border border-blue-500/30', label: 'Running', Icon: Loader2 },
  };
  const { cls, label, Icon } = cfg[status];
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {Icon && <Icon size={11} className="animate-spin" />}
      {label}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="p-1 text-gray-500 hover:text-white transition-colors"
    >
      {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
    </button>
  );
}

const STATUS_COLORS: Record<SyncLog['status'], string> = {
  success: '#22c55e',
  partial: '#f59e0b',
  failed: '#ef4444',
  running: '#3b82f6',
};

// ----- Tab: Overview -----
function OverviewTab({ integration, tenantId }: { integration: TenantIntegration; tenantId: string }) {
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);

  const { data: stats } = useQuery({
    queryKey: ['integration-stats', tenantId, integration.id],
    queryFn: () => getIntegrationStats(tenantId, integration.id),
  });

  const { data: logs = [] } = useQuery({
    queryKey: ['sync-logs', tenantId, integration.id],
    queryFn: () => listSyncLogs(tenantId, integration.id, { limit: 14 }),
  });

  const syncMutation = useMutation({
    mutationFn: () => triggerSync(tenantId, integration.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['sync-logs', tenantId, integration.id] });
      void qc.invalidateQueries({ queryKey: ['integration-stats', tenantId, integration.id] });
      setSyncing(false);
    },
    onError: () => setSyncing(false),
  });

  const statusBannerCls = {
    active: 'bg-green-500/10 border-green-500/30 text-green-400',
    error: 'bg-red-500/10 border-red-500/30 text-red-400',
    paused: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
    pending: 'bg-gray-500/10 border-gray-500/30 text-gray-400',
    disabled: 'bg-gray-700/20 border-gray-600/30 text-gray-500',
  }[integration.status];

  const chartData = [...logs].reverse().map((l, i) => ({
    name: `#${i + 1}`,
    records: l.records_processed ?? 0,
    status: l.status,
  }));

  return (
    <div className="space-y-4">
      {/* Status banner */}
      <div className={`border rounded-xl p-3 flex items-center justify-between ${statusBannerCls}`}>
        <span className="text-sm font-medium capitalize">Status: {integration.status}</span>
        <button
          onClick={() => { setSyncing(true); syncMutation.mutate(); }}
          disabled={syncing}
          className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
        >
          <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
          Sync Now
        </button>
      </div>

      {/* Stats grid */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total Records', value: stats.total_records.toLocaleString(), color: 'text-white' },
            { label: 'Success Rate', value: `${stats.success_rate_pct.toFixed(1)}%`, color: 'text-green-400' },
            { label: 'Total Syncs', value: stats.total_syncs.toLocaleString(), color: 'text-blue-400' },
            { label: 'Syncs This Week', value: stats.last_7_days_syncs.toLocaleString(), color: 'text-indigo-400' },
          ].map((s) => (
            <div key={s.label} className="bg-gray-800 border border-gray-700 rounded-xl p-3">
              <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-xs text-gray-400 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Last sync card */}
      {logs[0] && (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
          <p className="text-xs font-medium text-gray-400 mb-2">Last Sync</p>
          <div className="flex items-center gap-3">
            <SyncStatusBadge status={logs[0].status} />
            <span className="text-sm text-white">{relativeTime(logs[0].started_at)}</span>
            <span className="text-xs text-gray-500">·</span>
            <span className="text-xs text-gray-400">Duration: {duration(logs[0].started_at, logs[0].completed_at)}</span>
            {logs[0].records_processed != null && (
              <>
                <span className="text-xs text-gray-500">·</span>
                <span className="text-xs text-gray-400">{logs[0].records_processed.toLocaleString()} records</span>
              </>
            )}
          </div>
          {logs[0].error_summary && (
            <p className="text-xs text-red-400 mt-2">{logs[0].error_summary}</p>
          )}
        </div>
      )}

      {/* Mini chart */}
      {chartData.length > 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
          <p className="text-xs font-medium text-gray-400 mb-3">Last {chartData.length} Syncs — Records Processed</p>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={chartData} barCategoryGap="20%">
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} axisLine={false} tickLine={false} width={35} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#9ca3af' }}
                itemStyle={{ color: '#e5e7eb' }}
              />
              <Bar dataKey="records" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell key={idx} fill={STATUS_COLORS[entry.status as SyncLog['status']] ?? '#6b7280'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ----- Tab: Sync History -----
function SyncHistoryTab({ integration, tenantId }: { integration: TenantIntegration; tenantId: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['sync-logs', tenantId, integration.id],
    queryFn: () => listSyncLogs(tenantId, integration.id, { limit: 50 }),
  });

  if (isLoading) return <div className="text-sm text-gray-500 py-8 text-center">Loading…</div>;
  if (logs.length === 0) return <div className="text-sm text-gray-500 py-8 text-center">No sync history yet.</div>;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-700">
            <th className="text-left px-4 py-3 text-gray-400 font-medium">Started</th>
            <th className="text-left px-4 py-3 text-gray-400 font-medium">Type</th>
            <th className="text-left px-4 py-3 text-gray-400 font-medium">Duration</th>
            <th className="text-left px-4 py-3 text-gray-400 font-medium">Status</th>
            <th className="text-right px-4 py-3 text-gray-400 font-medium">Fetched</th>
            <th className="text-right px-4 py-3 text-gray-400 font-medium">Processed</th>
            <th className="text-left px-4 py-3 text-gray-400 font-medium">Data Types</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <>
              <tr
                key={log.id}
                onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 text-gray-300 whitespace-nowrap">{relativeTime(log.started_at)}</td>
                <td className="px-4 py-3 text-gray-400 capitalize">{log.sync_type}</td>
                <td className="px-4 py-3 text-gray-400">{duration(log.started_at, log.completed_at)}</td>
                <td className="px-4 py-3"><SyncStatusBadge status={log.status} /></td>
                <td className="px-4 py-3 text-gray-300 text-right">{log.records_fetched?.toLocaleString() ?? '—'}</td>
                <td className="px-4 py-3 text-gray-300 text-right">{log.records_processed?.toLocaleString() ?? '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {log.data_types_synced.slice(0, 2).map((dt) => (
                      <span key={dt} className="bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded-full">{dt}</span>
                    ))}
                    {log.data_types_synced.length > 2 && (
                      <span className="text-gray-500">+{log.data_types_synced.length - 2}</span>
                    )}
                  </div>
                </td>
              </tr>
              {expanded === log.id && log.error_summary && (
                <tr key={`${log.id}-expanded`} className="border-b border-gray-700/50 bg-gray-900/50">
                  <td colSpan={7} className="px-4 py-3">
                    <p className="text-xs text-red-400 font-mono">{log.error_summary}</p>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ----- Tab: Records -----
function RecordsTab({ integration, tenantId }: { integration: TenantIntegration; tenantId: string }) {
  const [dataType, setDataType] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: records = [], isLoading } = useQuery({
    queryKey: ['records', tenantId, integration.id, dataType],
    queryFn: () => listRecords(tenantId, integration.id, { data_type: dataType || undefined, limit: 50 }),
  });

  const dataTypes = Array.from(new Set(records.map((r) => r.data_type)));

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <select
          value={dataType}
          onChange={(e) => setDataType(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
        >
          <option value="">All types</option>
          {(integration.connector?.supported_data_types ?? dataTypes).map((dt) => (
            <option key={dt} value={dt}>{dt}</option>
          ))}
        </select>
        <span className="text-xs text-gray-500">{records.length} records</span>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading…</div>
      ) : records.length === 0 ? (
        <div className="text-sm text-gray-500 py-8 text-center">No records found.</div>
      ) : (
        <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left px-4 py-3 text-gray-400 font-medium">Data Type</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">Source ID</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">System</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">Ingested</th>
                <th className="w-8"></th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec) => (
                <>
                  <tr
                    key={rec.id}
                    onClick={() => setExpanded(expanded === rec.id ? null : rec.id)}
                    className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-gray-300">{rec.data_type}</td>
                    <td className="px-4 py-3 text-gray-400 font-mono truncate max-w-[120px]">{rec.source_record_id}</td>
                    <td className="px-4 py-3 text-gray-400">{rec.source_system}</td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{relativeTime(rec.ingested_at)}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {expanded === rec.id ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    </td>
                  </tr>
                  {expanded === rec.id && (
                    <tr key={`${rec.id}-expanded`} className="border-b border-gray-700/50 bg-gray-900/50">
                      <td colSpan={5} className="px-4 py-3">
                        <pre className="text-xs text-gray-300 font-mono overflow-x-auto scrollbar-thin whitespace-pre-wrap break-all">
                          {JSON.stringify(rec.normalized_data, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ----- Tab: Field Mappings -----
function FieldMappingsTab({ integration, tenantId }: { integration: TenantIntegration; tenantId: string }) {
  const [openType, setOpenType] = useState<string | null>(null);
  const connector = integration.connector;
  const dataTypes = connector?.supported_data_types ?? [];

  return (
    <div className="space-y-2">
      {dataTypes.length === 0 ? (
        <p className="text-sm text-gray-500 py-8 text-center">No data types configured.</p>
      ) : (
        dataTypes.map((dt) => (
          <FieldMappingAccordion
            key={dt}
            dataType={dt}
            connectorKey={connector!.connector_key}
            tenantId={tenantId}
            open={openType === dt}
            onToggle={() => setOpenType(openType === dt ? null : dt)}
          />
        ))
      )}
    </div>
  );
}

function FieldMappingAccordion({
  dataType,
  connectorKey,
  tenantId,
  open,
  onToggle,
}: {
  dataType: string;
  connectorKey: string;
  tenantId: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { data: templates = [] } = useQuery({
    queryKey: ['field-mappings', connectorKey, dataType],
    queryFn: () => getFieldMappingTemplates(tenantId, connectorKey, dataType),
    enabled: open,
  });

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-white hover:bg-gray-700/30 transition-colors"
      >
        <span className="capitalize">{dataType.replace(/_/g, ' ')}</span>
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      {open && (
        <div className="border-t border-gray-700">
          {templates.length === 0 ? (
            <p className="text-xs text-gray-500 px-4 py-3">No field mappings defined.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700/50">
                  <th className="text-left px-4 py-2 text-gray-400 font-medium">Source Field</th>
                  <th className="px-2 py-2 text-gray-600">→</th>
                  <th className="text-left px-4 py-2 text-gray-400 font-medium">Target Field</th>
                  <th className="text-left px-4 py-2 text-gray-400 font-medium">Transform</th>
                  <th className="text-center px-4 py-2 text-gray-400 font-medium">Required</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((t, i) => (
                  <tr key={i} className="border-b border-gray-700/30 last:border-0">
                    <td className="px-4 py-2 text-gray-300 font-mono">{t.source_field}</td>
                    <td className="px-2 py-2 text-gray-600 text-center">→</td>
                    <td className="px-4 py-2 text-gray-300 font-mono">{t.target_field}</td>
                    <td className="px-4 py-2">
                      {t.transform_fn ? (
                        <span className="bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded font-mono">
                          {t.transform_fn}
                        </span>
                      ) : (
                        <span className="text-gray-700">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {t.is_required ? (
                        <CheckCircle size={13} className="text-green-400 inline" />
                      ) : (
                        <span className="text-gray-700">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ----- Tab: Settings -----
function SettingsTab({ integration, tenantId, onBack }: { integration: TenantIntegration; tenantId: string; onBack: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(integration.integration_name);
  const [schedule, setSchedule] = useState(integration.sync_schedule);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const PRESETS = [
    { label: 'Every 15 min', value: '*/15 * * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Daily', value: '0 0 * * *' },
    { label: 'Weekly', value: '0 0 * * 0' },
  ];

  const updateMutation = useMutation({
    mutationFn: (payload: Parameters<typeof updateIntegration>[2]) =>
      updateIntegration(tenantId, integration.id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['integrations', tenantId] });
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    },
    onError: () => setSaving(false),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteIntegration(tenantId, integration.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['integrations', tenantId] });
      onBack();
    },
  });

  return (
    <div className="space-y-6">
      {/* General */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-semibold text-white">General</h3>
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-1">Integration Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-1">Sync Schedule</label>
          <select
            value={PRESETS.some((p) => p.value === schedule) ? schedule : 'custom'}
            onChange={(e) => setSchedule(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
          >
            {PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
            <option value="custom">Custom cron…</option>
          </select>
          {!PRESETS.some((p) => p.value === schedule) && (
            <input
              type="text"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
              placeholder="* * * * *"
              className="mt-2 w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-indigo-500 transition-colors"
            />
          )}
        </div>
        <button
          onClick={() => { setSaving(true); updateMutation.mutate({ integration_name: name, sync_schedule: schedule }); }}
          disabled={saving}
          className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {saving ? 'Saving…' : saved ? <><Check size={14} /> Saved</> : 'Save Changes'}
        </button>
      </div>

      {/* Webhook URL (if applicable) */}
      {integration.webhook_url && (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">Webhook</h3>
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">Webhook URL</label>
            <div className="flex items-center bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 gap-2">
              <span className="text-sm text-gray-400 flex-1 font-mono truncate">{integration.webhook_url}</span>
              <CopyButton text={integration.webhook_url} />
            </div>
          </div>
        </div>
      )}

      {/* Danger zone */}
      <div className="bg-red-500/5 border border-red-500/30 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-semibold text-red-400">Danger Zone</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => updateMutation.mutate({ status: integration.status === 'paused' ? 'active' : 'paused' })}
            className="flex items-center gap-1.5 bg-yellow-500/10 border border-yellow-500/30 hover:bg-yellow-500/20 text-yellow-400 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {integration.status === 'paused' ? 'Resume Integration' : 'Pause Integration'}
          </button>
          <button
            onClick={() => {
              if (confirm(`Permanently delete "${integration.integration_name}"? This cannot be undone.`)) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="flex items-center gap-1.5 bg-red-500/10 border border-red-500/30 hover:bg-red-500/20 text-red-400 text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            <XCircle size={14} />
            {deleteMutation.isPending ? 'Deleting…' : 'Delete Integration'}
          </button>
        </div>
        <p className="text-xs text-gray-500">
          Deleting this integration will permanently remove all sync history and records. This action cannot be undone.
        </p>
      </div>
    </div>
  );
}

// ----- Main Component -----
export default function IntegrationDetail({ integration, tenantId, onBack }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('Overview');

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors px-2 py-1.5 rounded-lg hover:bg-gray-800"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="bg-indigo-600 w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold text-sm shrink-0">
            {(integration.connector?.display_name ?? integration.integration_name).slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <h1 className="text-lg font-bold text-white truncate">{integration.integration_name}</h1>
            {integration.connector && (
              <p className="text-xs text-gray-400">{integration.connector.display_name}</p>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800 mb-5 overflow-x-auto scrollbar-thin">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`shrink-0 text-sm px-4 py-2 border-b-2 font-medium transition-colors ${
              activeTab === tab
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'Overview' && <OverviewTab integration={integration} tenantId={tenantId} />}
      {activeTab === 'Sync History' && <SyncHistoryTab integration={integration} tenantId={tenantId} />}
      {activeTab === 'Records' && <RecordsTab integration={integration} tenantId={tenantId} />}
      {activeTab === 'Field Mappings' && <FieldMappingsTab integration={integration} tenantId={tenantId} />}
      {activeTab === 'Settings' && <SettingsTab integration={integration} tenantId={tenantId} onBack={onBack} />}
    </div>
  );
}
