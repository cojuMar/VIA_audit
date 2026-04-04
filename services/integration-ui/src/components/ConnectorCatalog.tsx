import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, Search } from 'lucide-react';
import { listConnectors } from '../api';
import type { ConnectorDefinition, ConnectorCategory, AuthType } from '../types';

interface Props {
  tenantId: string;
  onSelect: (connector: ConnectorDefinition) => void;
  onClose: () => void;
}

const CATEGORY_TABS: { key: ConnectorCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'erp', label: 'ERP' },
  { key: 'hris', label: 'HRIS' },
  { key: 'itsm', label: 'ITSM' },
  { key: 'cloud', label: 'Cloud' },
  { key: 'identity', label: 'Identity' },
  { key: 'security', label: 'Security' },
  { key: 'collaboration', label: 'Collaboration' },
  { key: 'source_control', label: 'Source Control' },
  { key: 'crm', label: 'CRM' },
  { key: 'custom', label: 'Custom' },
];

const CATEGORY_BADGE: Record<ConnectorCategory, string> = {
  erp: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  hris: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  itsm: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
  cloud: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30',
  identity: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  security: 'bg-red-500/20 text-red-400 border border-red-500/30',
  collaboration: 'bg-green-500/20 text-green-400 border border-green-500/30',
  source_control: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  crm: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  custom: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
};

const AUTH_BADGE: Record<AuthType, string> = {
  oauth2: 'bg-green-500/20 text-green-400 border border-green-500/30',
  api_key: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  basic: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  webhook: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  service_account: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  none: 'bg-gray-600/20 text-gray-500 border border-gray-600/30',
};

const AUTH_LABELS: Record<AuthType, string> = {
  oauth2: 'OAuth 2.0',
  api_key: 'API Key',
  basic: 'Basic Auth',
  webhook: 'Webhook',
  service_account: 'Service Account',
  none: 'None',
};

const CATEGORY_AVATAR_BG: Record<ConnectorCategory, string> = {
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

export default function ConnectorCatalog({ tenantId, onSelect, onClose }: Props) {
  const [activeCategory, setActiveCategory] = useState<ConnectorCategory | 'all'>('all');
  const [search, setSearch] = useState('');

  const { data: connectors = [], isLoading } = useQuery({
    queryKey: ['connectors', tenantId],
    queryFn: () => listConnectors(tenantId),
  });

  const filtered = connectors.filter((c) => {
    if (!c.is_active) return false;
    if (activeCategory !== 'all' && c.category !== activeCategory) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        c.display_name.toLowerCase().includes(q) ||
        (c.description?.toLowerCase().includes(q) ?? false) ||
        c.category.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-lg font-bold text-white">Connector Catalog</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {connectors.filter((c) => c.is_active).length} connectors available
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800"
          >
            <X size={20} />
          </button>
        </div>

        {/* Search */}
        <div className="px-6 pt-4 pb-2">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Search connectors…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        {/* Category tabs */}
        <div className="px-6 py-2 border-b border-gray-800 flex gap-1 overflow-x-auto scrollbar-thin">
          {CATEGORY_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveCategory(tab.key)}
              className={`shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                activeCategory === tab.key
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Connector grid */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
              Loading connectors…
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-gray-500">
              <p className="text-sm">No connectors found.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((connector) => (
                <ConnectorCard
                  key={connector.id}
                  connector={connector}
                  onConnect={() => onSelect(connector)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ConnectorCard({
  connector,
  onConnect,
}: {
  connector: ConnectorDefinition;
  onConnect: () => void;
}) {
  const initials = connector.display_name.slice(0, 2).toUpperCase();
  const avatarBg = CATEGORY_AVATAR_BG[connector.category] ?? 'bg-gray-600';
  const visibleTypes = connector.supported_data_types.slice(0, 3);
  const remaining = connector.supported_data_types.length - 3;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex flex-col gap-3 hover:border-gray-600 transition-colors">
      {/* Top */}
      <div className="flex items-center gap-3">
        <div
          className={`${avatarBg} w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold text-xs shrink-0`}
        >
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate">{connector.display_name}</p>
          <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${CATEGORY_BADGE[connector.category]}`}>
            {connector.category.replace('_', ' ').toUpperCase()}
          </span>
        </div>
      </div>

      {/* Description */}
      {connector.description && (
        <p className="text-xs text-gray-400 line-clamp-2">{connector.description}</p>
      )}

      {/* Auth type */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Auth:</span>
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${AUTH_BADGE[connector.auth_type]}`}>
          {AUTH_LABELS[connector.auth_type]}
        </span>
      </div>

      {/* Data types */}
      {connector.supported_data_types.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {visibleTypes.map((dt) => (
            <span key={dt} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full">
              {dt}
            </span>
          ))}
          {remaining > 0 && (
            <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded-full">
              +{remaining} more
            </span>
          )}
        </div>
      )}

      {/* Connect button */}
      <button
        onClick={onConnect}
        className="mt-auto w-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium py-1.5 rounded-lg transition-colors"
      >
        Connect
      </button>
    </div>
  );
}
