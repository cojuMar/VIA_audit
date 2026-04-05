import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Users,
  Shield,
  BookOpen,
  UserCheck,
  AlertOctagon,
  Search,
  ChevronRight,
} from 'lucide-react';
import PeopleComplianceDashboard from './components/PeopleComplianceDashboard';
import EmployeeComplianceDashboard from './components/EmployeeComplianceDashboard';
import PoliciesManager from './components/PoliciesManager';
import TrainingTracker from './components/TrainingTracker';
import BackgroundChecks from './components/BackgroundChecks';
import EscalationLog from './components/EscalationLog';
import { fetchEmployees, setTenant } from './api';
import type { Employee } from './types';

type Tab =
  | 'dashboard'
  | 'employees'
  | 'policies'
  | 'training'
  | 'background'
  | 'escalations';

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('via_tenant_id') ?? 'default';
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

function EmployeeSearch({
  tenantId,
  onSelect,
}: {
  tenantId: string;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState('');

  const { data: employees } = useQuery<Employee[]>({
    queryKey: ['employees', tenantId],
    queryFn: fetchEmployees,
  });

  const filtered = (employees ?? []).filter(
    (e) =>
      query.length < 2 ||
      e.full_name.toLowerCase().includes(query.toLowerCase()) ||
      e.email.toLowerCase().includes(query.toLowerCase()) ||
      e.department?.toLowerCase().includes(query.toLowerCase()) ||
      e.employee_id.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-white mb-5 flex items-center gap-2">
        <Users size={20} className="text-indigo-400" />
        Employee Lookup
      </h2>

      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          className="input pl-9"
          placeholder="Search by name, email, department, or ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>

      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="text-center text-gray-500 py-10">No employees found.</div>
        )}
        {filtered.slice(0, 30).map((emp) => (
          <button
            key={emp.id}
            onClick={() => onSelect(emp.id)}
            className="w-full text-left card hover:border-indigo-500 hover:bg-indigo-950/20 transition-all flex items-center gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-200">{emp.full_name}</span>
                <span
                  className={`badge text-xs ${
                    emp.employment_status === 'active'
                      ? 'bg-green-900 text-green-300'
                      : emp.employment_status === 'on_leave'
                      ? 'bg-amber-900 text-amber-300'
                      : 'bg-gray-700 text-gray-400'
                  }`}
                >
                  {emp.employment_status.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5 truncate">
                {emp.email}
                {emp.department && ` · ${emp.department}`}
                {emp.job_title && ` · ${emp.job_title}`}
              </div>
            </div>
            <ChevronRight size={16} className="text-gray-600 flex-shrink-0" />
          </button>
        ))}
        {filtered.length > 30 && (
          <p className="text-xs text-center text-gray-600 pt-1">
            Showing 30 of {filtered.length} — narrow your search
          </p>
        )}
      </div>
    </div>
  );
}

const NAV_TABS: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
  { id: 'dashboard',   label: 'Org Dashboard',     icon: <LayoutDashboard size={15} /> },
  { id: 'employees',   label: 'Employee View',      icon: <Users size={15} /> },
  { id: 'policies',    label: 'Policies',           icon: <Shield size={15} /> },
  { id: 'training',    label: 'Training',           icon: <BookOpen size={15} /> },
  { id: 'background',  label: 'Background Checks',  icon: <UserCheck size={15} /> },
  { id: 'escalations', label: 'Escalations',        icon: <AlertOctagon size={15} /> },
];

function AppInner() {
  const [tenantId] = useState(getTenantId);
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null);

  useEffect(() => {
    setTenant(tenantId);
  }, [tenantId]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab !== 'employees') setSelectedEmployeeId(null);
  };

  return (
    <div className="via-app">
      <aside className="via-sidebar">
        <div className="via-sidebar-logo">
          <div className="via-logo-mark">V</div>
          <div>
            <div className="text-white text-sm font-bold leading-none">VIA</div>
            <div className="text-slate-500 text-[10px] leading-none mt-0.5 uppercase tracking-wider">People</div>
          </div>
        </div>
        <nav className="via-sidebar-nav">
          {NAV_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`via-nav-item ${activeTab === tab.id ? 'active' : ''}`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="via-sidebar-footer">
          <div className="text-xs truncate font-mono" style={{ color: '#334155' }}>{tenantId}</div>
        </div>
      </aside>

      <div className="via-main">
        <header className="via-topbar">
          <h1 className="text-sm font-bold" style={{ color: '#F1F5F9' }}>
            {NAV_TABS.find(t => t.id === activeTab)?.label}
          </h1>
        </header>
        <main className="via-content">
          {activeTab === 'dashboard' && (
            <PeopleComplianceDashboard tenantId={tenantId} />
          )}
          {activeTab === 'employees' && (
            selectedEmployeeId ? (
              <EmployeeComplianceDashboard
                tenantId={tenantId}
                employeeId={selectedEmployeeId}
                onBack={() => setSelectedEmployeeId(null)}
              />
            ) : (
              <EmployeeSearch
                tenantId={tenantId}
                onSelect={(id) => setSelectedEmployeeId(id)}
              />
            )
          )}
          {activeTab === 'policies' && (
            <PoliciesManager tenantId={tenantId} />
          )}
          {activeTab === 'training' && (
            <TrainingTracker tenantId={tenantId} />
          )}
          {activeTab === 'background' && (
            <BackgroundChecks tenantId={tenantId} />
          )}
          {activeTab === 'escalations' && (
            <EscalationLog tenantId={tenantId} />
          )}
        </main>
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
