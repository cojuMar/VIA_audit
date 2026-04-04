import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EngagementDashboard from './components/EngagementDashboard';
import PBCRequestList from './components/PBCRequestList';
import IssueRegister from './components/IssueRegister';
import WorkpaperEditor from './components/WorkpaperEditor';
import ExportPanel from './components/ExportPanel';
import type { AuditEngagement } from './types';

const queryClient = new QueryClient();

type AppView = 'engagements' | 'pbc' | 'issues' | 'workpapers' | 'export';

function AppInner() {
  const params = new URLSearchParams(window.location.search);
  const tenantId = params.get('tenantId') || localStorage.getItem('aegis_tenant_id') || '';

  const [selectedEngagementId, setSelectedEngagementId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AppView>('engagements');

  // When no engagement selected, show engagement list
  if (!selectedEngagementId) {
    return (
      <EngagementDashboard
        tenantId={tenantId}
        selectedEngagement={null}
        onSelectEngagement={(eng: AuditEngagement) => {
          setSelectedEngagementId(eng.id);
          setActiveTab('pbc');
        }}
        onNavigate={() => {}}
        onBack={() => {}}
      />
    );
  }

  // Tab navigation for selected engagement
  const tabs: { key: AppView; label: string }[] = [
    { key: 'pbc', label: 'PBC Requests' },
    { key: 'issues', label: 'Issue Register' },
    { key: 'workpapers', label: 'Workpapers' },
    { key: 'export', label: 'Export' },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Top nav with back button and tabs */}
      <div className="border-b border-gray-800 bg-gray-900">
        <div className="max-w-screen-xl mx-auto px-6 flex items-center gap-6 h-14">
          <button
            onClick={() => setSelectedEngagementId(null)}
            className="text-sm text-gray-400 hover:text-white flex items-center gap-1"
          >
            ← Engagements
          </button>
          <div className="h-4 w-px bg-gray-700" />
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`text-sm py-4 border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-screen-xl mx-auto px-6 py-6">
        {activeTab === 'pbc' && (
          <PBCRequestList
            tenantId={tenantId}
            engagementId={selectedEngagementId}
            onBack={() => setSelectedEngagementId(null)}
          />
        )}
        {activeTab === 'issues' && (
          <IssueRegister
            tenantId={tenantId}
            engagementId={selectedEngagementId}
            onBack={() => setSelectedEngagementId(null)}
          />
        )}
        {activeTab === 'workpapers' && (
          <WorkpaperEditor
            tenantId={tenantId}
            engagementId={selectedEngagementId}
            onBack={() => setSelectedEngagementId(null)}
          />
        )}
        {activeTab === 'export' && (
          <ExportPanel
            tenantId={tenantId}
            engagementId={selectedEngagementId}
          />
        )}
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
