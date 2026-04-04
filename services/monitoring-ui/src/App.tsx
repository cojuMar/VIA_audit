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
    localStorage.setItem('aegis_tenant_id', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('aegis_tenant_id') ?? 'default';
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [tenantId] = useState(getTenantId);
  const [tenantInput, setTenantInput] = useState(tenantId);
  const [currentTenant, setCurrentTenant] = useState(tenantId);

  useEffect(() => {
    document.title = `Aegis Monitoring — ${currentTenant}`;
  }, [currentTenant]);

  const switchTenant = () => {
    const t = tenantInput.trim();
    if (t) {
      localStorage.setItem('aegis_tenant_id', t);
      setCurrentTenant(t);
      queryClient.clear();
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Top nav */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-indigo-600">
            <Shield size={18} className="text-white" />
          </div>
          <div>
            <span className="text-white font-bold tracking-tight">Project Aegis</span>
            <span className="text-gray-500 text-sm ml-2">Continuous Monitoring</span>
          </div>
        </div>
        {/* Tenant switcher */}
        <div className="flex items-center gap-2">
          <span className="text-gray-500 text-xs">Tenant:</span>
          <input
            type="text"
            value={tenantInput}
            onChange={e => setTenantInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && switchTenant()}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-40 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={switchTenant}
            className="px-2 py-1 bg-indigo-700 hover:bg-indigo-600 text-white rounded text-xs transition-colors"
          >
            Switch
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-52 bg-gray-900 border-r border-gray-800 flex flex-col flex-shrink-0">
          <nav className="flex-1 py-4 space-y-0.5 px-2">
            {TABS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-600/30'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                  }`}
                >
                  <Icon size={16} className={activeTab === tab.id ? 'text-indigo-400' : 'text-gray-500'} />
                  {tab.label}
                </button>
              );
            })}
          </nav>
          <div className="p-4 border-t border-gray-800">
            <p className="text-xs text-gray-600">Sprint 11 — v0.1.0</p>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">
          {activeTab === 'dashboard' && (
            <MonitoringDashboard
              tenantId={currentTenant}
              onNavigate={(tab) => setActiveTab(tab as TabId)}
            />
          )}
          {activeTab === 'findings' && (
            <FindingsTable tenantId={currentTenant} />
          )}
          {activeTab === 'payroll' && (
            <PayrollAnalysis tenantId={currentTenant} />
          )}
          {activeTab === 'invoices' && (
            <InvoiceDuplicates tenantId={currentTenant} />
          )}
          {activeTab === 'sod' && (
            <SoDMatrix tenantId={currentTenant} />
          )}
          {activeTab === 'cloud' && (
            <CloudConfigDrift tenantId={currentTenant} />
          )}
          {activeTab === 'rules' && (
            <RulesConfig tenantId={currentTenant} />
          )}
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
