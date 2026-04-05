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

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'esg',        label: 'ESG Dashboard',     icon: <BarChart2 size={15} /> },
  { id: 'targets',    label: 'Targets & Progress', icon: <Target size={15} /> },
  { id: 'governance', label: 'Board Governance',   icon: <Users size={15} /> },
  { id: 'packages',   label: 'Board Packages',     icon: <FileText size={15} /> },
  { id: 'agenda',     label: 'Agenda Builder',     icon: <ClipboardList size={15} /> },
  { id: 'frameworks', label: 'Frameworks',         icon: <Globe size={15} /> },
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
      case 'esg':        return <ESGDashboard tenantId={tenantId} />;
      case 'targets':    return <ESGTargets tenantId={tenantId} />;
      case 'governance': return <BoardGovernance tenantId={tenantId} />;
      case 'packages':   return <BoardPackages tenantId={tenantId} />;
      case 'agenda':     return <AgendaBuilder tenantId={tenantId} />;
      case 'frameworks': return <FrameworksView />;
    }
  };

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">ESG &amp; Board</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`via-nav-item ${activeTab === tab.id ? 'active' : ''}`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs text-slate-600 truncate font-mono">{tenantId}</div>
        </div>
      </aside>

      <div className="via-main">
        <header className="via-topbar">
          <h1 className="text-base font-bold text-slate-900">
            {TABS.find(t => t.id === activeTab)?.label}
          </h1>
        </header>
        <main className="via-content">
          {renderContent()}
        </main>
      </div>
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
