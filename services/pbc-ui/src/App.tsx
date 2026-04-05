import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Briefcase, ClipboardList, AlertTriangle, FileEdit, Download } from 'lucide-react';
import { ErrorBoundary } from './components/ErrorBoundary';
import EngagementDashboard from './components/EngagementDashboard';
import PBCRequestList from './components/PBCRequestList';
import IssueRegister from './components/IssueRegister';
import WorkpaperEditor from './components/WorkpaperEditor';
import ExportPanel from './components/ExportPanel';
import type { AuditEngagement } from './types';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

type AppView = 'engagements' | 'pbc' | 'issues' | 'workpapers' | 'export';

const ENGAGEMENT_TABS: { key: AppView; label: string; icon: React.ReactNode }[] = [
  { key: 'pbc',        label: 'PBC Requests',   icon: <ClipboardList size={15} /> },
  { key: 'issues',     label: 'Issue Register',  icon: <AlertTriangle size={15} /> },
  { key: 'workpapers', label: 'Workpapers',      icon: <FileEdit size={15} /> },
  { key: 'export',     label: 'Export',          icon: <Download size={15} /> },
];

function AppInner() {
  const params = new URLSearchParams(window.location.search);
  const tenantId = params.get('tenantId') || localStorage.getItem('via_tenant_id') || '';

  const [selectedEngagement, setSelectedEngagement] = useState<AuditEngagement | null>(null);
  const [activeTab, setActiveTab] = useState<AppView>('engagements');

  const sidebarTabs = selectedEngagement
    ? ENGAGEMENT_TABS
    : [{ key: 'engagements' as AppView, label: 'Engagements', icon: <Briefcase size={15} /> }];

  const currentLabel = selectedEngagement
    ? ENGAGEMENT_TABS.find(t => t.key === activeTab)?.label ?? 'PBC Requests'
    : 'Engagements';

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">PBC &amp; Workpapers</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {selectedEngagement && (
            <button
              onClick={() => { setSelectedEngagement(null); setActiveTab('engagements'); }}
              className="via-nav-item mb-1"
              style={{ opacity: 0.7, fontSize: '11px' }}
            >
              <Briefcase size={13} />
              <span>← All Engagements</span>
            </button>
          )}
          {sidebarTabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`via-nav-item ${activeTab === tab.key ? 'active' : ''}`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs truncate font-mono" style={{ color: '#334155' }}>
            {selectedEngagement ? selectedEngagement.name ?? selectedEngagement.id : tenantId}
          </div>
        </div>
      </aside>

      <div className="via-main">
        <header className="via-topbar">
          <h1 className="text-sm font-bold text-slate-900">{currentLabel}</h1>
        </header>
        <main className="via-content">
          {!selectedEngagement && (
            <EngagementDashboard
              tenantId={tenantId}
              selectedEngagement={null}
              onSelectEngagement={(eng: AuditEngagement) => {
                setSelectedEngagement(eng);
                setActiveTab('pbc');
              }}
              onNavigate={() => {}}
              onBack={() => {}}
            />
          )}
          {selectedEngagement && activeTab === 'pbc' && (
            <PBCRequestList
              tenantId={tenantId}
              engagementId={selectedEngagement.id}
              onBack={() => { setSelectedEngagement(null); setActiveTab('engagements'); }}
            />
          )}
          {selectedEngagement && activeTab === 'issues' && (
            <IssueRegister
              tenantId={tenantId}
              engagementId={selectedEngagement.id}
              onBack={() => { setSelectedEngagement(null); setActiveTab('engagements'); }}
            />
          )}
          {selectedEngagement && activeTab === 'workpapers' && (
            <WorkpaperEditor
              tenantId={tenantId}
              engagementId={selectedEngagement.id}
              onBack={() => { setSelectedEngagement(null); setActiveTab('engagements'); }}
            />
          )}
          {selectedEngagement && activeTab === 'export' && (
            <ExportPanel
              tenantId={tenantId}
              engagementId={selectedEngagement.id}
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
      <ErrorBoundary>
        <AppInner />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
