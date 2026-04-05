import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Plug, Grid } from 'lucide-react';
import IntegrationDashboard from './components/IntegrationDashboard';
import IntegrationDetail from './components/IntegrationDetail';
import ConnectorCatalog from './components/ConnectorCatalog';
import IntegrationSetupWizard from './components/IntegrationSetupWizard';
import type { TenantIntegration, ConnectorDefinition } from './types';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 15000,
    },
  },
});

function resolveTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl);
    return fromUrl;
  }
  const stored = localStorage.getItem('via_tenant_id');
  if (stored) return stored;
  return 'default';
}

type NavTab = 'dashboard' | 'catalog';

type View =
  | { kind: 'dashboard' }
  | { kind: 'detail'; integration: TenantIntegration }
  | { kind: 'catalog' }
  | { kind: 'wizard'; connector: ConnectorDefinition };

const NAV_TABS: { id: NavTab; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Integrations',      icon: <Plug size={15} /> },
  { id: 'catalog',   label: 'Connector Catalog',  icon: <Grid size={15} /> },
];

function AppInner() {
  const [tenantId] = useState(resolveTenantId);
  const [view, setView] = useState<View>({ kind: 'dashboard' });
  const [activeNav, setActiveNav] = useState<NavTab>('dashboard');

  useEffect(() => {
    if (tenantId !== 'default') {
      localStorage.setItem('via_tenant_id', tenantId);
    }
  }, [tenantId]);

  const handleNavChange = (tab: NavTab) => {
    setActiveNav(tab);
    setView(tab === 'catalog' ? { kind: 'catalog' } : { kind: 'dashboard' });
  };

  const currentLabel = view.kind === 'detail'
    ? 'Integration Detail'
    : NAV_TABS.find(t => t.id === activeNav)?.label ?? 'Integrations';

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Integrations</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {NAV_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleNavChange(tab.id)}
              className={`via-nav-item ${activeNav === tab.id ? 'active' : ''}`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs truncate font-mono" style={{ color: '#334155' }}>{tenantId}</div>
        </div>
      </aside>

      <div className="via-main">
        <header className="via-topbar">
          <div className="flex items-center gap-2">
            {view.kind === 'detail' && (
              <button
                onClick={() => { setView({ kind: 'dashboard' }); setActiveNav('dashboard'); }}
                className="text-xs text-slate-400 hover:text-white mr-2"
              >
                ← Back
              </button>
            )}
            <h1 className="text-sm font-bold" style={{ color: '#F1F5F9' }}>{currentLabel}</h1>
          </div>
        </header>
        <main className="via-content">
          {view.kind === 'dashboard' && (
            <IntegrationDashboard
              tenantId={tenantId}
              onSelectIntegration={(integration) => {
                setView({ kind: 'detail', integration });
                setActiveNav('dashboard');
              }}
              onAddIntegration={() => { setView({ kind: 'catalog' }); setActiveNav('catalog'); }}
            />
          )}

          {view.kind === 'detail' && (
            <IntegrationDetail
              integration={view.integration}
              tenantId={tenantId}
              onBack={() => { setView({ kind: 'dashboard' }); setActiveNav('dashboard'); }}
            />
          )}

          {view.kind === 'catalog' && (
            <ConnectorCatalog
              tenantId={tenantId}
              onSelect={(connector) => setView({ kind: 'wizard', connector })}
              onClose={() => { setView({ kind: 'dashboard' }); setActiveNav('dashboard'); }}
            />
          )}

          {view.kind === 'wizard' && (
            <IntegrationSetupWizard
              connector={view.connector}
              tenantId={tenantId}
              onSuccess={() => {
                void queryClient.invalidateQueries({ queryKey: ['integrations', tenantId] });
                void queryClient.invalidateQueries({ queryKey: ['dashboard-summary', tenantId] });
                setView({ kind: 'dashboard' });
                setActiveNav('dashboard');
              }}
              onClose={() => { setView({ kind: 'dashboard' }); setActiveNav('dashboard'); }}
            />
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
