import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shield } from 'lucide-react'
import { FrameworkPicker } from './components/FrameworkPicker'
import { ComplianceScoreCard } from './components/ComplianceScoreCard'
import { GapAssessmentReport } from './components/GapAssessmentReport'
import { CrosswalkMatrix } from './components/CrosswalkMatrix'
import { ComplianceCalendar } from './components/ComplianceCalendar'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

type Tab = 'library' | 'scores' | 'gaps' | 'crosswalk' | 'calendar'

const TABS: { id: Tab; label: string }[] = [
  { id: 'library', label: 'Framework Library' },
  { id: 'scores', label: 'Compliance Scores' },
  { id: 'gaps', label: 'Gap Analysis' },
  { id: 'crosswalk', label: 'Crosswalk' },
  { id: 'calendar', label: 'Calendar' },
]

function getTenantId(): string {
  // Check URL param first
  const params = new URLSearchParams(window.location.search)
  const fromUrl = params.get('tenantId')
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl)
    return fromUrl
  }
  // Fall back to localStorage
  const stored = localStorage.getItem('via_tenant_id')
  if (stored) return stored
  // Default demo tenant
  const demo = 'tenant-demo-001'
  localStorage.setItem('via_tenant_id', demo)
  return demo
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<Tab>('library')
  const [tenantId] = useState<string>(getTenantId)

  useEffect(() => {
    document.title = 'VIA — Compliance Frameworks'
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-blue-600">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900 leading-tight">VIA Compliance Framework Engine</h1>
            <p className="text-xs text-gray-400">Tenant: {tenantId}</p>
          </div>
        </div>

        {/* Tab navigation */}
        <div className="max-w-screen-xl mx-auto px-6">
          <nav className="flex gap-0.5 -mb-px">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-screen-xl mx-auto px-6 py-8">
        {activeTab === 'library' && (
          <FrameworkPicker tenantId={tenantId} />
        )}
        {activeTab === 'scores' && (
          <ComplianceScoreCard tenantId={tenantId} />
        )}
        {activeTab === 'gaps' && (
          <GapAssessmentReport tenantId={tenantId} />
        )}
        {activeTab === 'crosswalk' && (
          <CrosswalkMatrix tenantId={tenantId} />
        )}
        {activeTab === 'calendar' && (
          <ComplianceCalendar tenantId={tenantId} />
        )}
      </main>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  )
}
