import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shield, Map, Target, TrendingUp, Zap } from 'lucide-react';
import RiskDashboard from './components/RiskDashboard';
import RiskHeatmap from './components/RiskHeatmap';
import AppetiteConfig from './components/AppetiteConfig';
import TreatmentTracker from './components/TreatmentTracker';
import { ToastProvider } from './components/Toaster';
import { ErrorBoundary } from './components/ErrorBoundary';
import { setTenantId, fetchAiNarrative, suggestTreatments, fetchRisks } from './api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

type Tab = 'dashboard' | 'heatmap' | 'appetite' | 'treatments' | 'ai';

interface NavItem {
  id: Tab;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <Shield className="h-4 w-4" /> },
  { id: 'heatmap', label: 'Heat Map', icon: <Map className="h-4 w-4" /> },
  { id: 'appetite', label: 'Risk Appetite', icon: <Target className="h-4 w-4" /> },
  { id: 'treatments', label: 'Treatments', icon: <TrendingUp className="h-4 w-4" /> },
  { id: 'ai', label: 'AI Insights', icon: <Zap className="h-4 w-4" /> },
];

function AiInsights({ tenantId }: { tenantId: string }) {
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [narrativeDate, setNarrativeDate] = useState<string | null>(null);
  const [riskId, setRiskId] = useState('');
  const [suggestions, setSuggestions] = useState<Array<{ title: string; description: string; treatment_type: string }> | null>(null);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [risks, setRisks] = useState<Array<{ id: string; risk_id: string; title: string }>>([]);

  useEffect(() => {
    fetchRisks().then((r) => setRisks(r.map((x) => ({ id: x.id, risk_id: x.risk_id, title: x.title }))));
  }, [tenantId]);

  async function handleNarrative() {
    setNarrativeLoading(true);
    setNarrative(null);
    try {
      const result = await fetchAiNarrative();
      setNarrative(result.narrative);
      setNarrativeDate(result.generated_at);
    } catch {
      setNarrative('Failed to generate narrative. Please try again.');
    } finally {
      setNarrativeLoading(false);
    }
  }

  async function handleSuggest() {
    if (!riskId) return;
    setSuggestLoading(true);
    setSuggestions(null);
    try {
      const result = await suggestTreatments(riskId);
      setSuggestions(result.suggestions);
    } catch {
      setSuggestions([]);
    } finally {
      setSuggestLoading(false);
    }
  }

  const typeColor: Record<string, string> = {
    mitigate: 'bg-blue-50 text-blue-700 ring-blue-600/20',
    accept: 'bg-gray-50 text-gray-600 ring-gray-500/20',
    transfer: 'bg-purple-50 text-purple-700 ring-purple-600/20',
    avoid: 'bg-red-50 text-red-700 ring-red-600/20',
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">AI Insights</h1>

      {/* Risk Narrative */}
      <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Risk Portfolio Narrative</h2>
            <p className="text-sm text-gray-500">AI-generated summary of your current risk landscape.</p>
          </div>
          <button
            onClick={handleNarrative}
            disabled={narrativeLoading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            <Zap className="h-4 w-4" />
            {narrativeLoading ? 'Generating…' : 'Generate Narrative'}
          </button>
        </div>

        {narrative && (
          <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
            {narrativeDate && (
              <p className="mb-2 text-xs text-indigo-400">
                Generated at {new Date(narrativeDate).toLocaleString()}
              </p>
            )}
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{narrative}</p>
          </div>
        )}
      </div>

      {/* Treatment Suggestions */}
      <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="text-base font-semibold text-gray-900 mb-1">AI Treatment Suggestions</h2>
        <p className="text-sm text-gray-500 mb-4">Select a risk to get AI-powered treatment suggestions.</p>

        <div className="flex gap-3 mb-4">
          <select
            value={riskId}
            onChange={(e) => setRiskId(e.target.value)}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">Select a risk…</option>
            {risks.map((r) => (
              <option key={r.id} value={r.id}>
                {r.risk_id} — {r.title}
              </option>
            ))}
          </select>
          <button
            onClick={handleSuggest}
            disabled={!riskId || suggestLoading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            <Zap className="h-4 w-4" />
            {suggestLoading ? 'Analysing…' : 'Get Suggestions'}
          </button>
        </div>

        {suggestions && suggestions.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-6">No suggestions returned.</p>
        )}

        {suggestions && suggestions.length > 0 && (
          <div className="space-y-3">
            {suggestions.map((s, i) => (
              <div key={i} className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`status-badge ${typeColor[s.treatment_type] ?? 'bg-gray-50 text-gray-600 ring-gray-500/20'} capitalize`}
                  >
                    {s.treatment_type}
                  </span>
                  <span className="text-sm font-semibold text-gray-900">{s.title}</span>
                </div>
                <p className="text-sm text-gray-600">{s.description}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');

  // Resolve tenantId from URL ?tenantId= or localStorage
  const [tenantId] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('tenantId');
    if (fromUrl) {
      localStorage.setItem('via_tenant_id', fromUrl);
      return fromUrl;
    }
    return localStorage.getItem('via_tenant_id') ?? 'default';
  });

  useEffect(() => {
    setTenantId(tenantId);
  }, [tenantId]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Nav */}
      <header className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            {/* Brand */}
            <div className="flex items-center gap-2">
              <Shield className="h-6 w-6 text-indigo-600" />
              <span className="text-lg font-bold text-gray-900">VIA</span>
              <span className="hidden text-sm text-gray-400 sm:block">Risk Management</span>
            </div>

            {/* Nav */}
            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    activeTab === item.id
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                  }`}
                >
                  {item.icon}
                  <span className="hidden sm:inline">{item.label}</span>
                </button>
              ))}
            </nav>

            {/* Tenant chip */}
            <div className="hidden items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600 lg:flex">
              Tenant: <span className="font-semibold">{tenantId}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {activeTab === 'dashboard' && <RiskDashboard tenantId={tenantId} />}
        {activeTab === 'heatmap' && <RiskHeatmap tenantId={tenantId} />}
        {activeTab === 'appetite' && <AppetiteConfig tenantId={tenantId} />}
        {activeTab === 'treatments' && <TreatmentTracker tenantId={tenantId} />}
        {activeTab === 'ai' && <AiInsights tenantId={tenantId} />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <ToastProvider>
          <AppInner />
        </ToastProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
