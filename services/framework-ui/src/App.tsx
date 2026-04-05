import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Shield, BarChart2, AlertTriangle, GitMerge, Calendar } from 'lucide-react'
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

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'library', label: 'Framework Library', icon: <Shield className="w-4 h-4" /> },
  { id: 'scores', label: 'Compliance Scores', icon: <BarChart2 className="w-4 h-4" /> },
  { id: 'gaps', label: 'Gap Analysis', icon: <AlertTriangle className="w-4 h-4" /> },
  { id: 'crosswalk', label: 'Crosswalk Matrix', icon: <GitMerge className="w-4 h-4" /> },
  { id: 'calendar', label: 'Compliance Calendar', icon: <Calendar className="w-4 h-4" /> },
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
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">Frameworks</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`via-nav-item ${activeTab === tab.id ? 'active' : ''}`}>
              {tab.icon}<span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs text-slate-600 truncate font-mono">{tenantId}</div>
        </div>
      </aside>
      <div className="via-main">
        <header className="via-topbar">
          <h1 className="text-base font-bold text-slate-900">{TABS.find(t => t.id === activeTab)?.label}</h1>
        </header>
        <main className="via-content">
          {activeTab === 'library' && <FrameworkPicker tenantId={tenantId} />}
          {activeTab === 'scores' && <ComplianceScoreCard tenantId={tenantId} />}
          {activeTab === 'gaps' && <GapAssessmentReport tenantId={tenantId} />}
          {activeTab === 'crosswalk' && <CrosswalkMatrix tenantId={tenantId} />}
          {activeTab === 'calendar' && <ComplianceCalendar tenantId={tenantId} />}
        </main>
      </div>
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
