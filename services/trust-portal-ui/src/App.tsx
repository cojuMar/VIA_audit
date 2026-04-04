import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PublicPortal from './components/PublicPortal';
import TrustPortalAdmin from './components/TrustPortalAdmin';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function resolveRoute(): { mode: 'portal'; slug: string } | { mode: 'admin'; tenantId: string } {
  const pathname = window.location.pathname;

  // Match /portal/:slug
  const portalMatch = pathname.match(/\/portal\/([^/]+)/);
  if (portalMatch) {
    return { mode: 'portal', slug: portalMatch[1] };
  }

  // Admin mode: tenantId from ?tenantId= param or localStorage
  const params = new URLSearchParams(window.location.search);
  const tenantFromQuery = params.get('tenantId');
  if (tenantFromQuery) {
    localStorage.setItem('aegis_tenant_id', tenantFromQuery);
    return { mode: 'admin', tenantId: tenantFromQuery };
  }

  const tenantFromStorage = localStorage.getItem('aegis_tenant_id');
  if (tenantFromStorage) {
    return { mode: 'admin', tenantId: tenantFromStorage };
  }

  // Fallback: no tenant
  return { mode: 'admin', tenantId: '' };
}

function AppContent() {
  const route = resolveRoute();

  if (route.mode === 'portal') {
    return <PublicPortal slug={route.slug} />;
  }

  if (!route.tenantId) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="text-center space-y-3">
          <h1 className="text-xl font-semibold text-gray-700">Aegis Trust Portal Admin</h1>
          <p className="text-sm text-gray-500">
            Add <code className="bg-gray-100 rounded px-1">?tenantId=YOUR_TENANT_ID</code> to the URL to access the admin panel.
          </p>
        </div>
      </div>
    );
  }

  return <TrustPortalAdmin tenantId={route.tenantId} />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
