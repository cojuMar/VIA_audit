import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shield, Building2 } from 'lucide-react'
import { VendorCatalog } from './components/VendorCatalog'
import { VendorRiskDashboard } from './components/VendorRiskDashboard'
import { TPRMDashboard } from './components/TPRMDashboard'
import { ErrorBoundary } from './components/ErrorBoundary'

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
    localStorage.setItem('via_tenant_id', fromUrl)
    return fromUrl
  }
  const fromStorage = localStorage.getItem('via_tenant_id')
  if (fromStorage) return fromStorage
  // Default for dev / demo
  return 'tenant_demo'
}

type Tab = 'overview' | 'catalog'

function AppShell() {
  const [tenantId] = useState<string>(getTenantId)
  const [selectedVendorId, setSelectedVendorId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

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

  const tabs = [
    { id: 'overview' as Tab, label: 'Portfolio Overview', icon: <Shield className="w-4 h-4" /> },
    { id: 'catalog' as Tab, label: 'Vendor Catalog', icon: <Building2 className="w-4 h-4" /> },
  ]

  if (selectedVendorId) {
    return (
      <div className="via-app">
        <aside className="via-sidebar">
          <div className="via-sidebar-logo">
            <div className="via-logo-mark">V</div>
            <div>
              <div className="text-white text-sm font-bold leading-none">VIA</div>
              <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Vendor Risk</div>
            </div>
          </div>
          <nav className="via-sidebar-nav">
            {tabs.map(t => (
              <button key={t.id} onClick={() => { handleBack(); setActiveTab(t.id); }} className="via-nav-item">
                {t.icon}<span>{t.label}</span>
              </button>
            ))}
          </nav>
          <div className="via-sidebar-footer">
            <div className="text-xs text-slate-600 truncate font-mono">{tenantId}</div>
          </div>
        </aside>
        <div className="via-main">
          <header className="via-topbar">
            <div className="flex items-center gap-2">
              <button onClick={handleBack} className="via-btn-secondary via-btn-sm">← Back</button>
              <h1 className="text-base font-bold text-slate-900">Vendor Details</h1>
            </div>
          </header>
          <main className="via-content">
            <VendorRiskDashboard tenantId={tenantId} vendorId={selectedVendorId} onBack={handleBack} />
          </main>
        </div>
      </div>
    )
  }

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Vendor Risk</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} className={`via-nav-item ${activeTab === t.id ? 'active' : ''}`}>
              {t.icon}<span>{t.label}</span>
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
          {activeTab === 'overview' && <TPRMDashboard tenantId={tenantId} onVendorSelect={handleVendorSelect} />}
          {activeTab === 'catalog' && <VendorCatalog tenantId={tenantId} onVendorSelect={handleVendorSelect} />}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AppShell />
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
