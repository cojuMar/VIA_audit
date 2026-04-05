import { useState, useMemo } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LayoutDashboard, Globe, ClipboardList, Briefcase, Clock, Shield } from 'lucide-react';
import PlanningDashboard from './components/PlanningDashboard';
import { ErrorBoundary } from './components/ErrorBoundary';
import AuditUniverse from './components/AuditUniverse';
import AuditPlanView from './components/AuditPlanView';
import EngagementTracker from './components/EngagementTracker';
import GanttChart from './components/GanttChart';
import TimeTracker from './components/TimeTracker';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get('tenantId') || localStorage.getItem('via_tenant_id') || 'demo-tenant';
}

type Tab = 'dashboard' | 'universe' | 'plan' | 'engagements' | 'gantt' | 'time';

const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: 'universe', label: 'Audit Universe', icon: <Globe className="w-4 h-4" /> },
  { id: 'plan', label: 'Annual Plan', icon: <ClipboardList className="w-4 h-4" /> },
  { id: 'engagements', label: 'Engagements', icon: <Briefcase className="w-4 h-4" /> },
  { id: 'gantt', label: 'Gantt', icon: <Clock className="w-4 h-4" /> },
  { id: 'time', label: 'Time', icon: <Clock className="w-4 h-4" /> },
];

function AppContent() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const tenantId = useMemo(() => getTenantId(), []);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-indigo-900 text-white shadow-lg">
        <div className="max-w-screen-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Shield className="w-7 h-7 text-indigo-300" />
            <div>
              <div className="font-bold text-lg leading-tight">VIA</div>
              <div className="text-indigo-300 text-xs leading-tight">Audit Planning</div>
            </div>
          </div>
          <div className="ml-auto text-xs text-indigo-400 font-mono">
            tenant: {tenantId}
          </div>
        </div>
      </header>

      {/* Tab nav */}
      <nav className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-screen-2xl mx-auto px-4">
          <div className="flex gap-1 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-6">
        {activeTab === 'dashboard' && <PlanningDashboard tenantId={tenantId} />}
        {activeTab === 'universe' && <AuditUniverse tenantId={tenantId} />}
        {activeTab === 'plan' && <AuditPlanView tenantId={tenantId} />}
        {activeTab === 'engagements' && <EngagementTracker tenantId={tenantId} />}
        {activeTab === 'gantt' && <GanttChart tenantId={tenantId} />}
        {activeTab === 'time' && <TimeTracker tenantId={tenantId} />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AppContent />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
