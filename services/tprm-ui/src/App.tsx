import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shield } from 'lucide-react'
import { VendorCatalog } from './components/VendorCatalog'
import { VendorRiskDashboard } from './components/VendorRiskDashboard'
import { TPRMDashboard } from './components/TPRMDashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search)
  const fromUrl = params.get('tenantId') ?? params.get('tenant_id')
  if (fromUrl) {
    localStorage.setItem('aegis_tenant_id', fromUrl)
    return fromUrl
  }
  const fromStorage = localStorage.getItem('aegis_tenant_id')
  if (fromStorage) return fromStorage
  // Default for dev / demo
  return 'tenant_demo'
}

function AppShell() {
  const [tenantId] = useState<string>(getTenantId)
  const [selectedVendorId, setSelectedVendorId] = useState<string | null>(null)

  // Support browser back button
  useEffect(() => {
    function onPopState() {
      const params = new URLSearchParams(window.location.search)
      const vid = params.get('vendorId')
      setSelectedVendorId(vid)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function handleVendorSelect(vendorId: string) {
    setSelectedVendorId(vendorId)
    const url = new URL(window.location.href)
    url.searchParams.set('vendorId', vendorId)
    window.history.pushState({}, '', url.toString())
  }

  function handleBack() {
    setSelectedVendorId(null)
    const url = new URL(window.location.href)
    url.searchParams.delete('vendorId')
    window.history.pushState({}, '', url.toString())
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-screen-xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-3">
          <Shield className="w-6 h-6 text-blue-600 shrink-0" />
          <h1 className="text-base font-bold text-gray-900 tracking-tight">
            Aegis <span className="font-normal text-gray-400">—</span> Vendor Risk Management
          </h1>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-gray-400 hidden sm:block">Tenant:</span>
            <span className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600">{tenantId}</span>
          </div>
        </div>
      </header>

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">
        {selectedVendorId ? (
          /* ── Vendor Detail View ── */
          <VendorRiskDashboard
            tenantId={tenantId}
            vendorId={selectedVendorId}
            onBack={handleBack}
          />
        ) : (
          /* ── Portfolio View: Dashboard + Catalog side by side on desktop ── */
          <div className="space-y-8">
            {/* Portfolio dashboard */}
            <TPRMDashboard
              tenantId={tenantId}
              onVendorSelect={handleVendorSelect}
            />

            {/* Divider */}
            <div className="border-t border-gray-200" />

            {/* Vendor catalog */}
            <div>
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Vendor Catalog</h2>
                <p className="text-sm text-gray-500">All third-party vendors and their risk profiles</p>
              </div>
              <VendorCatalog
                tenantId={tenantId}
                onVendorSelect={handleVendorSelect}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}
