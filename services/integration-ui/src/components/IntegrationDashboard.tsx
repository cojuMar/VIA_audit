import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  PauseCircle,
  PlayCircle,
  Settings,
  Trash2,
  Plus,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
} from 'lucide-react';
import {
  listIntegrations,
  getDashboardSummary,
  triggerSync,
  updateIntegration,
  deleteIntegration,
} from '../api';
import type { TenantIntegration, ConnectorCategory } from '../types';

const CATEGORY_COLORS: Record<ConnectorCategory, string> = {
  erp: 'bg-blue-600',
  hris: 'bg-purple-600',
  itsm: 'bg-orange-600',
  cloud: 'bg-cyan-600',
  identity: 'bg-indigo-600',
  security: 'bg-red-600',
  collaboration: 'bg-green-600',
  source_control: 'bg-gray-600',
  crm: 'bg-yellow-600',
  custom: 'bg-slate-600',
};

const CATEGORY_LABELS: Record<ConnectorCategory, string> = {
  erp: 'ERP',
  hris: 'HRIS',
  itsm: 'ITSM',
  cloud: 'Cloud',
  identity: 'Identity',
  security: 'Security',
  collaboration: 'Collaboration',
  source_control: 'Source Control',
  crm: 'CRM',
  custom: 'Custom',
};

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

function StatusBadge({ status }: { status: TenantIntegration['status'] }) {
  const cfg = {
    active: 'bg-green-500/20 text-green-400 border border-green-500/30',
    error: 'bg-red-500/20 text-red-400 border border-red-500/30',
    paused: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
    pending: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
    disabled: 'bg-gray-700/40 text-gray-500 border border-gray-600/30',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg[status]}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function SyncStatusIcon({ s }: { s: 'success' | 'partial' | 'failed' | null }) {
  if (!s) return null;
  if (s === 'success') return <CheckCircle size={14} className="text-green-400 shrink-0" />;
  if (s === 'partial') return <AlertTriangle size={14} className="text-amber-400 shrink-0" />;
  return <XCircle size={14} className="text-red-400 shrink-0" />;
}

function ConnectorAvatar({
  name,
  category,
}: {
  name: string;
  category?: ConnectorCategory;
}) {
  const bg = category ? CATEGORY_COLORS[category] : 'bg-gray-600';
  const initials = name.slice(0, 2).toUpperCase();
  return (
    <div
      className={`${bg} w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold text-sm shrink-0`}
    >
      {initials}
    </div>
  );
}

interface Props {
  tenantId: string;
  onSelectIntegration: (integration: TenantIntegration) => void;
  onAddIntegration: () => void;
}

export default function IntegrationDashboard({
  tenantId,
  onSelectIntegration,
  onAddIntegration,
}: Props) {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  const { data: integrations = [], isLoading } = useQuery({
    queryKey: ['integrations', tenantId],
    queryFn: () => listIntegrations(tenantId),
    refetchInterval: 30000,
  });

  const { data: summary } = useQuery({
    queryKey: ['dashboard-summary', tenantId],
    queryFn: () => getDashboardSummary(tenantId),
    refetchInterval: 30000,
  });

  const syncMutation = useMutation({
    mutationFn: (id: string) => triggerSync(tenantId, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['integrations', tenantId] });
      void qc.invalidateQueries({ queryKey: ['dashboard-summary', tenantId] });
      setSyncingId(null);
    },
    onError: () => setSyncingId(null),
  });

  const pauseMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateIntegration(tenantId, id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations', tenantId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteIntegration(tenantId, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['integrations', tenantId] });
      void qc.invalidateQueries({ queryKey: ['dashboard-summary', tenantId] });
    },
  });

  const filtered = statusFilter
    ? integrations.filter((i) => i.status === statusFilter)
    : integrations;

  const byStatus = summary?.by_status ?? {};
  const byCategory = summary?.by_category ?? {};

  const metricCards = [
    {
      label: 'Total Integrations',
      value: summary?.total ?? integrations.length,
      color: 'text-white',
      onClick: () => setStatusFilter(null),
      active: statusFilter === null,
    },
    {
      label: 'Active',
      value: byStatus['active'] ?? integrations.filter((i) => i.status === 'active').length,
      color: 'text-green-400',
      onClick: () => setStatusFilter(statusFilter === 'active' ? null : 'active'),
      active: statusFilter === 'active',
    },
    {
      label: 'With Errors',
      value: byStatus['error'] ?? integrations.filter((i) => i.status === 'error').length,
      color: 'text-red-400',
      onClick: () => setStatusFilter(statusFilter === 'error' ? null : 'error'),
      active: statusFilter === 'error',
    },
    {
      label: 'Paused',
      value: byStatus['paused'] ?? integrations.filter((i) => i.status === 'paused').length,
      color: 'text-yellow-400',
      onClick: () => setStatusFilter(statusFilter === 'paused' ? null : 'paused'),
      active: statusFilter === 'paused',
    },
    {
      label: 'Last Sync Errors',
      value: summary?.last_sync_errors ?? integrations.filter((i) => i.last_sync_status === 'failed').length,
      color: 'text-orange-400',
      onClick: () => {},
      active: false,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Integration Hub</h1>
          <p className="text-gray-400 text-sm mt-0.5">Manage your enterprise data connectors</p>
        </div>
        <button
          onClick={onAddIntegration}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Add Integration
        </button>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
        {metricCards.map((card) => (
          <button
            key={card.label}
            onClick={card.onClick}
            className={`bg-gray-900 border rounded-xl p-4 text-left transition-all ${
              card.active
                ? 'border-indigo-500 ring-1 ring-indigo-500'
                : 'border-gray-800 hover:border-gray-700'
            }`}
          >
            <div className={`text-2xl font-bold ${card.color}`}>{card.value}</div>
            <div className="text-xs text-gray-400 mt-1">{card.label}</div>
          </button>
        ))}
      </div>

      {/* Category breakdown */}
      {Object.keys(byCategory).length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6">
          <h2 className="text-sm font-medium text-gray-300 mb-3">By Category</h2>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(byCategory) as ConnectorCategory[]).map((cat) => (
              <div
                key={cat}
                className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-1.5"
              >
                <div className={`w-2 h-2 rounded-full ${CATEGORY_COLORS[cat] ?? 'bg-gray-500'}`} />
                <span className="text-xs text-gray-300">{CATEGORY_LABELS[cat] ?? cat}</span>
                <span className="text-xs font-bold text-white">{byCategory[cat]}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Integration grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <RefreshCw size={20} className="animate-spin mr-2" />
          Loading integrations…
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mb-4">
            <Plus size={28} className="text-gray-500" />
          </div>
          <p className="text-gray-300 font-medium mb-1">
            {statusFilter ? 'No integrations with this status.' : 'No integrations yet.'}
          </p>
          <p className="text-gray-500 text-sm">
            {statusFilter
              ? 'Try a different filter.'
              : 'Add your first connector to start syncing data.'}
          </p>
          {!statusFilter && (
            <button
              onClick={onAddIntegration}
              className="mt-4 flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} />
              Add Integration
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((integration) => (
            <IntegrationCard
              key={integration.id}
              integration={integration}
              syncing={syncingId === integration.id}
              onOpen={() => onSelectIntegration(integration)}
              onSync={() => {
                setSyncingId(integration.id);
                syncMutation.mutate(integration.id);
              }}
              onTogglePause={() => {
                const nextStatus =
                  integration.status === 'paused' ? 'active' : 'paused';
                pauseMutation.mutate({ id: integration.id, status: nextStatus });
              }}
              onDelete={() => {
                if (confirm(`Delete "${integration.integration_name}"? This cannot be undone.`)) {
                  deleteMutation.mutate(integration.id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function IntegrationCard({
  integration,
  syncing,
  onOpen,
  onSync,
  onTogglePause,
  onDelete,
}: {
  integration: TenantIntegration;
  syncing: boolean;
  onOpen: () => void;
  onSync: () => void;
  onTogglePause: () => void;
  onDelete: () => void;
}) {
  const connector = integration.connector;
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-3 hover:border-gray-700 transition-colors">
      {/* Top row */}
      <div className="flex items-start gap-3">
        <ConnectorAvatar
          name={connector?.display_name ?? integration.integration_name}
          category={connector?.category}
        />
        <div className="flex-1 min-w-0">
          <button
            onClick={onOpen}
            className="text-sm font-semibold text-white hover:text-indigo-400 transition-colors text-left leading-tight truncate block w-full"
          >
            {integration.integration_name}
          </button>
          {connector && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{connector.display_name}</p>
          )}
        </div>
        <StatusBadge status={integration.status} />
      </div>

      {/* Last sync row */}
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <Clock size={12} className="shrink-0" />
        <span>{relativeTime(integration.last_sync_at)}</span>
        {integration.last_sync_record_count != null && (
          <span className="text-gray-500">· {integration.last_sync_record_count.toLocaleString()} records</span>
        )}
        <div className="ml-auto">
          <SyncStatusIcon s={integration.last_sync_status} />
        </div>
      </div>

      {/* Error message */}
      {integration.status === 'error' && integration.error_message && (
        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 truncate">
          {integration.error_message}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 pt-1 border-t border-gray-800">
        <button
          onClick={onSync}
          disabled={syncing}
          title="Sync Now"
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-indigo-400 disabled:opacity-50 px-2 py-1 rounded hover:bg-gray-800 transition-colors"
        >
          <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
          Sync
        </button>
        <button
          onClick={onTogglePause}
          title={integration.status === 'paused' ? 'Resume' : 'Pause'}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-yellow-400 px-2 py-1 rounded hover:bg-gray-800 transition-colors"
        >
          {integration.status === 'paused' ? (
            <PlayCircle size={13} />
          ) : (
            <PauseCircle size={13} />
          )}
          {integration.status === 'paused' ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={onOpen}
          title="Settings"
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded hover:bg-gray-800 transition-colors"
        >
          <Settings size={13} />
          Settings
        </button>
        <button
          onClick={onDelete}
          title="Delete"
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-400 px-2 py-1 rounded hover:bg-gray-800 transition-colors ml-auto"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}
