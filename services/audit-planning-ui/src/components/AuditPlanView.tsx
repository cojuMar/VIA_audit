import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Check, Zap, X } from 'lucide-react';
import {
  fetchPlans,
  createPlan,
  fetchPlanSummary,
  fetchEntities,
  approvePlan,
  autoPopulatePlan,
  createPlanItem,
  updatePlanItem,
} from '../api';
import type { AuditPlan, PlanItem, PlanSummary, AuditEntity } from '../types';

interface Props {
  tenantId: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'badge-critical',
  high: 'badge-high',
  medium: 'badge-medium',
  low: 'badge-low',
};

const STATUS_OPTIONS = ['planned', 'in_progress', 'completed', 'deferred', 'cancelled'];

const PRIORITY_OPTIONS = ['critical', 'high', 'medium', 'low'];

const AUDIT_TYPES = ['financial', 'operational', 'compliance', 'it', 'fraud', 'follow_up'];

function PriorityCard({
  label,
  count,
  colorClass,
}: {
  label: string;
  count: number;
  colorClass: string;
}) {
  return (
    <div className={`rounded-lg border p-4 text-center ${colorClass}`}>
      <div className="text-2xl font-bold">{count}</div>
      <div className="text-xs font-medium capitalize mt-0.5">{label}</div>
    </div>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-5 right-5 z-50 bg-green-700 text-white text-sm px-4 py-3 rounded-lg shadow-lg flex items-center gap-3">
      <Check className="w-4 h-4" />
      {message}
      <button onClick={onClose}>
        <X className="w-4 h-4 opacity-70 hover:opacity-100" />
      </button>
    </div>
  );
}

export default function AuditPlanView({ tenantId: _tenantId }: Props) {
  const qc = useQueryClient();
  const currentYear = new Date().getFullYear();

  const [yearTab, setYearTab] = useState(currentYear);
  const [toast, setToast] = useState<string | null>(null);
  const [approveModal, setApproveModal] = useState(false);
  const [approverName, setApproverName] = useState('');
  const [createPlanModal, setCreatePlanModal] = useState(false);
  const [newPlanForm, setNewPlanForm] = useState({
    plan_year: currentYear,
    title: '',
    description: '',
    total_budget_hours: 1000,
  });
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [newItemForm, setNewItemForm] = useState({
    title: '',
    audit_entity_id: '',
    audit_type: 'operational',
    priority: 'medium',
    planned_start_date: '',
    planned_end_date: '',
    budget_hours: 80,
    assigned_lead: '',
    rationale: '',
  });

  const { data: plans = [] } = useQuery<AuditPlan[]>({
    queryKey: ['plans'],
    queryFn: fetchPlans,
  });

  const { data: entities = [] } = useQuery<AuditEntity[]>({
    queryKey: ['entities'],
    queryFn: () => fetchEntities(),
  });

  const selectedPlan = useMemo(
    () => plans.find((p) => p.plan_year === yearTab),
    [plans, yearTab]
  );

  const { data: summary } = useQuery<PlanSummary>({
    queryKey: ['plan-summary', selectedPlan?.id],
    queryFn: () => fetchPlanSummary(selectedPlan!.id),
    enabled: !!selectedPlan,
  });

  const createPlanMutation = useMutation({
    mutationFn: createPlan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] });
      setCreatePlanModal(false);
      setToast('Plan created successfully');
    },
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => approvePlan(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] });
      qc.invalidateQueries({ queryKey: ['plan-summary', selectedPlan?.id] });
      setApproveModal(false);
      setToast('Plan approved');
    },
  });

  const autoPopulateMutation = useMutation({
    mutationFn: (id: string) => autoPopulatePlan(id),
    onSuccess: (data: { added: number; items?: PlanItem[] }) => {
      qc.invalidateQueries({ queryKey: ['plan-summary', selectedPlan?.id] });
      setToast(`Auto-populated: ${data.added ?? 0} items added`);
    },
  });

  const createItemMutation = useMutation({
    mutationFn: createPlanItem,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan-summary', selectedPlan?.id] });
      setAddItemOpen(false);
      setNewItemForm({
        title: '',
        audit_entity_id: '',
        audit_type: 'operational',
        priority: 'medium',
        planned_start_date: '',
        planned_end_date: '',
        budget_hours: 80,
        assigned_lead: '',
        rationale: '',
      });
      setToast('Plan item added');
    },
  });

  const updateItemMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: object }) => updatePlanItem(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan-summary', selectedPlan?.id] });
    },
  });

  const years = [currentYear - 1, currentYear, currentYear + 1];

  const items: PlanItem[] = summary
    ? (summary as PlanSummary & { items?: PlanItem[] }).items ?? []
    : [];

  function handleCreatePlan(e: React.FormEvent) {
    e.preventDefault();
    createPlanMutation.mutate(newPlanForm);
  }

  function handleAddItem(e: React.FormEvent) {
    e.preventDefault();
    createItemMutation.mutate({
      ...newItemForm,
      plan_id: selectedPlan!.id,
    });
  }

  function handleStatusChange(item: PlanItem, newStatus: string) {
    updateItemMutation.mutate({ id: item.id, data: { status: newStatus } });
  }

  const priorityCounts = summary?.items_by_priority ?? {};

  function planStatusBadge(status: string) {
    const map: Record<string, string> = {
      draft: 'bg-gray-100 text-gray-700',
      active: 'bg-blue-100 text-blue-700',
      approved: 'bg-green-100 text-green-700',
      closed: 'bg-gray-200 text-gray-600',
    };
    return `status-badge ${map[status] ?? 'bg-gray-100 text-gray-600'}`;
  }

  return (
    <div className="space-y-5">
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* Year tabs + create plan */}
      <div className="flex items-center gap-2">
        {years.map((y) => (
          <button
            key={y}
            onClick={() => setYearTab(y)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              yearTab === y
                ? 'bg-indigo-600 text-white'
                : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {y}
          </button>
        ))}
        <button
          onClick={() => setCreatePlanModal(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg"
        >
          <Plus className="w-4 h-4" />
          New Plan
        </button>
      </div>

      {!selectedPlan ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 shadow-sm">
          No plan found for {yearTab}. Create one above.
        </div>
      ) : (
        <>
          {/* Plan header */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex flex-wrap items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="text-lg font-bold text-gray-900">{selectedPlan.title}</h2>
                <span className={planStatusBadge(selectedPlan.status)}>
                  {selectedPlan.status}
                </span>
                {selectedPlan.approved_by && (
                  <span className="text-xs text-gray-400">
                    Approved by {selectedPlan.approved_by}
                  </span>
                )}
              </div>
              {selectedPlan.description && (
                <p className="text-sm text-gray-500 mt-1">{selectedPlan.description}</p>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              {selectedPlan.status !== 'approved' && (
                <button
                  onClick={() => setApproveModal(true)}
                  className="flex items-center gap-1.5 px-3 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg"
                >
                  <Check className="w-4 h-4" />
                  Approve
                </button>
              )}
              <button
                onClick={() => autoPopulateMutation.mutate(selectedPlan.id)}
                disabled={autoPopulateMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg disabled:opacity-60"
              >
                <Zap className="w-4 h-4" />
                Auto-Populate
              </button>
            </div>
          </div>

          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm text-center sm:col-span-1">
              <div className="text-xl font-bold text-gray-900">{selectedPlan.item_count ?? items.length}</div>
              <div className="text-xs text-gray-500 mt-0.5">Total Items</div>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm text-center sm:col-span-1">
              <div className="text-xl font-bold text-gray-900">{selectedPlan.total_budget_hours}h</div>
              <div className="text-xs text-gray-500 mt-0.5">Budget Hours</div>
            </div>
            {(['critical', 'high', 'medium', 'low'] as const).map((p) => (
              <PriorityCard
                key={p}
                label={p}
                count={priorityCounts[p] ?? 0}
                colorClass={
                  p === 'critical' ? 'bg-red-50 text-red-700 border-red-200' :
                  p === 'high' ? 'bg-orange-50 text-orange-700 border-orange-200' :
                  p === 'medium' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                  'bg-green-50 text-green-700 border-green-200'
                }
              />
            ))}
          </div>

          {/* Items table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Entity</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Type</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Priority</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Lead</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Dates</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Budget</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-10 text-gray-400">
                      No plan items. Add one below or use Auto-Populate.
                    </td>
                  </tr>
                ) : (
                  items.map((item) => {
                    const entity = entities.find((e) => e.id === item.audit_entity_id);
                    return (
                      <tr key={item.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{item.title}</td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {entity?.name ?? <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                            {item.audit_type}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={PRIORITY_COLORS[item.priority] ?? 'badge-medium'}>
                            {item.priority}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {item.assigned_lead ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                          {item.planned_start_date
                            ? `${item.planned_start_date} → ${item.planned_end_date ?? '?'}`
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{item.budget_hours}h</td>
                        <td className="px-4 py-3">
                          <select
                            value={item.status}
                            onChange={(e) => handleStatusChange(item, e.target.value)}
                            className="text-xs border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-300"
                          >
                            {STATUS_OPTIONS.map((s) => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>

            {/* Add item inline */}
            <div className="border-t border-gray-200 p-4">
              {!addItemOpen ? (
                <button
                  onClick={() => setAddItemOpen(true)}
                  className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800"
                >
                  <Plus className="w-4 h-4" />
                  Add Plan Item
                </button>
              ) : (
                <form onSubmit={handleAddItem} className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="sm:col-span-2">
                    <label className="block text-xs text-gray-500 mb-1">Title *</label>
                    <input
                      required
                      type="text"
                      value={newItemForm.title}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, title: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Entity</label>
                    <select
                      value={newItemForm.audit_entity_id}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, audit_entity_id: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    >
                      <option value="">— None —</option>
                      {entities.map((e) => (
                        <option key={e.id} value={e.id}>{e.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Type</label>
                    <select
                      value={newItemForm.audit_type}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, audit_type: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    >
                      {AUDIT_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Priority</label>
                    <select
                      value={newItemForm.priority}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, priority: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    >
                      {PRIORITY_OPTIONS.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Start Date</label>
                    <input
                      type="date"
                      value={newItemForm.planned_start_date}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, planned_start_date: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">End Date</label>
                    <input
                      type="date"
                      value={newItemForm.planned_end_date}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, planned_end_date: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Budget Hours</label>
                    <input
                      type="number"
                      min={1}
                      value={newItemForm.budget_hours}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, budget_hours: Number(e.target.value) }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Lead Auditor</label>
                    <input
                      type="text"
                      value={newItemForm.assigned_lead}
                      onChange={(e) => setNewItemForm((f) => ({ ...f, assigned_lead: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                  <div className="sm:col-span-4 flex gap-2 justify-end">
                    <button
                      type="button"
                      onClick={() => setAddItemOpen(false)}
                      className="px-3 py-1.5 border border-gray-300 text-gray-600 rounded text-sm hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={createItemMutation.isPending}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-sm disabled:opacity-60"
                    >
                      {createItemMutation.isPending ? 'Saving…' : 'Add Item'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </>
      )}

      {/* Approve modal */}
      {approveModal && selectedPlan && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setApproveModal(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm p-6 m-4">
            <h2 className="text-base font-semibold text-gray-800 mb-4">Approve Plan</h2>
            <label className="block text-sm text-gray-600 mb-1">Approver Name</label>
            <input
              type="text"
              value={approverName}
              onChange={(e) => setApproverName(e.target.value)}
              placeholder="Your name"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 mb-4"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setApproveModal(false)}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  approveMutation.mutate({ id: selectedPlan.id, name: approverName })
                }
                disabled={!approverName || approveMutation.isPending}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm disabled:opacity-60"
              >
                {approveMutation.isPending ? 'Approving…' : 'Confirm Approve'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Plan modal */}
      {createPlanModal && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setCreatePlanModal(false)} />
          <form
            onSubmit={handleCreatePlan}
            className="relative bg-white rounded-xl shadow-2xl w-full max-w-md p-6 m-4 space-y-4"
          >
            <h2 className="text-base font-semibold text-gray-800">Create New Plan</h2>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Plan Year</label>
              <input
                type="number"
                value={newPlanForm.plan_year}
                onChange={(e) => setNewPlanForm((f) => ({ ...f, plan_year: Number(e.target.value) }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Title *</label>
              <input
                required
                type="text"
                value={newPlanForm.title}
                onChange={(e) => setNewPlanForm((f) => ({ ...f, title: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
              <textarea
                rows={2}
                value={newPlanForm.description}
                onChange={(e) => setNewPlanForm((f) => ({ ...f, description: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Total Budget Hours</label>
              <input
                type="number"
                min={0}
                value={newPlanForm.total_budget_hours}
                onChange={(e) =>
                  setNewPlanForm((f) => ({ ...f, total_budget_hours: Number(e.target.value) }))
                }
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={() => setCreatePlanModal(false)}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createPlanMutation.isPending}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm disabled:opacity-60"
              >
                {createPlanMutation.isPending ? 'Creating…' : 'Create Plan'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
