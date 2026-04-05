import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
  // 1. URL param ?tenantId=…
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl);
    return fromUrl;
  }
  // 2. localStorage
  const stored = localStorage.getItem('via_tenant_id');
  if (stored) return stored;
  // 3. Fallback default
  return 'default';
}

type View =
  | { kind: 'dashboard' }
  | { kind: 'detail'; integration: TenantIntegration }
  | { kind: 'catalog' }
  | { kind: 'wizard'; connector: ConnectorDefinition };

function AppInner() {
  const [tenantId] = useState(resolveTenantId);
  const [view, setView] = useState<View>({ kind: 'dashboard' });

  // Propagate tenantId changes to query cache key without full reload
  useEffect(() => {
    if (tenantId !== 'default') {
      localStorage.setItem('via_tenant_id', tenantId);
    }
  }, [tenantId]);

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Tenant badge */}
      <div className="fixed top-2 right-3 z-40">
        <span className="text-xs bg-gray-800 border border-gray-700 text-gray-400 px-2 py-1 rounded-full font-mono">
          tenant: {tenantId}
        </span>
      </div>

      {/* Main view */}
      {view.kind === 'dashboard' && (
        <IntegrationDashboard
          tenantId={tenantId}
          onSelectIntegration={(integration) => setView({ kind: 'detail', integration })}
          onAddIntegration={() => setView({ kind: 'catalog' })}
        />
      )}

      {view.kind === 'detail' && (
        <IntegrationDetail
          integration={view.integration}
          tenantId={tenantId}
          onBack={() => setView({ kind: 'dashboard' })}
        />
      )}

      {/* Modal overlays */}
      {view.kind === 'catalog' && (
        <ConnectorCatalog
          tenantId={tenantId}
          onSelect={(connector) => setView({ kind: 'wizard', connector })}
          onClose={() => setView({ kind: 'dashboard' })}
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
          }}
          onClose={() => setView({ kind: 'dashboard' })}
        />
      )}
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
