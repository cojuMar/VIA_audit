import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  Plus,
  Edit2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronRight,
} from 'lucide-react';
import {
  fetchPolicies,
  fetchPolicyAckStatus,
  createPolicy,
  updatePolicy,
  setTenant,
} from '../api';
import type { HRPolicy, PolicyAckStatus } from '../types';

interface Props {
  tenantId: string;
}

const CATEGORIES = ['All', 'Security', 'HR', 'Finance', 'IT', 'Compliance', 'Safety'];

const CATEGORY_COLORS: Record<string, string> = {
  Security: 'bg-red-900 text-red-200',
  HR: 'bg-blue-900 text-blue-200',
  Finance: 'bg-green-900 text-green-200',
  IT: 'bg-purple-900 text-purple-200',
  Compliance: 'bg-yellow-900 text-yellow-200',
  Safety: 'bg-orange-900 text-orange-200',
};

function PolicyModal({
  policy,
  onClose,
  onDone,
}: {
  policy?: HRPolicy;
  onClose: () => void;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = !!policy;

  const [form, setForm] = useState({
    title: policy?.title ?? '',
    policy_key: policy?.policy_key ?? '',
    category: policy?.category ?? 'Security',
    description: policy?.description ?? '',
    acknowledgment_frequency_days: policy?.acknowledgment_frequency_days ?? 365,
    applies_to_roles: policy?.applies_to_roles ?? [] as string[],
    acknowledgment_required: policy?.acknowledgment_required ?? true,
    is_active: policy?.is_active ?? true,
  });

  const ROLES = ['all', 'manager', 'engineer', 'analyst', 'admin', 'hr', 'finance', 'executive'];

  const toggleRole = (role: string) => {
    setForm((f) => ({
      ...f,
      applies_to_roles: f.applies_to_roles.includes(role)
        ? f.applies_to_roles.filter((r) => r !== role)
        : [...f.applies_to_roles, role],
    }));
  };

  const mutation = useMutation({
    mutationFn: () =>
      isEdit
        ? updatePolicy(policy!.id, form)
        : createPolicy(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['policies'] });
      onDone();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg shadow-2xl overflow-y-auto max-h-[90vh]">
        <h3 className="text-lg font-semibold text-white mb-4">
          {isEdit ? 'Edit Policy' : 'New Policy'}
        </h3>
        <div className="space-y-4">
          <div>
            <label className="label">Title</label>
            <input
              className="input"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">Policy Key</label>
            <input
              className="input font-mono"
              value={form.policy_key}
              onChange={(e) => setForm((f) => ({ ...f, policy_key: e.target.value }))}
              placeholder="e.g., SEC_001"
            />
          </div>
          <div>
            <label className="label">Category</label>
            <select
              className="select"
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            >
              {CATEGORIES.filter((c) => c !== 'All').map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Description</label>
            <textarea
              className="input h-20 resize-none"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">Acknowledgment Frequency (days)</label>
            <input
              className="input"
              type="number"
              min={1}
              value={form.acknowledgment_frequency_days}
              onChange={(e) =>
                setForm((f) => ({ ...f, acknowledgment_frequency_days: Number(e.target.value) }))
              }
            />
          </div>
          <div>
            <label className="label">Applies to Roles</label>
            <div className="flex flex-wrap gap-2 mt-1">
              {ROLES.map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => toggleRole(role)}
                  className={`px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                    form.applies_to_roles.includes(role)
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {role}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.acknowledgment_required}
                onChange={(e) =>
                  setForm((f) => ({ ...f, acknowledgment_required: e.target.checked }))
                }
                className="rounded"
              />
              Acknowledgment Required
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                className="rounded"
              />
              Active
            </label>
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-6">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.title}
          >
            {mutation.isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Policy'}
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 text-sm mt-2">Failed to save. Please try again.</p>
        )}
      </div>
    </div>
  );
}

function PolicyDetail({
  policy,
  tenantId,
  onEdit,
}: {
  policy: HRPolicy;
  tenantId: string;
  onEdit: () => void;
}) {
  const { data: ackStatuses } = useQuery<PolicyAckStatus[]>({
    queryKey: ['policy-ack-status', policy.id, tenantId],
    queryFn: () => fetchPolicyAckStatus(policy.id),
  });

  const total = ackStatuses?.length ?? 0;
  const acked = ackStatuses?.filter((s) => s.acknowledged && !s.is_overdue).length ?? 0;
  const pct = total > 0 ? Math.round((acked / total) * 100) : 0;

  const overdue = ackStatuses?.filter((s) => s.is_overdue) ?? [];

  const barColor = pct >= 90 ? 'bg-green-500' : pct >= 70 ? 'bg-amber-500' : 'bg-red-500';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-white">{policy.title}</h2>
            <span
              className={`badge ${CATEGORY_COLORS[policy.category] ?? 'bg-gray-700 text-gray-300'}`}
            >
              {policy.category}
            </span>
            {!policy.is_active && (
              <span className="badge bg-gray-700 text-gray-400">Inactive</span>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1 font-mono">
            {policy.policy_key} · v{policy.current_version}
          </div>
          {policy.description && (
            <p className="text-sm text-gray-400 mt-2">{policy.description}</p>
          )}
        </div>
        <button className="btn-secondary" onClick={onEdit}>
          <Edit2 size={13} /> Edit
        </button>
      </div>

      {/* Roles */}
      <div>
        <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Applies To</div>
        <div className="flex flex-wrap gap-1.5">
          {policy.applies_to_roles.map((r) => (
            <span key={r} className="badge bg-gray-700 text-gray-300">
              {r}
            </span>
          ))}
        </div>
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 mb-1">Acknowledgment Frequency</div>
          <div className="text-gray-200 font-medium">{policy.acknowledgment_frequency_days} days</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 mb-1">Acknowledgment Required</div>
          <div className={policy.acknowledgment_required ? 'text-green-400 font-medium' : 'text-gray-400'}>
            {policy.acknowledgment_required ? 'Yes' : 'No'}
          </div>
        </div>
      </div>

      {/* Compliance Bar */}
      {total > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-gray-400 uppercase">Acknowledgment Compliance</span>
            <span className="text-sm font-bold text-gray-200">{pct}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`${barColor} h-2 rounded-full transition-all`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {acked} of {total} applicable employees acknowledged
          </div>
        </div>
      )}

      {/* Acknowledgment Status Table */}
      {ackStatuses && ackStatuses.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Acknowledgment Status</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Employee</th>
                  <th className="th">Status</th>
                  <th className="th">Last Acknowledged</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {ackStatuses.slice(0, 20).map((s, i) => (
                  <tr key={i} className="hover:bg-gray-800/50">
                    <td className="td text-gray-300">{s.title}</td>
                    <td className="td">
                      {s.acknowledged && !s.is_overdue ? (
                        <span className="flex items-center gap-1 text-green-400 text-xs">
                          <CheckCircle size={12} /> Current
                        </span>
                      ) : s.is_overdue ? (
                        <span className="flex items-center gap-1 text-red-400 text-xs">
                          <AlertTriangle size={12} /> Overdue
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-gray-500 text-xs">
                          <XCircle size={12} /> Never
                        </span>
                      )}
                    </td>
                    <td className="td text-gray-500 text-xs">
                      {s.acknowledged_at ? new Date(s.acknowledged_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Overdue Employees */}
      {overdue.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-400 mb-2 flex items-center gap-1.5">
            <AlertTriangle size={14} /> Overdue Employees ({overdue.length})
          </h3>
          <div className="space-y-1">
            {overdue.map((o, i) => (
              <div key={i} className="flex items-center justify-between bg-red-950/30 border border-red-900/40 rounded-lg px-3 py-2">
                <span className="text-sm text-gray-300">{o.title}</span>
                {o.days_until_due != null && (
                  <span className="text-xs text-red-400">
                    {Math.abs(o.days_until_due)}d overdue
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PoliciesManager({ tenantId }: Props) {
  setTenant(tenantId);
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editPolicy, setEditPolicy] = useState<HRPolicy | undefined>(undefined);

  const { data: policies } = useQuery<HRPolicy[]>({
    queryKey: ['policies', tenantId],
    queryFn: fetchPolicies,
  });

  const filtered = (policies ?? []).filter(
    (p) => selectedCategory === 'All' || p.category === selectedCategory
  );

  const selectedPolicy = policies?.find((p) => p.id === selectedPolicyId);

  return (
    <div className="flex h-full overflow-hidden" style={{ minHeight: 0 }}>
      {/* Left Pane */}
      <div className="w-80 flex-shrink-0 flex flex-col border-r border-gray-800 overflow-hidden">
        {/* Category Tabs */}
        <div className="p-4 pb-2 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-300">Policies</h2>
            <button
              className="btn-primary text-xs py-1"
              onClick={() => {
                setEditPolicy(undefined);
                setShowModal(true);
              }}
            >
              <Plus size={12} /> Add Policy
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2 py-0.5 rounded-md text-xs font-medium transition-colors ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Policy List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {filtered.length === 0 && (
            <div className="text-center text-gray-500 text-sm py-8">No policies found.</div>
          )}
          {filtered.map((policy) => (
            <button
              key={policy.id}
              onClick={() => setSelectedPolicyId(policy.id)}
              className={`w-full text-left rounded-xl p-3 border transition-all ${
                selectedPolicyId === policy.id
                  ? 'border-indigo-500 bg-indigo-950/40'
                  : 'border-gray-800 bg-gray-900 hover:border-gray-700 hover:bg-gray-800/50'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-200 text-sm truncate">{policy.title}</div>
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    <span
                      className={`badge text-xs ${CATEGORY_COLORS[policy.category] ?? 'bg-gray-700 text-gray-300'}`}
                    >
                      {policy.category}
                    </span>
                    <span className="text-xs text-gray-500">v{policy.current_version}</span>
                    {!policy.is_active && (
                      <span className="badge bg-gray-800 text-gray-500 text-xs">Inactive</span>
                    )}
                  </div>
                  {policy.applies_to_roles.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {policy.applies_to_roles.slice(0, 3).map((r) => (
                        <span key={r} className="text-xs text-gray-500 bg-gray-800 rounded px-1">
                          {r}
                        </span>
                      ))}
                      {policy.applies_to_roles.length > 3 && (
                        <span className="text-xs text-gray-600">
                          +{policy.applies_to_roles.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="text-xs text-gray-600 mt-1">
                    Every {policy.acknowledgment_frequency_days}d
                  </div>
                </div>
                <ChevronRight size={14} className="text-gray-600 flex-shrink-0 mt-1" />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right Pane */}
      <div className="flex-1 overflow-y-auto p-6">
        {selectedPolicy ? (
          <PolicyDetail
            policy={selectedPolicy}
            tenantId={tenantId}
            onEdit={() => {
              setEditPolicy(selectedPolicy);
              setShowModal(true);
            }}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-500">
            <Shield size={40} className="mb-3 text-gray-700" />
            <p className="text-sm">Select a policy to view details</p>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <PolicyModal
          policy={editPolicy}
          onClose={() => setShowModal(false)}
          onDone={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
