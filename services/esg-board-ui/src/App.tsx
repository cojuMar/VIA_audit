import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  BarChart2, Target, Users, FileText, ClipboardList, Globe, Leaf,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getTenantId, fetchFrameworks } from './api';
import type { ESGFramework } from './types';
import ESGDashboard from './components/ESGDashboard';
import ESGTargets from './components/ESGTargets';
import BoardGovernance from './components/BoardGovernance';
import BoardPackages from './components/BoardPackages';
import AgendaBuilder from './components/AgendaBuilder';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

type Tab = 'esg' | 'targets' | 'governance' | 'packages' | 'agenda' | 'frameworks';

const TABS: { id: Tab; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'esg', label: 'ESG Dashboard', Icon: BarChart2 },
  { id: 'targets', label: 'Targets & Progress', Icon: Target },
  { id: 'governance', label: 'Board Governance', Icon: Users },
  { id: 'packages', label: 'Board Packages', Icon: FileText },
  { id: 'agenda', label: 'Agenda Builder', Icon: ClipboardList },
  { id: 'frameworks', label: 'Frameworks', Icon: Globe },
];

function categoryColor(category: string) {
  switch (category.toLowerCase()) {
    case 'environmental': return 'esg-e';
    case 'social': return 'esg-s';
    case 'governance': return 'esg-g';
    default: return 'bg-gray-100 text-gray-700';
  }
}

function FrameworksView() {
  const { data: frameworksRaw, isLoading } = useQuery<ESGFramework[]>({
    queryKey: ['frameworks'],
    queryFn: () => fetchFrameworks(),
    retry: 1,
  });
  const frameworks = frameworksRaw ?? [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">ESG Frameworks</h2>
        <p className="text-sm text-gray-500 mt-0.5">Disclosure frameworks and standards in use</p>
      </div>
      {isLoading ? (
        <div className="text-center py-12 text-gray-400">Loading frameworks…</div>
      ) : frameworks.length === 0 ? (
        <div className="metric-card text-center py-12 text-gray-400">No frameworks configured.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {frameworks.map((fw) => (
            <div key={fw.id} className="metric-card hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Leaf className="w-4 h-4 text-gray-400" />
                  <span className="text-sm font-bold text-gray-800">{fw.display_name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {fw.is_mandatory && (
                    <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">Mandatory</span>
                  )}
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${categoryColor(fw.category)}`}>{fw.category}</span>
                </div>
              </div>
              <p className="text-xs text-gray-500 font-mono mb-2">{fw.framework_key}{fw.version ? ` v${fw.version}` : ''}</p>
              {fw.description && (
                <p className="text-sm text-gray-600 line-clamp-3">{fw.description}</p>
              )}
              {fw.issuing_body && (
                <p className="text-xs text-gray-400 mt-2">Issued by: {fw.issuing_body}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<Tab>('esg');
  const tenantId = getTenantId();

  const renderContent = () => {
    switch (activeTab) {
      case 'esg': return <ESGDashboard tenantId={tenantId} />;
      case 'targets': return <ESGTargets tenantId={tenantId} />;
      case 'governance': return <BoardGovernance tenantId={tenantId} />;
      case 'packages': return <BoardPackages tenantId={tenantId} />;
      case 'agenda': return <AgendaBuilder tenantId={tenantId} />;
      case 'frameworks': return <FrameworksView />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Leaf className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-gray-900">Aegis</h1>
              <p className="text-xs text-gray-500">ESG &amp; Board Management</p>
            </div>
          </div>
          {tenantId && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Tenant:</span>
              <span className="text-xs font-mono bg-gray-100 text-gray-700 px-2 py-0.5 rounded">{tenantId}</span>
            </div>
          )}
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-0 overflow-x-auto">
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === id
                  ? 'border-indigo-600 text-indigo-700'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        {renderContent()}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
