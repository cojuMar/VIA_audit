import { useState, useEffect } from 'react';
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
    localStorage.setItem('aegis_tenant_id', fromUrl);
    return fromUrl;
  }
  return localStorage.getItem('aegis_tenant_id') ?? 'default';
}

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
  { id: 'dashboard', label: 'Org Dashboard', icon: <LayoutDashboard size={16} /> },
  { id: 'employees', label: 'Employee View', icon: <Users size={16} /> },
  { id: 'policies', label: 'Policies', icon: <Shield size={16} /> },
  { id: 'training', label: 'Training', icon: <BookOpen size={16} /> },
  { id: 'background', label: 'Background Checks', icon: <UserCheck size={16} /> },
  { id: 'escalations', label: 'Escalations', icon: <AlertOctagon size={16} /> },
];

export default function App() {
  const [tenantId] = useState(getTenantId);
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null);

  useEffect(() => {
    setTenant(tenantId);
  }, [tenantId]);

  // If tab changes away from employees, reset employee selection
  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab !== 'employees') setSelectedEmployeeId(null);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-950 overflow-hidden">
      {/* Top Nav */}
      <header className="flex-shrink-0 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-1 px-4 py-2 overflow-x-auto">
          {/* Logo / Brand */}
          <div className="flex items-center gap-2 mr-6 flex-shrink-0">
            <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Shield size={14} className="text-white" />
            </div>
            <span className="font-bold text-white text-sm whitespace-nowrap">Aegis People</span>
          </div>

          {/* Tabs */}
          {NAV_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}

          {/* Tenant badge */}
          <div className="ml-auto flex-shrink-0 text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
            Tenant: {tenantId}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
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
          <div className="h-full flex flex-col overflow-hidden" style={{ height: 'calc(100vh - 48px)' }}>
            <PoliciesManager tenantId={tenantId} />
          </div>
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
  );
}
