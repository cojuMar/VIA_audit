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
  { id: 'gantt', label: 'Gantt Chart', icon: <Clock className="w-4 h-4" /> },
  { id: 'time', label: 'Time Tracking', icon: <Clock className="w-4 h-4" /> },
];

function AppContent() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const tenantId = useMemo(() => getTenantId(), []);

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Audit Planning</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {tabs.map(tab => (
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
          <h1 className="text-base font-bold text-slate-900">{tabs.find(t => t.id === activeTab)?.label}</h1>
        </header>
        <main className="via-content">
          {activeTab === 'dashboard' && <PlanningDashboard tenantId={tenantId} />}
          {activeTab === 'universe' && <AuditUniverse tenantId={tenantId} />}
          {activeTab === 'plan' && <AuditPlanView tenantId={tenantId} />}
          {activeTab === 'engagements' && <EngagementTracker tenantId={tenantId} />}
          {activeTab === 'gantt' && <GanttChart tenantId={tenantId} />}
          {activeTab === 'time' && <TimeTracker tenantId={tenantId} />}
        </main>
      </div>
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
