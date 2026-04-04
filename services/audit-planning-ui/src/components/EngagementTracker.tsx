import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Plus, CheckCircle, Clock, User } from 'lucide-react';
import {
  fetchEngagements,
  fetchEngagement,
  createEngagement,
  transitionEngagement,
  fetchEngagementMilestones,
  fetchEngagementResources,
  fetchEngagementHours,
  logHours,
  completeMilestone,
  assignResource,
  seedMilestones,
} from '../api';
import type { Engagement, Milestone, ResourceAssignment, EngagementHours } from '../types';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface Props {
  tenantId: string;
}

const STATUS_TRANSITIONS: Record<string, string[]> = {
  planning: ['fieldwork', 'cancelled'],
  fieldwork: ['reporting', 'planning'],
  reporting: ['review', 'fieldwork'],
  review: ['closed', 'reporting'],
  closed: [],
  cancelled: ['planning'],
};

const STATUS_COLORS: Record<string, string> = {
  planning: 'bg-indigo-100 text-indigo-700',
  fieldwork: 'bg-amber-100 text-amber-700',
  reporting: 'bg-blue-100 text-blue-700',
  review: 'bg-purple-100 text-purple-700',
  closed: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-600',
};

const ADVANCE_STATUSES = ['fieldwork', 'reporting', 'review', 'closed'];
const PIE_COLORS = ['#6366f1', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444'];

const ACTIVITY_TYPES = ['planning', 'fieldwork', 'reporting', 'review', 'admin', 'travel'];
const AUDIT_TYPES = ['financial', 'operational', 'compliance', 'it', 'fraud', 'follow_up'];
const RESOURCE_ROLES = ['lead', 'senior', 'staff', 'specialist', 'manager', 'observer'];

type DrawerTab = 'overview' | 'milestones' | 'team' | 'time';

function InitialsAvatar({ name }: { name?: string }) {
  if (!name) return <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-400 text-xs"><User className="w-4 h-4" /></div>;
  const initials = name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
  return (
    <div className="w-8 h-8 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
      {initials}
    </div>
  );
}

function ProgressBar({ logged, budget }: { logged: number; budget: number }) {
  const pct = budget > 0 ? Math.min((logged / budget) * 100, 100) : 0;
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-400' : 'bg-indigo-500';
  return (
    <div className="w-full bg-gray-100 rounded-full h-2">
      <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function EngagementTracker({ tenantId: _tenantId }: Props) {
  const qc = useQueryClient();

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [leadFilter, setLeadFilter] = useState('');
  const [search, setSearch] = useState('');

  // Drawer
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('overview');

  // Create modal
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: '',
    audit_type: 'operational',
    status: 'planning',
    scope: '',
    objectives: '',
    planned_start_date: '',
    planned_end_date: '',
    budget_hours: 200,
    lead_auditor: '',
    engagement_manager: '',
    engagement_code: '',
  });

  // Log hours form
  const [logForm, setLogForm] = useState({
    auditor_name: '',
    auditor_email: '',
    entry_date: new Date().toISOString().split('T')[0],
    hours: 1,
    activity_type: 'fieldwork',
    description: '',
    is_billable: true,
  });

  // Add member form
  const [memberForm, setMemberForm] = useState({
    auditor_name: '',
    auditor_email: '',
    role: 'staff',
    allocated_hours: 40,
  });

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => fetchEngagements(),
  });

  const { data: selectedEngagement } = useQuery<Engagement>({
    queryKey: ['engagement', selectedId],
    queryFn: () => fetchEngagement(selectedId!),
    enabled: !!selectedId,
  });

  const { data: milestones = [] } = useQuery<Milestone[]>({
    queryKey: ['milestones', selectedId],
    queryFn: () => fetchEngagementMilestones(selectedId!),
    enabled: !!selectedId && drawerTab === 'milestones',
  });

  const { data: resources = [] } = useQuery<ResourceAssignment[]>({
    queryKey: ['resources', selectedId],
    queryFn: () => fetchEngagementResources(selectedId!),
    enabled: !!selectedId && drawerTab === 'team',
  });

  const { data: hours } = useQuery<EngagementHours>({
    queryKey: ['hours', selectedId],
    queryFn: () => fetchEngagementHours(selectedId!),
    enabled: !!selectedId && drawerTab === 'time',
  });

  const transitionMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      transitionEngagement(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['engagements'] });
      qc.invalidateQueries({ queryKey: ['engagement', selectedId] });
    },
  });

  const createMutation = useMutation({
    mutationFn: createEngagement,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['engagements'] });
      setCreateOpen(false);
    },
  });

  const logHoursMutation = useMutation({
    mutationFn: (data: object) => logHours(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hours', selectedId] });
      qc.invalidateQueries({ queryKey: ['engagement', selectedId] });
    },
  });

  const completeMilestoneMutation = useMutation({
    mutationFn: (id: string) => completeMilestone(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['milestones', selectedId] });
    },
  });

  const seedMilestonesMutation = useMutation({
    mutationFn: () => seedMilestones(selectedId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['milestones', selectedId] });
    },
  });

  const assignMemberMutation = useMutation({
    mutationFn: (data: object) => assignResource(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['resources', selectedId] });
      setMemberForm({ auditor_name: '', auditor_email: '', role: 'staff', allocated_hours: 40 });
    },
  });

  const filtered = engagements.filter((e) => {
    if (statusFilter && e.status !== statusFilter) return false;
    if (leadFilter && !e.lead_auditor?.toLowerCase().includes(leadFilter.toLowerCase())) return false;
    if (search && !e.title.toLowerCase().includes(search.toLowerCase()) &&
      !e.engagement_code?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  // Next milestone for each engagement (from milestones stored on engagement object)
  function nextMilestone(eng: Engagement) {
    const ms = eng.milestones ?? [];
    const pending = ms
      .filter((m) => m.status !== 'completed')
      .sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime());
    return pending[0];
  }

  function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    createMutation.mutate(createForm);
  }

  function handleLogHours(e: React.FormEvent) {
    e.preventDefault();
    logHoursMutation.mutate({ ...logForm, engagement_id: selectedId });
  }

  function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    assignMemberMutation.mutate({ ...memberForm, engagement_id: selectedId });
  }

  const hoursData = hours
    ? Object.entries(hours.by_activity).map(([activity, value]) => ({ activity, value }))
    : [];

  const MILESTONE_TYPE_ICONS: Record<string, string> = {
    kickoff: '🚀',
    fieldwork_start: '🔍',
    fieldwork_end: '✅',
    draft_report: '📝',
    final_report: '📄',
    management_response: '💬',
    default: '🔷',
  };

  return (
    <div className="space-y-5">
      {/* Filter bar */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4 flex flex-wrap gap-3 items-end">
        <div className="relative flex-1 min-w-40">
          <input
            type="text"
            placeholder="Search by title or code…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded-lg text-sm px-2 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="">All Statuses</option>
            {Object.keys(STATUS_TRANSITIONS).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <input
            type="text"
            placeholder="Lead auditor…"
            value={leadFilter}
            onChange={(e) => setLeadFilter(e.target.value)}
            className="border border-gray-300 rounded-lg text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg"
        >
          <Plus className="w-4 h-4" />
          New Engagement
        </button>
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.length === 0 ? (
          <div className="sm:col-span-2 xl:col-span-3 bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
            No engagements found
          </div>
        ) : (
          filtered.map((eng) => {
            const transitions = STATUS_TRANSITIONS[eng.status] ?? [];
            const nm = nextMilestone(eng);
            const logged = eng.total_logged_hours ?? 0;
            return (
              <div
                key={eng.id}
                className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => { setSelectedId(eng.id); setDrawerTab('overview'); }}
              >
                <div className="flex items-start justify-between mb-2 gap-2">
                  <div className="flex-1 min-w-0">
                    {eng.engagement_code && (
                      <span className="text-xs font-mono bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded mr-2">
                        {eng.engagement_code}
                      </span>
                    )}
                    <div className="font-semibold text-gray-900 text-sm mt-1 truncate">{eng.title}</div>
                  </div>
                  <span className={`status-badge shrink-0 ${STATUS_COLORS[eng.status] ?? 'bg-gray-100 text-gray-600'}`}>
                    {eng.status}
                  </span>
                </div>
                <div className="flex items-center gap-2 mb-3">
                  <InitialsAvatar name={eng.lead_auditor} />
                  <span className="text-xs text-gray-500">{eng.lead_auditor ?? 'Unassigned'}</span>
                </div>
                <div className="mb-2">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>{logged}h logged</span>
                    <span>{eng.budget_hours}h budget</span>
                  </div>
                  <ProgressBar logged={logged} budget={eng.budget_hours} />
                </div>
                {nm && (
                  <div className="text-xs text-gray-400 mt-2 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Next: {nm.title} — {new Date(nm.due_date).toLocaleDateString()}
                  </div>
                )}
                {/* Transition buttons */}
                {transitions.length > 0 && (
                  <div
                    className="flex gap-1.5 mt-3 flex-wrap"
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    {transitions.map((t) => {
                      const isAdvance = ADVANCE_STATUSES.includes(t);
                      return (
                        <button
                          key={t}
                          onClick={() => transitionMutation.mutate({ id: eng.id, status: t })}
                          disabled={transitionMutation.isPending}
                          className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors disabled:opacity-60 ${
                            isAdvance
                              ? 'bg-green-100 text-green-700 hover:bg-green-200'
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          }`}
                        >
                          → {t}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Detail drawer */}
      {selectedId && (
        <div className="fixed inset-0 z-30 flex justify-end">
          <div className="flex-1 bg-black/30" onClick={() => setSelectedId(null)} />
          <div className="w-full max-w-xl bg-white shadow-2xl flex flex-col overflow-hidden">
            {/* Drawer header */}
            <div className="px-5 py-4 border-b border-gray-200 bg-gray-50">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  {selectedEngagement?.engagement_code && (
                    <span className="text-xs font-mono bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded mr-2">
                      {selectedEngagement.engagement_code}
                    </span>
                  )}
                  <div className="font-bold text-gray-900 text-base mt-0.5">
                    {selectedEngagement?.title ?? 'Loading…'}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                      {selectedEngagement?.audit_type}
                    </span>
                    {selectedEngagement && (
                      <span className={`status-badge ${STATUS_COLORS[selectedEngagement.status] ?? 'bg-gray-100 text-gray-600'}`}>
                        {selectedEngagement.status}
                      </span>
                    )}
                  </div>
                </div>
                <button onClick={() => setSelectedId(null)}>
                  <X className="w-5 h-5 text-gray-400 hover:text-gray-700" />
                </button>
              </div>
              {/* Tabs */}
              <div className="flex gap-4 mt-3">
                {(['overview', 'milestones', 'team', 'time'] as DrawerTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDrawerTab(tab)}
                    className={`text-sm pb-1 font-medium capitalize border-b-2 transition-colors ${
                      drawerTab === tab
                        ? 'border-indigo-600 text-indigo-700'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {/* Overview tab */}
              {drawerTab === 'overview' && selectedEngagement && (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Scope</div>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap">
                      {selectedEngagement.scope ?? <span className="text-gray-400">Not defined</span>}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Objectives</div>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap">
                      {selectedEngagement.objectives ?? <span className="text-gray-400">Not defined</span>}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">Planned Dates</div>
                      <div className="text-sm font-medium text-gray-800 mt-0.5">
                        {selectedEngagement.planned_start_date ?? '?'} → {selectedEngagement.planned_end_date ?? '?'}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">Actual Dates</div>
                      <div className="text-sm font-medium text-gray-800 mt-0.5">
                        {selectedEngagement.actual_start_date ?? '—'} → {selectedEngagement.actual_end_date ?? '—'}
                      </div>
                    </div>
                  </div>
                  {/* Budget gauge */}
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="flex justify-between text-xs text-gray-500 mb-2">
                      <span>Hours: {selectedEngagement.total_logged_hours ?? 0}h logged</span>
                      <span>{selectedEngagement.budget_hours}h budget</span>
                    </div>
                    <ProgressBar
                      logged={selectedEngagement.total_logged_hours ?? 0}
                      budget={selectedEngagement.budget_hours}
                    />
                    <div className="text-xs text-gray-400 mt-1">
                      {selectedEngagement.budget_hours > 0
                        ? `${(((selectedEngagement.total_logged_hours ?? 0) / selectedEngagement.budget_hours) * 100).toFixed(1)}% consumed`
                        : '—'}
                    </div>
                  </div>
                </div>
              )}

              {/* Milestones tab */}
              {drawerTab === 'milestones' && (
                <div className="space-y-3">
                  <div className="flex justify-end">
                    <button
                      onClick={() => seedMilestonesMutation.mutate()}
                      disabled={seedMilestonesMutation.isPending}
                      className="text-xs px-3 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors disabled:opacity-60"
                    >
                      Seed Standard Milestones
                    </button>
                  </div>
                  {milestones.length === 0 ? (
                    <div className="text-center text-gray-400 text-sm py-8">No milestones. Seed them above.</div>
                  ) : (
                    <div className="relative">
                      <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
                      <div className="space-y-4">
                        {milestones
                          .sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime())
                          .map((m) => {
                            const isOverdue = !m.completed_date && new Date(m.due_date) < new Date();
                            return (
                              <div key={m.id} className="flex gap-3 pl-8 relative">
                                <div
                                  className={`absolute left-2.5 w-3 h-3 rounded-full border-2 top-1 ${
                                    m.status === 'completed'
                                      ? 'bg-green-500 border-green-500'
                                      : isOverdue
                                      ? 'bg-red-400 border-red-400'
                                      : 'bg-white border-gray-400'
                                  }`}
                                />
                                <div className="flex-1 bg-gray-50 rounded-lg p-3">
                                  <div className="flex items-start justify-between gap-2">
                                    <div>
                                      <div className="text-sm font-medium text-gray-800">
                                        {MILESTONE_TYPE_ICONS[m.milestone_type] ?? MILESTONE_TYPE_ICONS.default}{' '}
                                        {m.title}
                                      </div>
                                      <div className="text-xs text-gray-400 mt-0.5">
                                        Due: {new Date(m.due_date).toLocaleDateString()}
                                        {m.owner ? ` · ${m.owner}` : ''}
                                        {isOverdue && !m.completed_date && (
                                          <span className="ml-2 text-red-500 font-medium">OVERDUE</span>
                                        )}
                                      </div>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <span
                                        className={`status-badge ${
                                          m.status === 'completed'
                                            ? 'bg-green-100 text-green-700'
                                            : isOverdue
                                            ? 'bg-red-100 text-red-700'
                                            : 'bg-gray-100 text-gray-600'
                                        }`}
                                      >
                                        {m.status}
                                      </span>
                                      {m.status !== 'completed' && (
                                        <button
                                          onClick={() => completeMilestoneMutation.mutate(m.id)}
                                          disabled={completeMilestoneMutation.isPending}
                                          className="text-xs px-2 py-1 bg-green-50 text-green-600 hover:bg-green-100 rounded transition-colors disabled:opacity-60 flex items-center gap-1"
                                        >
                                          <CheckCircle className="w-3 h-3" />
                                          Done
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Team tab */}
              {drawerTab === 'team' && (
                <div className="space-y-4">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 text-left">
                          <th className="pb-2 font-semibold text-gray-600 text-xs">Auditor</th>
                          <th className="pb-2 font-semibold text-gray-600 text-xs">Role</th>
                          <th className="pb-2 font-semibold text-gray-600 text-xs">Allocated</th>
                          <th className="pb-2 font-semibold text-gray-600 text-xs">Actual</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {resources.length === 0 && (
                          <tr>
                            <td colSpan={4} className="py-6 text-center text-gray-400 text-xs">No team members</td>
                          </tr>
                        )}
                        {resources.map((r) => (
                          <tr key={r.id}>
                            <td className="py-2 pr-4">
                              <div className="flex items-center gap-2">
                                <InitialsAvatar name={r.auditor_name} />
                                <div>
                                  <div className="text-sm font-medium text-gray-800">{r.auditor_name}</div>
                                  <div className="text-xs text-gray-400">{r.auditor_email}</div>
                                </div>
                              </div>
                            </td>
                            <td className="py-2 pr-4">
                              <span className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
                                {r.role}
                              </span>
                            </td>
                            <td className="py-2 pr-4 text-gray-600">{r.allocated_hours}h</td>
                            <td className="py-2 text-gray-600">{r.actual_hours ?? 0}h</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Add Member form */}
                  <div className="border-t border-gray-200 pt-4">
                    <div className="text-xs font-semibold text-gray-600 mb-2">Add Team Member</div>
                    <form onSubmit={handleAddMember} className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Name *</label>
                        <input
                          required
                          type="text"
                          value={memberForm.auditor_name}
                          onChange={(e) => setMemberForm((f) => ({ ...f, auditor_name: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Email *</label>
                        <input
                          required
                          type="email"
                          value={memberForm.auditor_email}
                          onChange={(e) => setMemberForm((f) => ({ ...f, auditor_email: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Role</label>
                        <select
                          value={memberForm.role}
                          onChange={(e) => setMemberForm((f) => ({ ...f, role: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        >
                          {RESOURCE_ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Allocated Hours</label>
                        <input
                          type="number"
                          min={1}
                          value={memberForm.allocated_hours}
                          onChange={(e) => setMemberForm((f) => ({ ...f, allocated_hours: Number(e.target.value) }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div className="col-span-2 flex justify-end">
                        <button
                          type="submit"
                          disabled={assignMemberMutation.isPending}
                          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-sm disabled:opacity-60"
                        >
                          {assignMemberMutation.isPending ? 'Adding…' : 'Add Member'}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Time tab */}
              {drawerTab === 'time' && (
                <div className="space-y-5">
                  {/* Donut chart */}
                  {hoursData.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-600 mb-2">Hours by Activity</div>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie data={hoursData} dataKey="value" nameKey="activity" cx="50%" cy="50%" outerRadius={70} label={({ activity }) => activity}>
                            {hoursData.map((_entry, index) => (
                              <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Auditor breakdown */}
                  {hours && hours.by_auditor.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-600 mb-2">Hours by Auditor</div>
                      <div className="divide-y divide-gray-100">
                        {hours.by_auditor.map((a) => (
                          <div key={a.email} className="py-2 flex justify-between text-sm">
                            <span className="text-gray-700">{a.name}</span>
                            <span className="font-medium text-gray-900">{a.hours}h</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Log hours form */}
                  <div className="border-t border-gray-200 pt-4">
                    <div className="text-xs font-semibold text-gray-600 mb-2">Log Hours</div>
                    <form onSubmit={handleLogHours} className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Auditor Name *</label>
                        <input
                          required
                          type="text"
                          value={logForm.auditor_name}
                          onChange={(e) => setLogForm((f) => ({ ...f, auditor_name: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Email</label>
                        <input
                          type="email"
                          value={logForm.auditor_email}
                          onChange={(e) => setLogForm((f) => ({ ...f, auditor_email: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Date</label>
                        <input
                          type="date"
                          value={logForm.entry_date}
                          onChange={(e) => setLogForm((f) => ({ ...f, entry_date: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Hours</label>
                        <input
                          type="number"
                          min={0.25}
                          step={0.25}
                          max={24}
                          value={logForm.hours}
                          onChange={(e) => setLogForm((f) => ({ ...f, hours: Number(e.target.value) }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Activity</label>
                        <select
                          value={logForm.activity_type}
                          onChange={(e) => setLogForm((f) => ({ ...f, activity_type: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        >
                          {ACTIVITY_TYPES.map((a) => (
                            <option key={a} value={a}>{a}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 mb-1">Description</label>
                        <input
                          type="text"
                          value={logForm.description}
                          onChange={(e) => setLogForm((f) => ({ ...f, description: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                        />
                      </div>
                      <div className="col-span-2 flex items-center gap-3 justify-between">
                        <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={logForm.is_billable}
                            onChange={(e) => setLogForm((f) => ({ ...f, is_billable: e.target.checked }))}
                            className="accent-indigo-600"
                          />
                          Billable
                        </label>
                        <button
                          type="submit"
                          disabled={logHoursMutation.isPending}
                          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-sm disabled:opacity-60"
                        >
                          {logHoursMutation.isPending ? 'Logging…' : 'Log Hours'}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create Engagement Modal */}
      {createOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setCreateOpen(false)} />
          <form
            onSubmit={handleCreateSubmit}
            className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg m-4 overflow-y-auto max-h-[90vh]"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-800">New Engagement</h2>
              <button type="button" onClick={() => setCreateOpen(false)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-700" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-700 mb-1">Title *</label>
                  <input
                    required
                    type="text"
                    value={createForm.title}
                    onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Code</label>
                  <input
                    type="text"
                    value={createForm.engagement_code}
                    onChange={(e) => setCreateForm((f) => ({ ...f, engagement_code: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Audit Type</label>
                  <select
                    value={createForm.audit_type}
                    onChange={(e) => setCreateForm((f) => ({ ...f, audit_type: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  >
                    {AUDIT_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Start Date</label>
                  <input
                    type="date"
                    value={createForm.planned_start_date}
                    onChange={(e) => setCreateForm((f) => ({ ...f, planned_start_date: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">End Date</label>
                  <input
                    type="date"
                    value={createForm.planned_end_date}
                    onChange={(e) => setCreateForm((f) => ({ ...f, planned_end_date: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Budget Hours</label>
                  <input
                    type="number"
                    min={0}
                    value={createForm.budget_hours}
                    onChange={(e) => setCreateForm((f) => ({ ...f, budget_hours: Number(e.target.value) }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Lead Auditor</label>
                  <input
                    type="text"
                    value={createForm.lead_auditor}
                    onChange={(e) => setCreateForm((f) => ({ ...f, lead_auditor: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Engagement Manager</label>
                  <input
                    type="text"
                    value={createForm.engagement_manager}
                    onChange={(e) => setCreateForm((f) => ({ ...f, engagement_manager: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-700 mb-1">Scope</label>
                  <textarea
                    rows={2}
                    value={createForm.scope}
                    onChange={(e) => setCreateForm((f) => ({ ...f, scope: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-700 mb-1">Objectives</label>
                  <textarea
                    rows={2}
                    value={createForm.objectives}
                    onChange={(e) => setCreateForm((f) => ({ ...f, objectives: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>
            </div>
            <div className="px-5 py-4 border-t border-gray-200 flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm disabled:opacity-60"
              >
                {createMutation.isPending ? 'Creating…' : 'Create Engagement'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
