import { useState, useEffect } from 'react';
import { Home, ClipboardList, Plus, RefreshCw } from 'lucide-react';
import HomeScreen from './components/HomeScreen';
import AuditList from './components/AuditList';
import AuditPlayer from './components/AuditPlayer';
import AuditSummary from './components/AuditSummary';
import TemplateSelector from './components/TemplateSelector';
import { useSyncStatus, useOnlineStatus } from './offline/sync';
import type { FieldAudit } from './types';

type View =
  | 'home'
  | 'audits'
  | 'new'
  | 'audit-player'
  | 'audit-summary';

type NavTab = 'home' | 'audits' | 'new' | 'sync';

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('aegis_tenant_id', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('aegis_tenant_id') ?? 'default';
}

function getAuditorEmail(): string | null {
  return localStorage.getItem('aegis_auditor_email');
}

function EmailPrompt({ onSubmit }: { onSubmit: (email: string) => void }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.includes('@')) {
      setError('Please enter a valid email address');
      return;
    }
    onSubmit(email.trim().toLowerCase());
  };

  return (
    <div className="min-h-screen bg-blue-700 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center text-white">
          <div className="w-20 h-20 bg-white/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <ClipboardList size={40} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold">Aegis Field Auditor</h1>
          <p className="text-blue-200 mt-1 text-sm">Enter your email to get started</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="email"
              className="input-field text-base"
              placeholder="auditor@company.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setError('');
              }}
              autoComplete="email"
              autoFocus
            />
            {error && <p className="text-red-300 text-sm mt-1">{error}</p>}
          </div>
          <button type="submit" className="btn-primary w-full py-4 text-base font-bold bg-white text-blue-700 hover:bg-blue-50">
            Get Started
          </button>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [tenantId] = useState(getTenantId);
  const [auditorEmail, setAuditorEmail] = useState<string | null>(getAuditorEmail);
  const [currentView, setCurrentView] = useState<View>('home');
  const [activeNav, setActiveNav] = useState<NavTab>('home');

  // Active audit player state
  const [playerState, setPlayerState] = useState<{
    templateId: string;
    auditId?: string;
    locationName: string;
    assignmentId?: string;
  } | null>(null);

  // Active summary state
  const [summaryAuditId, setSummaryAuditId] = useState<string | null>(null);

  const isOnline = useOnlineStatus();
  const syncStatus = useSyncStatus(tenantId, auditorEmail ?? '');
  const totalPending =
    syncStatus.pendingAudits + syncStatus.pendingResponses + syncStatus.pendingPhotos;

  useEffect(() => {
    // Persist tenant ID
    if (tenantId) localStorage.setItem('aegis_tenant_id', tenantId);
  }, [tenantId]);

  const handleEmailSubmit = (email: string) => {
    localStorage.setItem('aegis_auditor_email', email);
    setAuditorEmail(email);
  };

  const navigateTo = (view: View, nav?: NavTab) => {
    setCurrentView(view);
    if (nav) setActiveNav(nav);
  };

  const handleNavClick = (tab: NavTab) => {
    setActiveNav(tab);
    if (tab === 'home') navigateTo('home');
    else if (tab === 'audits') navigateTo('audits');
    else if (tab === 'new') navigateTo('new');
    else if (tab === 'sync') {
      syncStatus.triggerSync();
    }
  };

  const handleAuditCreated = (audit: FieldAudit) => {
    setPlayerState({
      templateId: audit.template_id,
      auditId: audit.id,
      locationName: audit.location_name,
      assignmentId: audit.assignment_id,
    });
    navigateTo('audit-player');
  };

  const handleOpenAudit = (auditId: string) => {
    setSummaryAuditId(auditId);
    navigateTo('audit-summary');
  };

  // First launch: prompt for email
  if (!auditorEmail) {
    return <EmailPrompt onSubmit={handleEmailSubmit} />;
  }

  // ── Views that take full screen (no bottom nav) ─────────────────────────
  if (currentView === 'audit-player' && playerState) {
    return (
      <AuditPlayer
        tenantId={tenantId}
        templateId={playerState.templateId}
        auditId={playerState.auditId}
        assignmentId={playerState.assignmentId}
        auditorEmail={auditorEmail}
        locationName={playerState.locationName}
        onComplete={() => {
          setPlayerState(null);
          navigateTo('audits', 'audits');
        }}
        onBack={() => {
          setPlayerState(null);
          navigateTo('new', 'new');
        }}
      />
    );
  }

  if (currentView === 'audit-summary' && summaryAuditId) {
    return (
      <AuditSummary
        tenantId={tenantId}
        auditId={summaryAuditId}
        onBack={() => {
          setSummaryAuditId(null);
          navigateTo('audits', 'audits');
        }}
      />
    );
  }

  if (currentView === 'new') {
    return (
      <TemplateSelector
        tenantId={tenantId}
        auditorEmail={auditorEmail}
        onAuditCreated={handleAuditCreated}
        onBack={() => navigateTo('home', 'home')}
      />
    );
  }

  // ── Main tabbed views ────────────────────────────────────────────────────
  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Main content */}
      <div className="flex-1 overflow-y-auto" style={{ paddingBottom: '4.5rem' }}>
        {currentView === 'home' && (
          <HomeScreen
            tenantId={tenantId}
            auditorEmail={auditorEmail}
            onStartNewAudit={() => navigateTo('new', 'new')}
            onViewAudits={() => navigateTo('audits', 'audits')}
            onOpenAudit={handleOpenAudit}
          />
        )}
        {currentView === 'audits' && (
          <AuditList
            tenantId={tenantId}
            auditorEmail={auditorEmail}
            onOpenAudit={handleOpenAudit}
          />
        )}
      </div>

      {/* Bottom navigation bar */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex safe-bottom z-40"
           style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        {/* Home */}
        <button
          onClick={() => handleNavClick('home')}
          className={`bottom-nav-item ${activeNav === 'home' ? 'text-blue-600' : 'text-gray-500'}`}
        >
          <Home size={22} />
          <span>Home</span>
        </button>

        {/* My Audits */}
        <button
          onClick={() => handleNavClick('audits')}
          className={`bottom-nav-item ${activeNav === 'audits' ? 'text-blue-600' : 'text-gray-500'}`}
        >
          <ClipboardList size={22} />
          <span>My Audits</span>
        </button>

        {/* New Audit — highlighted center button */}
        <button
          onClick={() => handleNavClick('new')}
          className="flex flex-col items-center justify-center flex-1 py-1 gap-1 text-xs"
        >
          <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center shadow-lg active:bg-blue-700 -mt-4">
            <Plus size={26} className="text-white" />
          </div>
          <span className={activeNav === 'new' ? 'text-blue-600' : 'text-gray-500'}>New</span>
        </button>

        {/* Sync */}
        <button
          onClick={() => handleNavClick('sync')}
          className={`bottom-nav-item relative ${activeNav === 'sync' ? 'text-blue-600' : 'text-gray-500'}`}
        >
          <div className="relative">
            <RefreshCw
              size={22}
              className={syncStatus.isSyncing ? 'animate-spin text-blue-500' : isOnline ? '' : 'text-gray-400'}
            />
            {totalPending > 0 && (
              <span className="sync-badge">
                {totalPending > 99 ? '99+' : totalPending}
              </span>
            )}
          </div>
          <span>Sync</span>
        </button>
      </nav>
    </div>
  );
}
