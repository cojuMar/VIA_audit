import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  LayoutDashboard,
  List,
  DollarSign,
  FileText,
  Users,
  Cloud,
  Settings,
  Shield,
  type LucideIcon,
} from 'lucide-react';
import MonitoringDashboard from './components/MonitoringDashboard';
import { ErrorBoundary } from './components/ErrorBoundary';
import FindingsTable from './components/FindingsTable';
import PayrollAnalysis from './components/PayrollAnalysis';
import InvoiceDuplicates from './components/InvoiceDuplicates';
import SoDMatrix from './components/SoDMatrix';
import CloudConfigDrift from './components/CloudConfigDrift';
import RulesConfig from './components/RulesConfig';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

type TabId = 'dashboard' | 'findings' | 'payroll' | 'invoices' | 'sod' | 'cloud' | 'rules';

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'findings', label: 'All Findings', icon: List },
  { id: 'payroll', label: 'Payroll', icon: DollarSign },
  { id: 'invoices', label: 'Invoices', icon: FileText },
  { id: 'sod', label: 'Seg. of Duties', icon: Users },
  { id: 'cloud', label: 'Cloud Config', icon: Cloud },
  { id: 'rules', label: 'Rules Config', icon: Settings },
];

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('via_tenant_id') ?? 'default';
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [tenantId] = useState(getTenantId);
  const [tenantInput, setTenantInput] = useState(tenantId);
  const [currentTenant, setCurrentTenant] = useState(tenantId);

  useEffect(() => {
    document.title = `VIA Monitoring — ${currentTenant}`;
  }, [currentTenant]);

  const switchTenant = () => {
    const t = tenantInput.trim();
    if (t) {
      localStorage.setItem('via_tenant_id', t);
      setCurrentTenant(t);
      queryClient.clear();
    }
  };

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Monitoring</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {TABS.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`via-nav-item ${activeTab === tab.id ? 'active' : ''}`}
              >
                <Icon size={15} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs truncate font-mono" style={{ color: '#334155' }}>{currentTenant}</div>
        </div>
      </aside>
      <div className="via-main">
        <header className="via-topbar">
          <h1 className="text-sm font-bold" style={{ color: '#F1F5F9' }}>{TABS.find(t => t.id === activeTab)?.label}</h1>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={tenantInput}
              onChange={e => setTenantInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && switchTenant()}
              className="via-input text-xs w-36"
              placeholder="Tenant ID"
            />
            <button onClick={switchTenant} className="via-btn-primary via-btn-sm">Switch</button>
          </div>
        </header>
        <main className="via-content">
          {activeTab === 'dashboard' && <MonitoringDashboard tenantId={currentTenant} onNavigate={(tab) => setActiveTab(tab as TabId)} />}
          {activeTab === 'findings' && <FindingsTable tenantId={currentTenant} />}
          {activeTab === 'payroll' && <PayrollAnalysis tenantId={currentTenant} />}
          {activeTab === 'invoices' && <InvoiceDuplicates tenantId={currentTenant} />}
          {activeTab === 'sod' && <SoDMatrix tenantId={currentTenant} />}
          {activeTab === 'cloud' && <CloudConfigDrift tenantId={currentTenant} />}
          {activeTab === 'rules' && <RulesConfig tenantId={currentTenant} />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AppInner />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
